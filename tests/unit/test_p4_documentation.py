"""[P4 · DENETİM 2026-10-16] Dokümantasyon = kod.

Denetim maddeleri 13/14/15: README/RUNBOOK'da yalnızca **ölçülmüş** yetenekler
"çalışıyor" yazılmalı; ölçülemeyenler "DOĞRULANMADI" bölümünde olmalı.
Ajan listesinde "Lilith: CLI-only" ve holehe'nin gerçek durumu yazılmalı;
RUNBOOK'da 9Router kipinde `dialogue_manager` boşluğu (M-1) ve `sk-pineal`
önek şartı (M-3) yazılmalı.

Bu dosya doküman iddialarını **koda karşı** kilitler: iddia yazılmışsa kod
gerçekten öyle olmalıdır.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
README_TECHNICAL = REPO_ROOT / "README_TECHNICAL.md"
RUNBOOK = REPO_ROOT / "RUNBOOK.md"


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _readme_technical() -> str:
    return README_TECHNICAL.read_text(encoding="utf-8")


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 1. md.13 — ölçülen ↔ DOĞRULANMADI tablosu
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_has_the_measured_vs_unverified_table():
    """README'de iki başlıklı durum tablosu var: ölçülen + DOĞRULANMADI."""
    readme = _readme()
    assert "Durum tablosu" in readme
    assert "ÖLÇÜLEBİLDİ" in readme
    assert "DOĞRULANMADI" in readme


def test_every_unverified_row_states_a_reason():
    """DOĞRULANMADI satırlarının **sebebi** boş bırakılmaz (md.13)."""
    readme = _readme()
    header = readme.index("**DOĞRULANMADI (sebebiyle):**")
    start = readme.index("| Ne | Sebep |", header)
    end = readme.find("\n\n", start)
    block = readme[start:end if end != -1 else start + 4000]
    rows = [ln for ln in block.splitlines() if ln.startswith("|") and "---" not in ln]
    assert len(rows) >= 5, f"DOĞRULANMADI tablosu çok kısa: {len(rows)} satır"
    for row in rows[1:]:  # ilk satır başlıktır
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 2, f"beklenen 2 sütun: {row}"
        assert cells[0], f"boş satır: {row}"
        assert len(cells[1]) > 8, f"sebep yazılmamış: {row}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. md.14 — ajan listesi notları
# ─────────────────────────────────────────────────────────────────────────────
def test_readme_technical_marks_lilith_as_cli_only():
    """Lilith başlığı CLI-only olarak işaretli (md.14)."""
    technical = _readme_technical()
    lilith = technical.split("`LilithGrowthAgent`", 1)[1][:200]
    assert "CLI-ONLY" in lilith


def test_readme_technical_states_the_measured_holehe_state():
    """OSINT bölümü holehe'nin **ölçülmüş** durumunu yazar (md.14).

    Denetimin "holehe ana hattan erişilemez" tespiti P1'le geçersizleşti;
    doküman ya geçerli tespiti ya da ölçülmüş durumu yazmalı — ikisini birden
    değil.
    """
    technical = _readme_technical()
    start = technical.index("#### `osint_investigator`")
    end = technical.find("\n#### ", start + 5)
    osint = technical[start:end if end != -1 else start + 6000]
    assert "holehe" in osint
    assert "DOĞRULANMADI" in osint, "canlı tarama ölçülemediyse bu yazılmalı"
    # Geçersizleşen tespit "düzeltilmiş" olarak anılabilir; ama DÜZELTİLME
    # YAPILMADAN iddia edilirse (aynı cümlede "geçersizleşti" yoksa) yanlıştır.
    sentences = re.split(r"(?<=[.!?])\s+", osint)
    stale = [s for s in sentences if "erişilemez" in s and "geçersizleşti" not in s]
    assert not stale, f"holehe 'erişilemez' iddiası düzeltmesiz yazılmış: {stale}"


def test_readme_does_not_claim_unmeasured_capabilities_work():
    """README "çalışıyor" diye ölçülmemiş bir yeteneği iddia etmemeli."""
    readme = _readme()
    for forbidden in ("maigret çalışıyor", "holehe çalışıyor", "socid çalışıyor"):
        assert forbidden not in readme.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. md.15 — RUNBOOK: M-1 ve M-3
# ─────────────────────────────────────────────────────────────────────────────
def test_runbook_documents_the_sk_pineal_requirement():
    """M-3: 9Router kipinde kasa anahtarının `sk-pineal` önek şartı yazılı."""
    runbook = _runbook()
    assert "sk-pineal" in runbook
    assert "M-3" in runbook


def test_runbook_documents_the_dialogue_manager_gap():
    """M-1: 9Router kipinde `dialogue_manager` kanonik zinciri yok — yazılı."""
    runbook = _runbook()
    assert "dialogue_manager" in runbook
    assert "M-1" in runbook


# ─────────────────────────────────────────────────────────────────────────────
# 4. İDDİALAR KODA KARŞI DOĞRULANIR (belge uydurma yasağı)
# ─────────────────────────────────────────────────────────────────────────────
def test_beacon_service_count_claim_holds():
    """README "12 beacon servisi" diyor → docker-compose gerçekten 12."""
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    count = len(re.findall(r"^  beacon-[a-z0-9-]+:", compose, flags=re.M))
    assert count == 12, f"docker-compose'ta {count} beacon servisi var (README 12 diyor)"


def test_task_agent_count_claim_holds():
    """README/README_TECHNICAL "13 görev ajanı" diyor → yürütücü 13 kaydediyor."""
    source = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            attrs = [t.attr for t in node.targets if isinstance(t, ast.Attribute)]
            if ("agents" in names or "agents" in attrs) and isinstance(node.value, ast.Dict):
                count = len(node.value.keys)
    assert count == 13, f"yürütücü {count} ajan kaydediyor (doküman 13 diyor)"


def test_dialogue_manager_gap_claim_holds():
    """M-1 iddiası: 9Router kanonik zincirlerinde dialogue_manager YOK."""
    from agent_core.services.llm_gateway import LLMGateway

    chains = LLMGateway.NINEROUTER_AGENT_CHAINS
    assert "dialogue_manager" not in chains
    assert len(chains) == 20, f"kanonik zincir sayısı {len(chains)} (RUNBOOK 20 diyor)"


def test_sk_pineal_condition_claim_holds():
    """M-3 iddiası: `/api/vault` 9Router anahtarında `sk-pineal` öneki arar."""
    source = (REPO_ROOT / "backend" / "api.py").read_text(encoding="utf-8")
    assert '"20128" in os.getenv("OPENROUTER_BASE_URL"' in source
    assert 'startswith("sk-pineal")' in source


def test_holehe_is_reachable_from_the_main_line():
    """P4 ölçümü: hedefte e-posta varsa holehe yeteneği çağrılır.

    Denetimin "holehe ana hattan erişilemez" tespiti P1'deki kablo
    düzeltmesiyle geçersizleşti: e-posta biyografiden çıkarılır ve
    `_apply_email_scan` çağrılır.
    """
    source = (REPO_ROOT / "agent_core" / "agents" / "osint_investigator.py").read_text(
        encoding="utf-8"
    )
    assert "_extract_candidate_emails" in source
    assert 'if profile.connected_emails:' in source
    assert '"sensor.identity.holehe"' in source
