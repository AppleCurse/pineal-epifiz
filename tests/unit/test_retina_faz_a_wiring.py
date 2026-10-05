"""FAZ A · RETİNA (wiring) — omurganın ÜRETİM yoluna bağlandığının kanıtı.

A1 · `platform_registry.scrape_x` X'i omurgadan kazır; kanıt yoksa
     InsufficientEvidenceError (profil UYDURULMAZ).
A2 · X profili GERÇEK zaman damgaları taşır ve ölçülmeyen alanları `None`
     bırakır (eski yolun uydurma 150 takipçisi yoktur).
A3 · Politika durumu tek yerden üretilir (`capabilities.state`); kasa kapalı
     hiçbir yetenek koşmaz.
A4 · Kasa kapalıyken public-web araştırması da metin çekemez.
"""

from __future__ import annotations

import pytest

from agent_core.capabilities.base import CapabilityResult, make_evidence
from agent_core.capabilities.state import (
    MANAGED_GATE_FLAGS,
    enabled_flags,
    parse_bool,
    policy_state,
)
from agent_core.services.platform_registry import (
    extract_x_username,
    scrape_x,
    x_target_profile_update,
)


# ------------------------------------------------------------ A1 · X omurgası
def test_x_username_extracted_only_from_real_profile_url():
    assert extract_x_username("https://x.com/hedef") == "hedef"
    assert extract_x_username("https://x.com/home") == ""


@pytest.mark.asyncio
async def test_scrape_x_rejects_non_profile_url_instead_of_guessing():
    from agent_core.scraper.instagram_ghost import InsufficientEvidenceError

    with pytest.raises(InsufficientEvidenceError):
        await scrape_x("https://x.com/home")


@pytest.mark.asyncio
async def test_scrape_x_halts_when_sensor_produces_no_evidence(monkeypatch):
    """Yetenek reddedilirse (kasa/kapı/çocuk kilidi) profil UYDURULMAZ."""
    from agent_core.scraper.instagram_ghost import InsufficientEvidenceError
    import agent_core.capabilities as caps

    async def _denied(cap_id, ctx, *, state=None, registry=None, emit=None):
        return CapabilityResult(
            capability_id=cap_id,
            available=False,
            unavailable_reason="policy:vault_locked",
            denied_by="vault",
        )

    monkeypatch.setattr(caps, "run_capability", _denied)
    with pytest.raises(InsufficientEvidenceError, match="policy:vault_locked"):
        await scrape_x("https://x.com/hedef")


@pytest.mark.asyncio
async def test_scrape_x_builds_profile_from_real_series(monkeypatch):
    """Gerçek akış → gerçek zaman damgaları; ölçülmeyen alan None kalır."""
    import agent_core.capabilities as caps

    series = [
        {
            "created_at": "2026-10-01T22:30:00+00:00",
            "text": "gece paylaşımı",
            "url": "https://x.com/hedef/status/1",
            "like_count": 3,
            "reply_count": 1,
            "retweet_count": 0,
            "quote_count": 0,
        },
        {"created_at": "", "text": "   ", "url": "", "like_count": 0},
    ]

    async def _ok(cap_id, ctx, *, state=None, registry=None, emit=None):
        item = make_evidence(
            content="gece paylaşımı",
            source_engine="twscrape",
            provenance_refs=["https://x.com/hedef/status/1"],
        )
        return CapabilityResult(
            capability_id=cap_id,
            available=True,
            items=(item,),
            payload={"platform": "x", "username": "hedef", "series": series},
        )

    monkeypatch.setattr(caps, "run_capability", _ok)
    profile = await scrape_x("https://x.com/hedef")

    assert profile["platform"] == "x"
    assert profile["posts"] == ["gece paylaşımı"]        # boş metin düşürüldü
    assert profile["post_times"] == ["2026-10-01T22:30:00+00:00"]
    assert profile["followers"] is None                   # uydurma sayı YOK
    assert profile["following"] is None
    assert profile["bio"] == ""                           # snippet biyografi değil
    assert profile["posts_meta"][0]["like_count"] == 3


def test_x_target_profile_update_drops_empty_posts():
    profile = x_target_profile_update("hedef", [{"text": "", "created_at": None}])
    assert profile["posts"] == []
    assert profile["post_times"] == []
    assert profile["platform"] == "x"


# ------------------------------------------------- A3 · politika durumu (tek yer)
def test_all_managed_gate_flags_default_closed():
    flags = enabled_flags({})
    assert set(flags) == set(MANAGED_GATE_FLAGS)
    assert all(value is False for value in flags.values()), "varsayılan: KAPALI"


def test_enabled_flags_reads_truthy_values():
    flags = enabled_flags({"ENABLE_X_SENSOR": "true", "ENABLE_SEARXNG": "1"})
    assert flags["ENABLE_X_SENSOR"] is True
    assert flags["ENABLE_SEARXNG"] is True
    assert flags["ENABLE_MAIGRET"] is False


def test_parse_bool_is_strict_and_defaults_narrow():
    assert parse_bool("On") is True
    assert parse_bool("maybe") is False
    assert parse_bool(None, default=True) is True


def test_policy_state_marks_unknown_rate_as_unknown():
    """Hız durumu bilinmiyorsa `rate_ok=None` kalır → 'rate' kapısı RET verir."""
    state = policy_state(vault_locked=True)
    assert state.vault_locked is True
    assert state.rate_ok is None
    assert state.enabled_flags == enabled_flags()


# --------------------------------------------- A4 · kasa kapalı: metin çekilmez
@pytest.mark.asyncio
async def test_vault_lock_blocks_web_extraction_in_research(monkeypatch):
    """Kasa kilitliyken omurga hiçbir kademeyi denemez (dış dünya yok)."""
    from agent_core.services import crawl_enricher
    from backend.api import _run_public_web_research
    from tests.unit.test_crawl_enricher import _engine

    async def _must_not_run(url, *a, **kw):  # pragma: no cover - çağrılırsa test düşer
        raise AssertionError("kasa kapalıyken kazıma çağrıldı")

    monkeypatch.setattr(crawl_enricher, "fetch_readable", _must_not_run)
    monkeypatch.setenv("ENABLE_CRAWL4AI", "true")
    # SSRF guard'ı DNS'e bakar; hermetik testte ağ yok sayılır → tek engel KASA.
    from agent_core.capabilities import adapters_web

    monkeypatch.setattr(adapters_web, "is_safe_url", lambda url: True)

    research = await _run_public_web_research(
        "https://x.com/alper",
        _engine("https://blog.example.com/alper"),
        client_id="locked-default",
    )
    assert research["status"] == "ok"
    assert all("crawl" not in m for m in research["results"])
