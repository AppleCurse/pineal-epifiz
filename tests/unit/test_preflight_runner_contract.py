"""9Router preflight İŞ AKIŞI sözleşmesi — koşmayan kapı kapı değildir.

[2026-10-24 · BULUNAN KUSUR] `.github/workflows/preflight.yml` her 6 saatte bir
`schedule` ile tetikleniyordu ve `runs-on: self-hosted` istiyordu. Depoda
kayıtlı self-hosted runner YOK: 2026-10-23 03:04 · 10:55 · 16:20 UTC (ve 10-24)
koşuları **hâlâ `queued`**, tek adım bile çalışmadı. Yani "preflight
doğrulaması" adı taşıyan bir kapı, hiçbir şeyi doğrulamadan kuyrukta bekliyordu
— ne yeşil ne kırmızı ürettiği için görünmez bir sahte güvenceydi.

Bu dosya üç şeyi kilitler:
  1. İş AKIŞI artık zamanlanmış tetikleyici TAŞIMAZ (elle + runner kaydıyla).
  2. Runner gereksinimi ve concurrency/timeout açıkça tanımlı.
  3. Betik, hub'a ULAŞAMADIĞINDA **fail-closed** (exit != 0) davranır ve
     depodaki izlenen kanıt dosyasını kendiliğinden EZMEZ.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "preflight.yml"
SCRIPT = ROOT / "scripts" / "preflight_9router.py"
EVIDENCE = ROOT / "reports" / "9router_preflight_latest.json"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    # YAML `on:` anahtarını bazı sürümlerde True olarak ayrıştırır.
    return doc.get("on") or doc.get(True) or {}


def test_preflight_workflow_is_not_scheduled():
    """Zamanlanmış tetik YOK: runner yokken her 6 saatte bir kuyruk birikiyordu."""
    triggers = _triggers(_workflow())
    assert "schedule" not in triggers, (
        "preflight zamanlanmış tetik taşıyor; runner yoksa her koşu sonsuza kadar "
        "kuyrukta kalır ve hiçbir şey doğrulamaz"
    )
    assert "workflow_dispatch" in triggers, "elle koşturma yolu korunmalı"


def test_preflight_workflow_declares_the_runner_requirement():
    """İş, hub'ın yanındaki self-hosted runner'ı ister; sınırlar tanımlı."""
    job = _workflow()["jobs"]["preflight-probe"]
    runner = job["runs-on"]
    runner = runner if isinstance(runner, list) else [runner]
    assert "self-hosted" in runner, (
        f"9Router hub'ı 127.0.0.1'de; barındırılan runner oraya ulaşamaz: {runner}"
    )
    assert job.get("timeout-minutes"), "asili kalan iş için timeout tanımlı olmalı"
    doc = _workflow()
    assert doc.get("concurrency", {}).get("group"), (
        "art arda elle tetiklemeler birikmesin: concurrency grubu yok"
    )


def test_preflight_fails_closed_and_does_not_overwrite_tracked_evidence(tmp_path):
    """Hub erişilemezse: exit != 0 VE depodaki kanıt dosyası DEĞİŞMEZ.

    Gerçek koşu (taklit yok): betik, kapalı bir porta yönlendirilir; bağlantı
    reddedilir → kapı kırmızı olmalı. Rapor yolu ortam değişkeniyle geçici
    dizine çekilir; bu olmadan betik depodaki izlenen kanıt dosyasını eziyordu.
    """
    before = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() if EVIDENCE.exists() else None
    report = tmp_path / "preflight.json"
    env = {
        **os.environ,
        "NINEROUTER_BASE_URL": "http://127.0.0.1:9/v1",  # hiç dinlemeyen port
        "NINEROUTER_PREFLIGHT_REPORT": str(report),
        "NINEROUTER_API_KEY": "test-key",
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        cwd=str(ROOT),
    )
    assert result.returncode != 0, (
        "hub erişilemezken betik YEŞİL döndü — kapı fail-closed değil:\n"
        + result.stdout[-1500:]
    )
    assert "PREFLIGHT BAŞARISIZ" in result.stdout
    assert report.exists(), "rapor, ortam değişkeninin gösterdiği yola yazılmalı"
    after = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() if EVIDENCE.exists() else None
    assert after == before, "betik depodaki izlenen kanıt dosyasını ezdi"
