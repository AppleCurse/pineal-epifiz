"""Yaprak kasa kapısı (agent_core.services.vault_gate) sözleşmesi.

[AUDIT 2026-10-08 · E-GÖZ2-3] Tüzük Md.4'ün ikinci savunması: API sınırındaki
``_require_vault_open`` atlanırsa (yeni iç çağrı yolu, MCP, worker) scraper/OSINT
yaprakları KENDİ egress'lerinden önce kasayı denetler ve kilitliyse çıkmaz.

Kilitlenen davranışlar:
  1. Açık parametre (``unlocked=``) her zaman önceliklidir (oda-bazlı karar).
  2. Override (``mark_vault_unlocked``) ikinci sıradadır (süreç-içi karar).
  3. Dosya kasası: VARLIK değil, GERÇEK anahtar malzemesi açar.
  4. Hiçbir kaynak yoksa KİLİTLİ (fail-closed) — VaultLockedError fırlar.
  5. Yapraklar kapıdan geçer: instagram_ghost.scrape_async kilitliyse
     VaultLockedError; holehe scan_email kilitliyse ``reason="vault_locked"``.
"""

from __future__ import annotations

import json

import pytest

from agent_core.services import vault_gate
from agent_core.services.vault_gate import VaultLockedError


@pytest.fixture(autouse=True)
def _reset_override():
    vault_gate.mark_vault_unlocked(None)
    yield
    vault_gate.mark_vault_unlocked(None)


# ─────────────────────────────────────────────────────────────────────────
# 1) Açık parametre önceliklidir
# ─────────────────────────────────────────────────────────────────────────

def test_explicit_unlocked_true_passes_even_when_override_locked():
    vault_gate.mark_vault_unlocked(False)
    status = vault_gate.require_vault_open("test.source", unlocked=True)
    assert status["locked"] is False
    assert status["source"] == "caller"


def test_explicit_unlocked_false_raises_even_when_override_open():
    vault_gate.mark_vault_unlocked(True)
    with pytest.raises(VaultLockedError, match="KASA KİLİTLİ"):
        vault_gate.require_vault_open("test.source", unlocked=False)


# ─────────────────────────────────────────────────────────────────────────
# 2) Override ikinci sıradadır
# ─────────────────────────────────────────────────────────────────────────

def test_override_decides_when_no_explicit_param():
    vault_gate.mark_vault_unlocked(True)
    assert vault_gate.get_vault_status() == {"locked": False, "source": "override"}
    vault_gate.mark_vault_unlocked(False)
    with pytest.raises(VaultLockedError):
        vault_gate.require_vault_open("test.source")


# ─────────────────────────────────────────────────────────────────────────
# 3) Dosya kasası: varlık değil, ANAHTAR MALZEMESİ açar
# ─────────────────────────────────────────────────────────────────────────

def test_file_vault_needs_real_key_material(tmp_path, monkeypatch):
    vault_file = tmp_path / "vault.json"
    monkeypatch.setattr(vault_gate, "VAULT_FILE", str(vault_file))

    # Dosya yok → kilitli (fail-closed).
    assert vault_gate.get_vault_status()["locked"] is True

    # Bomboş dosya / yer tutucu → kilitli (varlık yetki değildir).
    vault_file.write_text(json.dumps({"providers": {}}), encoding="utf-8")
    assert vault_gate.get_vault_status()["locked"] is True
    vault_file.write_text(
        json.dumps({"providers": {"gemini": {"api_key": "PLACEHOLDER"}}}),
        encoding="utf-8",
    )
    assert vault_gate.get_vault_status()["locked"] is True

    # Gerçek anahtar malzemesi → açık.
    vault_file.write_text(
        json.dumps({"providers": {"gemini": {"api_key": "sk-gercek-anahtar-123456"}}}),
        encoding="utf-8",
    )
    status = vault_gate.get_vault_status()
    assert status == {"locked": False, "source": "file_vault"}


def test_unreadable_vault_file_fails_closed(tmp_path, monkeypatch):
    vault_file = tmp_path / "vault.json"
    vault_file.write_text("{bozuk json", encoding="utf-8")
    monkeypatch.setattr(vault_gate, "VAULT_FILE", str(vault_file))
    # Okunamayan dosya = dar taraf (kilitli), sessiz açık varsayılmaz.
    assert vault_gate.get_vault_status()["locked"] is True


# ─────────────────────────────────────────────────────────────────────────
# 4) Hiçbir kaynak yoksa kilitli (fail-closed)
# ─────────────────────────────────────────────────────────────────────────

def test_no_source_means_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(vault_gate, "VAULT_FILE", str(tmp_path / "yok.json"))
    with pytest.raises(VaultLockedError):
        vault_gate.require_vault_open("test.source")


# ─────────────────────────────────────────────────────────────────────────
# 5) Yapraklar kapıdan geçer (gerçek modül çağrıları)
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_instagram_ghost_blocked_when_vault_locked():
    """Kilitliyse ilk egress (page.goto) öncesi VaultLockedError — sayfa mock'u bile."""
    from agent_core.scraper.instagram_ghost import InstagramGhostScraper

    class _FakePage:
        async def goto(self, *args, **kwargs):  # egress asla olmamalı
            raise AssertionError("kasa kilitliyken egress olmamalı")

    scraper = InstagramGhostScraper()
    with pytest.raises(VaultLockedError, match="KASA KİLİTLİ"):
        await scraper.scrape_async("hedef", playwright_page=_FakePage())


@pytest.mark.asyncio
async def test_holehe_reports_vault_locked_instead_of_scanning():
    """holehe dürüst-sonuç idiomu: kilitliyse available=False + vault_locked."""
    from agent_core.services.holehe_scanner import scan_email

    result = await scan_email("ornek@example.com", vault_unlocked=False)
    assert result.available is False
    assert result.reason == "vault_locked"


@pytest.mark.asyncio
async def test_instagram_ghost_passes_when_vault_open():
    """Açık kararla kapı geçilir; page yoksa beklenen ISE (kapı değil) fırlar."""
    from agent_core.scraper.instagram_ghost import (
        InsufficientEvidenceError,
        InstagramGhostScraper,
    )

    scraper = InstagramGhostScraper()
    with pytest.raises(InsufficientEvidenceError, match="Playwright page verilmedi"):
        await scraper.scrape_async("hedef", playwright_page=None, vault_unlocked=True)


def test_browser_session_reexports_the_same_exception():
    """Tek exception sınıfı: browser_session ve vault_gate AYNI sınıfı paylaşır."""
    from agent_core.services.browser_session import VaultLockedError as BrowserVaultLockedError

    assert BrowserVaultLockedError is VaultLockedError
