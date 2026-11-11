"""
HindsightMemory — CanonicalMemory'nin anlamsal arama genişletmesi.

Tasarım ilkesi: CanonicalMemory'yi DEĞİŞTİRMEZ, genişletir.
- merge_evidence() ve get_task_memory() CanonicalMemory'den miras alınır
  (executor ve testler hiç değişmeden çalışır).
- Üstüne SQLite + yerel embedding ile anlamsal arama eklenir.
- sentence-transformers/numpy YOKKEN bile çalışır (anlamsal özellikler
  graceful olarak devre dışı kalır, kanıt saklama etkilenmez).
- Embedding modeli ilk kullanımda LAZY olarak yüklenir (startup bloklanmaz).
- PINEAL_MEMORY_ENGINE=hindsight env'i ile aktif edilir; varsayılan canonical'dır.
"""
from __future__ import annotations

from typing import Tuple
import asyncio
import hashlib
import importlib.util
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.services.canonical_memory import CanonicalMemory

logger = logging.getLogger(__name__)

# Do not import this configured dependency on the default canonical path.
# Hindsight imports it lazily when semantic behavior is actually requested.
NUMPY_AVAILABLE = True
ST_AVAILABLE = importlib.util.find_spec("sentence_transformers") is not None

# Varsayılan hafif embedding modeli (~80MB, ilk kullanımda indirilir)
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 çıktı boyutu


