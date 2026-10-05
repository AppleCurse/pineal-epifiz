"""FAZ B · B7 — DEĞİŞİM İZLEME.

Soru: "bu hedefi bir hafta önce de taramıştık, NE DEĞİŞTİ?"

Bugün her görev belleğe yazılıyor ama iki görev arasındaki fark HİÇ
raporlanmıyor. Bu modül o boşluğu kapatır:

    kanıt zinciri → kararlı parmak izi (digest) → önceki anlık görüntüyle fark

Sözleşme (projenin dürüstlük kurallarıyla birebir aynı):
- Parmak izi yalnız KANIDIN KENDİSİNDEN üretilir (kaynak anahtarı + içerik
  karması). Tarih/saat damgası FARK sayılmaz: aynı bulgunun yeniden görülmesi
  "değişim" değildir.
- Önceki kayıt yoksa `available=False` + sebep `no_baseline`; fark UYDURULMAZ.
- Depolama: `memory/changes/<hedef>.json`; hedef başına son N anlık görüntü.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SnapshotEntry",
    "ChangeSnapshot",
    "ChangeReport",
    "target_key",
    "build_snapshot",
    "diff_snapshots",
    "record_snapshot",
    "latest_before",
    "load_history",
]

_MAX_SNAPSHOTS = 10
_SAFE = re.compile(r"[^a-z0-9._-]+")


class SnapshotEntry(BaseModel):
    """Tek bir kanıt kaydının parmak izi."""

    key: str
    digest: str
    epistemic_type: str = "observation"
    source_engine: str = ""
    model_config = ConfigDict(extra="forbid")


class ChangeSnapshot(BaseModel):
    target: str
    task_id: str
    captured_at: str
    entries: list[SnapshotEntry] = Field(default_factory=list)
    entry_count: int = 0
    #: Tüm kanıtın tek karması (hızlı "hiç değişmedi" testi).
    fingerprint: str = ""
    model_config = ConfigDict(extra="forbid")


class ChangeReport(BaseModel):
    available: bool = False
    reason: str | None = None
    target: str = ""
    before_task_id: str | None = None
    after_task_id: str | None = None
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    unchanged_count: int = 0
    machine_note: str = ""
    model_config = ConfigDict(extra="forbid")


def _slug(value: str) -> str:
    return _SAFE.sub("_", (value or "").strip().lower()).strip("_")[:64]


def target_key(target_profile: Any = None, evidence: Any = None) -> str:
    """Hedefin kararlı anahtarı (kullanıcı adı yoksa kanıttan URL host'u)."""
    if isinstance(target_profile, dict):
        for field in ("username", "name"):
            value = str(target_profile.get(field) or "").strip().lstrip("@")
            if value:
                return _slug(value)
    items = [i for i in (evidence or []) if isinstance(i, dict)] if isinstance(
        evidence, Sequence
    ) and not isinstance(evidence, (str, bytes)) else []
    for item in items:
        for ref in (item.get("provenance_refs") or []):
            host = str(ref).split("//", 1)[-1].split("/", 1)[0].lower()
            host = host[4:] if host.startswith("www.") else host
            if host and "." in host:
                return _slug(host)
    return ""


def _entry_key(item: dict) -> str:
    """Kanıt kaydının KİMLİĞİ (içerik HARİÇ).

    `evidence_id` kullanılmaz: her görevde yeniden üretilir ve HER ŞEY "yeni"
    görünürdü. Anahtar, bulgunun KENDİSİNDEN türetilir:
    ``kaynak motor | kapsam | ilk kaynak bağlantısı``.

    İçerik anahtara DAHİL DEĞİLDİR — aksi hâlde bir bulgunun METNİ değiştiğinde
    "1 kayıp + 1 yeni" görünürdü. Metin değişimi `digest` ile yakalanır ve
    raporda "değişen" olarak ayrıca sayılır (dürüst ayrım).
    """
    engine = str(item.get("source_engine") or item.get("agent") or "?")
    scope = item.get("scope") or {}
    scope_key = ""
    if isinstance(scope, dict):
        scope_key = str(
            scope.get("site")
            or scope.get("platform")
            or scope.get("measurement")
            or scope.get("kind")
            or ""
        )
    first_ref = ""
    refs = item.get("provenance_refs") or []
    if refs:
        first_ref = str(refs[0])
    raw = f"{engine}|{scope_key}|{first_ref}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _digest(item: dict) -> str:
    """İçerik karması: aynı bulgunun METNİ değişirse fark sayılır."""
    payload = json.dumps(
        {
            "content": str(item.get("content") or ""),
            "refs": [str(r) for r in (item.get("provenance_refs") or [])],
            "scope": item.get("scope") or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _iter_items(evidence: Any) -> list[dict]:
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence") or evidence.get("evidence_chain") or []
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        return []
    return [i for i in evidence if isinstance(i, dict)]


def build_snapshot(
    evidence: Any,
    target_profile: Any = None,
    *,
    task_id: str = "",
    target: str | None = None,
) -> ChangeSnapshot:
    """Kanıt zincirinden anlık görüntü (kararlı parmak izleri)."""
    items = _iter_items(evidence)
    target_slug = target or target_key(target_profile, items)
    entries = [
        SnapshotEntry(
            key=_entry_key(item),
            digest=_digest(item),
            epistemic_type=str(item.get("epistemic_type") or "observation"),
            source_engine=str(item.get("source_engine") or ""),
        )
        for item in items
    ]
    entries.sort(key=lambda e: e.key)
    fingerprint = hashlib.sha256(
        "|".join(f"{e.key}:{e.digest}" for e in entries).encode("utf-8")
    ).hexdigest()[:24]
    return ChangeSnapshot(
        target=target_slug,
        task_id=task_id,
        captured_at=datetime.now(timezone.utc).isoformat(),
        entries=entries,
        entry_count=len(entries),
        fingerprint=fingerprint,
    )


def diff_snapshots(before: ChangeSnapshot | None, after: ChangeSnapshot | None) -> ChangeReport:
    """İki anlık görüntünün farkı. Önceki yoksa fark UYDURULMAZ."""
    target = (after or before).target if (after or before) else ""
    if before is None or after is None:
        return ChangeReport(
            available=False,
            reason="no_baseline",
            target=target,
            after_task_id=after.task_id if after else None,
            before_task_id=before.task_id if before else None,
            machine_note="DEĞİŞİM: karşılaştırılacak önceki kayıt yok.",
        )

    before_map = {e.key: e for e in before.entries}
    after_map = {e.key: e for e in after.entries}

    added = sorted(set(after_map) - set(before_map))
    removed = sorted(set(before_map) - set(after_map))
    changed = sorted(
        k for k in set(before_map) & set(after_map) if before_map[k].digest != after_map[k].digest
    )
    unchanged = len(set(before_map) & set(after_map)) - len(changed)

    if not (added or removed or changed):
        note = f"DEĞİŞİM: {len(after_map)} kayıt birebir aynı — değişim yok."
    else:
        note = (
            f"DEĞİŞİM: +{len(added)} yeni · -{len(removed)} kayıp · "
            f"~{len(changed)} değişen · {unchanged} aynı."
        )

    return ChangeReport(
        available=True,
        reason=None,
        target=target,
        before_task_id=before.task_id,
        after_task_id=after.task_id,
        added=added,
        removed=removed,
        changed=changed,
        unchanged_count=unchanged,
        machine_note=note,
    )


def _history_path(storage_path: str, target: str) -> str:
    return os.path.join(storage_path, "changes", f"{target or 'unknown'}.json")


def load_history(storage_path: str, target: str) -> list[ChangeSnapshot]:
    path = _history_path(storage_path, target)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return []
    rows = payload.get("snapshots") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[ChangeSnapshot] = []
    for row in rows:
        try:
            out.append(ChangeSnapshot.model_validate(row))
        except Exception:
            continue  # bozuk satır atlanır, dosya gizlenmez
    return out


def _atomic_write(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def latest_before(storage_path: str, target: str, task_id: str) -> ChangeSnapshot | None:
    """Bu görev DIŞINDAKİ en son anlık görüntü (kendisiyle karşılaştırma olmaz)."""
    rows = [s for s in load_history(storage_path, target) if s.task_id != task_id]
    return rows[-1] if rows else None


def record_snapshot(
    storage_path: str,
    snapshot: ChangeSnapshot,
    *,
    keep: int = _MAX_SNAPSHOTS,
) -> ChangeSnapshot:
    """Anlık görüntüyü hedefin geçmişine yazar (atomik; son N kayıt)."""
    rows = [s for s in load_history(storage_path, snapshot.target) if s.task_id != snapshot.task_id]
    rows.append(snapshot)
    rows = rows[-max(1, keep):]
    _atomic_write(
        _history_path(storage_path, snapshot.target),
        {"target": snapshot.target, "snapshots": [r.model_dump() for r in rows]},
    )
    return snapshot
