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


# ============ A3 · Agent-Reach: son kademe + X'in ikinci okuma yolu ============
@pytest.mark.asyncio
async def test_agent_reach_is_the_last_resort_tier(monkeypatch):
    """Üç çıkarıcı da alamazsa SON kademe agent-reach devreye girer."""
    from agent_core.capabilities.runner import CapabilityRunner
    from agent_core.capabilities.adapters_web import extract_web_text

    calls: list[str] = []

    async def _fake(self, cap_id, ctx, *, state=None):
        calls.append(cap_id)
        if cap_id != "sensor.web.agent_reach":
            return CapabilityResult(
                capability_id=cap_id, available=False, unavailable_reason="empty_text"
            )
        item = make_evidence(
            content="agent-reach metni",
            source_engine="agent_reach",
            provenance_refs=[ctx.subject],
        )
        return CapabilityResult(capability_id=cap_id, available=True, items=(item,))

    monkeypatch.setattr(CapabilityRunner, "run", _fake)
    result = await extract_web_text("https://example.com/x")
    assert result.ok is True
    assert result.capability_id == "sensor.web.agent_reach"
    assert calls[-1] == "sensor.web.agent_reach"   # en son denenen
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_x_falls_back_to_agent_reach_without_faking_timestamps(monkeypatch):
    """twscrape yoksa X büsbütün kaybolmaz; ama sahte saat de ÜRETİLMEZ."""
    import agent_core.capabilities as caps

    async def _fake(cap_id, ctx, *, state=None, registry=None, emit=None):
        if cap_id == "sensor.x.twscrape":
            return CapabilityResult(
                capability_id=cap_id,
                available=False,
                unavailable_reason="gate_disabled:ENABLE_X_SENSOR",
            )
        item = make_evidence(
            content="X profilinden okunan genel metin",
            source_engine="agent_reach",
            provenance_refs=[ctx.subject],
        )
        return CapabilityResult(capability_id=cap_id, available=True, items=(item,))

    monkeypatch.setattr(caps, "run_capability", _fake)
    profile = await scrape_x("https://x.com/hedef")

    assert profile["sensor"] == "agent_reach"
    assert profile["posts"] == ["X profilinden okunan genel metin"]
    assert profile["post_times"] == [""]      # uydurma zaman damgası YOK
    assert profile["followers"] is None
    assert "ikinci yol" in profile["sensor_note"]


# ===================== A4 · SearXNG: ücretsiz arama yedeği =====================
def test_searxng_stays_out_unless_operator_opens_the_gate(monkeypatch):
    from agent_core.services.search_engine import SearchEngine

    monkeypatch.delenv("ENABLE_SEARXNG", raising=False)
    monkeypatch.delenv("SEARXNG_BASE_URL", raising=False)
    assert SearchEngine()._searxng_enabled() is False

    monkeypatch.setenv("ENABLE_SEARXNG", "true")
    assert SearchEngine()._searxng_enabled() is False  # URL yok → kapalı

    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    assert SearchEngine()._searxng_enabled() is True


@pytest.mark.asyncio
async def test_searxng_results_join_search_as_free_fallback(monkeypatch):
    """Anahtar yokken SearXNG devreye girer; bulgular `provider: searxng`."""
    import agent_core.capabilities as caps
    from agent_core.services.search_engine import SearchEngine

    seen: dict = {}

    async def _fake(cap_id, ctx, *, state=None, registry=None, emit=None):
        seen["cap_id"] = cap_id
        seen["query"] = ctx.subject
        seen["vault_locked"] = state.vault_locked
        item = make_evidence(
            content="arama bulgusu",
            source_engine="searxng",
            provenance_refs=["https://kaynak.test/1"],
        )
        return CapabilityResult(capability_id=cap_id, available=True, items=(item,))

    monkeypatch.setattr(caps, "run_capability", _fake)
    monkeypatch.setenv("ENABLE_SEARXNG", "true")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")

    engine = SearchEngine()
    engine.set_policy({"vault_locked": False})

    async def _no_dd(self, query, num_results, client=None):
        return []

    monkeypatch.setattr(SearchEngine, "_search_duckduckgo", _no_dd)
    outcome = await engine.search("hedef kişi", num_results=3)
    assert outcome.available is True
    assert [r.provider for r in outcome.results] == ["searxng"]
    assert seen["cap_id"] == "sensor.search.searxng"
    assert seen["query"] == "hedef kişi"
    assert seen["vault_locked"] is False  # kasa gerçeği omurgaya TAŞINDI


@pytest.mark.asyncio
async def test_searxng_blocked_when_vault_locked(monkeypatch):
    """Kasa kapalı: omurga yeteneği koşmaz → dışarı HTTP isteği ÇIKMAZ.

    Koşturucu MOCKLANMAZ (mock kapıyı atlardı); bunun yerine HTTP istemcisi
    "patlayan" bir istemciyle değiştirilir: istek çıkarsa test düşer.
    """
    from agent_core.capabilities import adapters_sensors
    from agent_core.services.search_engine import SearchEngine

    class _BoomClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise AssertionError("kasa kapalıyken dışarı HTTP isteği çıktı")

    monkeypatch.setattr(adapters_sensors.httpx, "AsyncClient", _BoomClient)
    monkeypatch.setenv("ENABLE_SEARXNG", "true")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")

    engine = SearchEngine()
    engine.set_policy({"vault_locked": True})

    async def _no_dd(self, query, num_results, client=None):
        return []

    monkeypatch.setattr(SearchEngine, "_search_duckduckgo", _no_dd)
    outcome = await engine.search("hedef", num_results=3)
    assert outcome.results == []
    assert outcome.status == "NO_RESULTS"


@pytest.mark.asyncio
async def test_searxng_path_is_live_when_vault_open(monkeypatch):
    """Kasa açık: aynı düzenekte kapı GEÇİLİR, HTTP yolu canlıdır.

    Kasa kapalı testin aynısı, tek fark `vault_locked=False`: istek patlamalı
    (yani yol gerçekten açıldı). Kilit ile açık hal arasındaki TEK fark kasa.
    """
    from agent_core.capabilities import adapters_sensors
    from agent_core.services.search_engine import SearchEngine

    class _BoomClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise AssertionError("http_request_made")

    monkeypatch.setattr(adapters_sensors.httpx, "AsyncClient", _BoomClient)
    monkeypatch.setenv("ENABLE_SEARXNG", "true")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")

    engine = SearchEngine()
    engine.set_policy({"vault_locked": False})

    async def _no_dd(self, query, num_results, client=None):
        return []

    monkeypatch.setattr(SearchEngine, "_search_duckduckgo", _no_dd)
    outcome = await engine.search("hedef", num_results=3)
    # Yetenek koştu ama servis yok -> dürüst "yok", uydurma bulgu değil.
    assert outcome.results == []
    assert outcome.status == "NO_RESULTS"


# ==================== A7 · Scrapling: kırılganlık kademesi ====================
def test_scrapling_is_third_tier_and_gated():
    from agent_core.capabilities.adapters_web import ScraplingCapability
    from agent_core.capabilities.adapters_web import WEB_EXTRACTION_ORDER

    assert WEB_EXTRACTION_ORDER[2] == "extractor.web.scrapling"
    cap = ScraplingCapability()
    assert "ENABLE_SCRAPLING" in cap.gates
    assert cap.license == "BSD-3-Clause"