class HindsightMemory(CanonicalMemory):
    """
    Kanıtları JSON dosyasında saklamaya DEVAM eder (CanonicalMemory gibi),
    ek olarak SQLite'ta anlamsal indeks tutar.

    Anlamsal indeks yalnızca arama/deduplikasyon içindir; kanıt kayıtları
    her zaman CanonicalMemory'nin dosya tabanlı sistemine yazılır, böylece
    mevcut davranış ve testler bozulmaz.
    """

    def __init__(
        self,
        storage_path: str = "./memory/",
        db_path: Optional[str] = None,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        dedup_threshold: float = 0.95,
    ):
        super().__init__(storage_path=storage_path)

        self.db_path = db_path or os.path.join(storage_path, "hindsight.db")
        self.embedding_model_name = embedding_model
        self.dedup_threshold = dedup_threshold

        # Lazy-loaded embedding modeli (startup'ta indirilmez/bloklanmaz)
        self._embedder = None
        self._embedder_lock = threading.Lock()
        self._embedder_load_attempted = False
        self._embedder_error = None

        self._init_db()

    # ------------------------------------------------------------------ DB
    def _connect(self) -> sqlite3.Connection:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        return sqlite3.connect(self.db_path, timeout=5)

    def _init_db(self) -> None:
        try:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS semantic_memories (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id      TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        content_text TEXT NOT NULL,
                        embedding    TEXT,
                        metadata     TEXT,
                        created_at   REAL NOT NULL,
                        UNIQUE(task_id, content_hash)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sm_task ON semantic_memories(task_id)"
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning("HindsightMemory DB başlatılamadı: %s", exc)

    # ------------------------------------------------------------------ Embedding
    def _get_embedder(self):
        """Embedding modelini ilk çağrıda yükler (thread-safe, lazy)."""
        if self._embedder is not None:
            return self._embedder
        if self._embedder_load_attempted:
            return self._embedder  # önceki denemede başarısızdı, tekrar deneme

        with self._embedder_lock:
            if self._embedder is not None or self._embedder_load_attempted:
                return self._embedder
            self._embedder_load_attempted = True

            if not ST_AVAILABLE:
                self._embedder_error = {
                    "error_code": "OPTIONAL_DEPENDENCY_MISSING",
                    "dependency": "sentence-transformers",
                }
                logger.info(
                    "HindsightMemory: sentence-transformers kurulu değil — "
                    "anlamsal özellikler devre dışı, kanıt saklama etkilenmez."
                )
                return None

            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:
                if exc.name == "sentence_transformers":
                    self._embedder_error = {
                        "error_code": "OPTIONAL_DEPENDENCY_MISSING",
                        "dependency": "sentence-transformers",
                    }
                    return None
                # Installed package with a missing transitive dependency is
                # broken, not equivalent to an optional package being absent.
                raise

            try:
                logger.info("HindsightMemory embedding modeli yükleniyor: %s", self.embedding_model_name)
                self._embedder = SentenceTransformer(self.embedding_model_name)
                self._embedder_error = None
                logger.info("HindsightMemory embedding modeli hazır.")
            except Exception as exc:
                self._embedder_error = {
                    "error_code": "EMBEDDING_MODEL_LOAD_FAILED",
                    "dependency": "sentence-transformers",
                    "cause_type": type(exc).__name__,
                }
                logger.warning(
                    "HindsightMemory embedding modeli yüklenemedi: %s — "
                    "anlamsal arama devre dışı.", exc
                )
                self._embedder = None
            return self._embedder

    def _embed(self, text: str) -> Optional[List[float]]:
        embedder = self._get_embedder()
        if embedder is None:
            return None
        try:
            vec = embedder.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            if hasattr(vec, "tolist"):
                return vec.tolist()
            return list(vec)
        except Exception as exc:
            logger.warning("HindsightMemory embedding hatası: %s", exc)
            return None

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not NUMPY_AVAILABLE:
            # Saf Python fallback
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5
            nb = sum(y * y for y in b) ** 0.5
            return dot / (na * nb) if na and nb else 0.0
        arr_a = np.array(a)
        arr_b = np.array(b)
        norm = np.linalg.norm(arr_a) * np.linalg.norm(arr_b)
        return float(np.dot(arr_a, arr_b) / norm) if norm else 0.0

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------ CanonicalMemory genişletmesi
    async def merge_evidence(
        self, task_id: str, evidence_chain: List[Dict], metadata: Optional[Dict] = None
    ):
        """Preserve CanonicalMemory's drop-in merge_evidence signature."""
        await super().merge_evidence(task_id, evidence_chain, metadata=metadata)
        # Anlamsal indekse de yaz (en iyi çaba — hata kanıt akışını bozmaz)
        def _index_all_evidence():
            records = []
            for evidence in evidence_chain:
                try:
                    content_text = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
                    content_hash = self._hash(content_text)
                    embedding = self._embed(content_text)
                    embedding_str = json.dumps(embedding) if embedding is not None else None
                    metadata_str = json.dumps(evidence, ensure_ascii=False, default=str)
                    records.append((
                        task_id,
                        content_hash,
                        content_text,
                        embedding_str,
                        metadata_str,
                        datetime.now(timezone.utc).timestamp(),
                    ))
                except Exception as exc:
                    logger.debug("HindsightMemory kanıt hazırlama hatası (yoksayıldı): %s", exc)

            if not records:
                return

            # OPTIMIZATION: Using `executemany` inside a single connection and commit block
            # drastically reduces SQLite transaction overhead and avoids file-level locking
            # issues compared to multiple independent connections (e.g. O(1) commits instead of O(N)).
            conn = self._connect()
            try:
                conn.executemany(
                    "INSERT OR IGNORE INTO semantic_memories "
                    "(task_id, content_hash, content_text, embedding, metadata, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    records
                )
                conn.commit()
            except Exception as exc:
                logger.debug("HindsightMemory toplu indeksleme hatası (yoksayıldı): %s", exc)
            finally:
                conn.close()

        if evidence_chain:
            await asyncio.to_thread(_index_all_evidence)

    # ------------------------------------------------------------------ Anlamsal arama
    def _fetch_rows(self, task_id: Optional[str]) -> List[Tuple]:
        conn = self._connect()
        try:
            if task_id:
                self._validate_task_id(task_id)
                return conn.execute(
                    "SELECT content_text, embedding, metadata, created_at "
                    "FROM semantic_memories WHERE task_id = ? ORDER BY created_at DESC LIMIT 5000",
                    (task_id,),
                ).fetchall()
            else:
                return conn.execute(
                    "SELECT content_text, embedding, metadata, created_at "
                    "FROM semantic_memories ORDER BY created_at DESC LIMIT 5000"
                ).fetchall()
        finally:
            conn.close()

    async def semantic_search(
        self,
        query: str,
        task_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Anlamsal benzerliğe göre kanıt arar.

        Embedding modeli yoksa boş liste döner (hata fırlatmaz).
        """
        query_embedding = self._embed(query)
        if query_embedding is None:
            return []

        rows = await asyncio.to_thread(self._fetch_rows, task_id)

        results = []
        for content_text, embedding_str, metadata_str, created_at in rows:
            if not embedding_str:
                continue
            stored_embedding = json.loads(embedding_str)
            similarity = self._cosine(query_embedding, stored_embedding)
            results.append({
                "content": json.loads(metadata_str) if metadata_str else content_text,
                "similarity": round(similarity, 4),
                "created_at": created_at,
                "task_id": task_id,
            })

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        try:
            conn = self._connect()
            try:
                total, = conn.execute("SELECT COUNT(*) FROM semantic_memories").fetchone()
                tasks, = conn.execute(
                    "SELECT COUNT(DISTINCT task_id) FROM semantic_memories"
                ).fetchone()
            finally:
                conn.close()
        except Exception:
            total, tasks = 0, 0

        embedder = self._get_embedder()
        return {
            "engine": "hindsight",
            "total_indexed": total,
            "unique_tasks": tasks,
            "semantic_enabled": embedder is not None,
            "semantic_error": self._embedder_error,
            "embedding_model": self.embedding_model_name if embedder else None,
            "storage_path": self.storage_path,
            "db_path": self.db_path,
        }


def build_memory_from_env() -> CanonicalMemory:
    """
    PINEAL_MEMORY_ENGINE ayarına göre bellek motorunu döndürür.
    Varsayılan 'canonical'dır (güvenli); 'hindsight' için HindsightMemory.
    """
    engine = os.getenv("PINEAL_MEMORY_ENGINE", "canonical").strip().lower()
    if engine in ("hindsight", "auto"):
        storage_path = os.getenv("PINEAL_MEMORY_PATH", "./memory/")
        db_path = os.getenv("PINEAL_MEMORY_DB", os.path.join(storage_path, "hindsight.db"))
        embedding_model = os.getenv("PINEAL_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        return HindsightMemory(
            storage_path=storage_path,
            db_path=db_path,
            embedding_model=embedding_model,
        )
    return CanonicalMemory(os.getenv("PINEAL_MEMORY_PATH", "./memory/"))
