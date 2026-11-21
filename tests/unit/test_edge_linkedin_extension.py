"""LinkedIn uzantısı: çekirdek dürüstlüğü + canlı yük zinciri (2026-11-21).

Ölçülen kusur:
    ``extensions/chrome-linkedin/core.js`` "browser-bağımsız çekirdek" olarak
    YAZILDI ve 2026-11-11 DÜRÜSTLÜK düzeltmelerini taşıyordu (uydurma hedef
    yok, URL kapısı, planAnalysis). Ama manifest yalnız ``content.js``
    yüklediği ve hiçbir dosya core.js'i import etmediği için bu çekirdek
    ÖLÜYDÜ; canlı içerik betiği eski, uyduran davranışla yayında kaldı.
    Ayrıca çekirdeğin testinin adı (``tests/edge/linkedin_extension.mjs``)
    hiç var olmadı — "ölçülebilir" dendi, ölçen olmadı.

    Ek olarak content.js, sunucu kaynaklı metinleri (``g.reason``,
    ``g.machine_note``) ``innerHTML``'e interpolasyonla basıyordu —
    hedef-türevli bir dize linkedin.com bağlamında enjeksiyona dönüşebilirdi.

Bu dosya iki şeyi kilitler:
    1. KAYNAK DÜZEYİNDE: manifest çekirdeği ÖNCE yükler; canlı content.js
       sunucu metnini innerHTML'e VERMEZ ve çekirdekten kopya mantık
       TAŞIMAZ (serverError/REASON tekrar tanımı yok).
    2. DAVRANIŞ: ``node tests/edge/linkedin_extension.mjs`` çekirdeğin
       sözleşmesini gerçekten koşturur (hedef uydurmaz, URL kapısı çalışır,
       boş graf ham sebeple gösterilir).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXT_DIR = REPO_ROOT / "extensions" / "chrome-linkedin"
CONTENT = EXT_DIR / "content.js"
CORE = EXT_DIR / "core.js"
MANIFEST = EXT_DIR / "manifest.json"
EDGE_PROBE = REPO_ROOT / "tests" / "edge" / "linkedin_extension.mjs"


def test_manifest_loads_core_before_content():
    import json

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scripts = None
    for cs in manifest.get("content_scripts", []):
        if "content.js" in cs.get("js", []):
            scripts = cs["js"]
            break
    assert scripts, "content.js hiçbir content_scripts kaydında yok"
    assert scripts.index("core.js") < scripts.index("content.js"), (
        "core.js, content.js'ten ÖNCE yüklenmeli (window.AtlasLinkedInCore)"
    )


def test_live_content_script_uses_shared_core():
    source = CONTENT.read_text(encoding="utf-8")
    assert "window.AtlasLinkedInCore" in source, "content.js çekirdeği kullanmıyor"
    # Kopya mantık YOK: serverError/REASON tablosu content.js'te yeniden tanımlanmaz.
    assert "KASADA" not in source
    assert "KİMLİK REDDEDİLDİ" not in source, "serverError content.js'te tekrar tanımlı"
    assert "no_evidence:" not in source, "REASON_TEXT content.js'te tekrar tanımlı"


def test_core_exposes_global_for_content_script():
    source = CORE.read_text(encoding="utf-8")
    assert "window.AtlasLinkedInCore" in source


def test_live_content_script_never_writes_server_text_as_html():
    source = CONTENT.read_text(encoding="utf-8")
    # Sunucuya ait metinlerin innerHTML'e interpolasyonu yasak:
    for marker in ("atlas-note').innerHTML", 'atlas-note").innerHTML', "innerHTML = `<div><strong>${g"):
        assert marker not in source, f"sunucu metni innerHTML'e gidiyor: {marker}"
    # Sonuç bölgesi metin düğümüyle yazılmalı:
    assert "note.textContent" in source
    assert "nodes.replaceChildren()" in source


def test_live_content_script_has_target_gate_and_honest_fallbacks():
    source = CONTENT.read_text(encoding="utf-8")
    assert "planAnalysis" in source, "istek kurulmadan önce hedef kapısı yok"
    assert "'LinkedIn Profili'" not in source, "uydurma varsayılan hedef adı geri gelmiş"


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node yok")
def test_extension_core_behavior_passes_node_probe():
    result = subprocess.run(
        ["node", str(EDGE_PROBE)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"edge ölçümü başarısız:\n{output}"
    assert "LINKEDIN_EXT_OK" in output
    for scenario in (
        "hedef yoksa istek GÖNDERİLMEZ",
        "ad yoksa hedef yoktur",
        "boş graf + BİLİNMEYEN sebep → ham sebep gösterilir",
    ):
        assert scenario in output
