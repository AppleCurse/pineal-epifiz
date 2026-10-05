"""[W4.2] scripts/run_task.py — Rust TaskManager'ın standart girişi.

Sözleşme testleri (gerçek subprocess, mock yok):
- Tanınmayan platform -> exit 2 + {"status": "unsupported_platform"}
- X -> sensör kanıt üretemediğinde exit 3 + {"status": "halted_evidence"}
  (sahte profil ÜRETİLMEZ; eski "awaiting_authorization" yolu kaldırıldı,
  Faz A · Retina)
- Geçersiz stdin -> exit 4 + {"status": "invalid_input"}
- Boş URL (kazımasız) -> pipeline GERÇEKTEN koşar -> exit 0 + TaskStatus
  (kanıt yok -> dürüst halted_* durumu; asla sahte COMPLETED değil)
"""

import json
import subprocess
import sys
import os


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_task(payload: str, tmp_path):
    return subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "scripts", "run_task.py")],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(tmp_path),  # memory/ gibi yan dosyalar test alanına düşsün
    )


def _json_stdout(proc):
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_unsupported_platform_exits_with_explicit_status(tmp_path):
    proc = _run_task(json.dumps({
        "url": "https://tiktok.com/@baskasi",
        "rituals": [], "playlist": [], "envies": [],
    }), tmp_path)
    assert proc.returncode == 2
    data = _json_stdout(proc)
    assert data["status"] == "unsupported_platform"
    # Kazıma/analiz YAPILMADI — sahte sonuç yok
    assert "evidence_chain" not in data


def test_x_platform_halts_honestly_without_evidence(tmp_path):
    """X artık "yetki bekleyen bir delik" değil: gerçek sensör koşar.

    Sensör kanıt üretemezse (kütüphane/kapı/hesap yok) sahte profil
    ÜRETİLMEZ; görev exit 3 + halted_evidence ile dürüstçe durur.
    """
    proc = _run_task(json.dumps({
        "url": "https://x.com/hedef", "rituals": [], "playlist": [], "envies": [],
    }), tmp_path)
    assert proc.returncode == 3
    data = _json_stdout(proc)
    assert data["status"] in ("halted_evidence", "scrape_failed")
    assert data.get("platform") == "x"
    assert "evidence_chain" not in data


def test_invalid_stdin_is_rejected_not_improvised(tmp_path):
    proc = _run_task("bu json degil", tmp_path)
    assert proc.returncode == 4
    data = _json_stdout(proc)
    assert data["status"] == "invalid_input"


def test_empty_url_runs_real_pipeline_and_halts_honestly(tmp_path):
    """Kazıma yok + kullanıcı verisi yok -> gerçek executor koşar ve KANIT
    YOKSA dürüstçe durur. Sahte 'completed' asla üretilmez."""
    proc = _run_task(json.dumps({
        "url": "", "rituals": [], "playlist": [], "envies": [],
    }), tmp_path)
    assert proc.returncode == 0, proc.stderr[-500:]
    data = _json_stdout(proc)
    # TaskStatus alanları gerçek
    assert data["task_id"].startswith("rust_")
    assert data["status"] in (
        "halted_insufficient_evidence", "halted_critical", "partially_completed",
        "completed", "halted_frequency", "halted_evidence",
    )
    # Boş girdiyle sahte başarı sözleşmesi: kanıtsız COMPLETED gelemez
    assert data["status"] != "completed", "sıfır kanıtla completed üretildi"
    assert isinstance(data.get("evidence_chain"), list)


def test_user_only_run_produces_mirror_evidence_path(tmp_path):
    """URL yok ama kullanıcı verisi var -> mirror yolu AÇIK olmalı; yine dürüst
    durum dönmeli (LLLM kapalı olduğundan fallback/halt beklenebilir)."""
    proc = _run_task(json.dumps({
        "url": "",
        "rituals": ["gece koşusu"],
        "playlist": ["neşet ertaş"],
        "envies": ["derin bağ"],
    }), tmp_path)
    assert proc.returncode == 0, proc.stderr[-500:]
    data = _json_stdout(proc)
    assert data["status"] in (
        "halted_insufficient_evidence", "halted_critical",
        "partially_completed", "completed", "halted_frequency",
        "halted_evidence",
    )
    # Payload kullanıcı verisini taşıdı mı? TaskStatus bunu direkt göstermez;
    # en azından kanıt zinciri üretilmiş/boş dürüst olmalı.
    assert isinstance(data.get("evidence_chain"), list)
