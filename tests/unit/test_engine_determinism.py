"""Yedi motor determinizmi — gerçek çıktı karşılaştırmasıyla kilitlenir.

[RÖNTGEN 2026-09-23] Ölçülen kusurlar (aynı girdi, farklı koşular):

1. `GRAVITY`: kuyular `set(...)` yinelemesiyle dolduruluyordu. Python'da küme
   yineleme sırası hash rastgelelemesine (PYTHONHASHSEED) bağlıdır; eşit
   pull/mass'lı kuyularda sıralama bu giriş sırasına düştüğü için
   `dominant_attractor` AYNI VERİYLE koşudan koşuya değişiyordu
   (ölçüldü: 'uzun' → 'düşündüm' → 'hakkında'). KEY matrisi `wells[0]`'ı
   kullandığı için kusur senteze de taşıyordu.
2. `SEISMOS`: `event_id` `uuid.uuid4()` ile üretiliyordu — deterministik diye
   beyan edilen bir motorda her koşuda farklı kimlik. Kanıt mühürleri (SHA-256)
   ve yeniden-üretim karşılaştırmaları bu yüzden anlamsızdı.
3. `VOID`: `hits` listesi küme yinelemesinden geliyordu (çıktıya bugün
   yansımıyor ama `hits[:8]` kırpması sıraya bağımlıydı).

Bu dosya determinizmi "kod okumasıyla" değil, aynı girdiyi farklı süreçlerde
(farklı PYTHONHASHSEED ile) çalıştırıp kanonik çıktıyı karşılaştırarak kilitler.
Duvar saati alanı (`computed_at`) karşılaştırmadan çıkarılır: o alan tanımı
gereği koşuya özgüdür, determinizm ihlali değildir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_core.engines.pillar_orchestrator import PillarOrchestrator

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = REPO_ROOT / "agent_core" / "engines"

RUNNER = r"""
import asyncio, importlib.util, sys
test_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("engine_determinism_probe", test_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(mod.canonical_bundle(asyncio.run(mod.build_bundle())))
"""


# --------------------------------------------------------------------------- #
# girdi + kanonikleştirme (alt süreç de aynı fonksiyonları kullanır)
# --------------------------------------------------------------------------- #
def sample_data() -> dict:
    """Yedi motoru da besleyen, kıyaslanabilir zenginlikte sabit girdi."""
    base = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    times: list[datetime] = []
    for i in range(10):
        times.append(base + timedelta(hours=8 * i))
    # 12 günlük sessizlik boşluğu -> SEISMOS SILENCE_GAP
    times.append(times[-1] + timedelta(days=12))
    for i in range(1, 8):
        times.append(times[-1] + timedelta(hours=8 * i))

    corpus = (
        "siyaset seçim aile annem babam kariyer ofis para yatırım sanat müzik tasarım "
        "seyahat tatil aşk sevgili sağlık spor uyku inanç dua kavga iş plan proje "
    )
    posts = []
    for i in range(len(times)):
        if i < 10:
            posts.append(f"bugün harika bir gündü uzun uzun yazdım düşündüm gerçekten {corpus.strip()}")
        else:
            posts.append(f"çok yorgunum bitkin ve stresliyim kötü bir gündü bıktım artık uzun uzun düşündüm {corpus.strip()}")
    meta = [{"like_count": 8 + i * 3, "comment_count": i % 5, "created_at": t.isoformat()}
            for i, t in enumerate(times)]

    return {
        "target_profile": {
            "platform": "instagram",
            "bio": corpus * 2,
            "posts": posts,
            "post_times": [t.isoformat() for t in times],
            "posts_meta": meta,
            "interests": ["sanat", "siyaset"],
        }
    }


def _strip_clock(node):
    if isinstance(node, dict):
        return {k: _strip_clock(v) for k, v in node.items() if k != "computed_at"}
    if isinstance(node, list):
        return [_strip_clock(x) for x in node]
    return node


def canonical_bundle(bundle) -> str:
    """Duvar saati dışarıda bırakılmış, anahtarları sıralı kanonik JSON."""
    return json.dumps(_strip_clock(bundle), sort_keys=True, ensure_ascii=False, default=str)


async def build_bundle() -> dict:
    return await PillarOrchestrator().run(sample_data())


def _run_in_subprocess(seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    proc = subprocess.run(
        [sys.executable, "-c", RUNNER, str(Path(__file__).resolve())],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    assert proc.returncode == 0, f"PYTHONHASHSEED={seed} koşusu çöktü: {proc.stderr[-1500:]}"
    return proc.stdout.strip()


# --------------------------------------------------------------------------- #
# testler
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_same_input_produces_identical_bundle_in_process():
    first = canonical_bundle(await build_bundle())
    second = canonical_bundle(await build_bundle())
    assert first == second


def test_bundle_identical_across_python_hash_seeds():
    """Küme/dict yineleme sırası çıktıyı DEĞİŞTİREMEZ."""
    outputs = {seed: _run_in_subprocess(seed) for seed in ("0", "1", "42")}
    unique = set(outputs.values())
    assert len(unique) == 1, (
        "Motorlar hash tohumuna göre farklı çıktı üretti: "
        + json.dumps({s: o[:400] for s, o in outputs.items()}, ensure_ascii=False, indent=2)
    )


def test_gravity_dominant_attractor_is_stable():
    """`dominant_attractor` koşular arasında değişmez (eski kusur)."""
    outputs = [_run_in_subprocess(seed) for seed in ("0", "7")]
    dominants = []
    for blob in outputs:
        gravity = json.loads(blob)["gravity_map"]
        dominants.append(gravity.get("dominant_attractor"))
    assert len(set(dominants)) == 1, f"dominant_attractor değişti: {dominants}"
    assert dominants[0], "örnek girdiyle en az bir kuyu beklenir"


def test_seismos_event_ids_are_stable_not_random():
    """`event_id` rastgele değil, girdiden türetilmiş olmalı."""
    blobs = [_run_in_subprocess(seed) for seed in ("0", "13")]
    ids = [sorted(e["event_id"] for e in json.loads(b)["seismos_events"]["events"]) for b in blobs]
    assert ids[0] == ids[1], f"event_id'ler koşular arasında değişti: {ids}"
    assert ids[0], "örnek girdiyle en az bir sismik olay beklenir"
    assert all(i.startswith("sez_") for i in ids[0])


@pytest.mark.parametrize(
    "engine_file",
    [
        "frequency_engine.py",
        "seismos_engine.py",
        "void_engine.py",
        "strata_engine.py",
        "gravity_engine.py",
        "pulse_engine.py",
        "key_engine.py",
    ],
)
def test_engines_import_no_randomness_sources(engine_file: str):
    """Motorlar LLM de rastgelelik de içermez: uuid/random/time-saat yok."""
    source = (ENGINE_DIR / engine_file).read_text(encoding="utf-8")
    code_lines = [ln for ln in source.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    for forbidden in ("import uuid", "uuid4", "import random", "random.", "np.random", "time.time()", "datetime.now("):
        assert forbidden not in code, (
            f"{engine_file} determinizm ihlali: '{forbidden}' bulundu. Yedi motor "
            "LLM'siz ve tekrar-üretilebilir olmak zorundadır; rastgele kimlik/skor "
            "üretimi kanıt mühürlerini (SHA-256) anlamsızlaştırır."
        )


def test_engines_do_not_call_llm_gateway():
    """Determinizm beyanı: motorlar LLM hattına bağlanamaz."""
    for path in ENGINE_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "llm_gateway" not in source and "generate_text" not in source, (
            f"{path.name} LLM hattına dokunuyor — motor determinizmi ihlali"
        )
