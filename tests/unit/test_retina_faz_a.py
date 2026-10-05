"""FAZ A · RETİNA — kabul testleri.

Kapsanan iddialar (hepsi ölçülebilir, hiçbiri ağa çıkmaz):

A1 · Temiz metin omurgası: trafilatura → crawl4ai → scrapling **sıralı düşüş**,
     tek arayüz, hepsi aynı EvidenceItem şemasını üretir.
A2 · maigret/socid çıktısı artık **EvidenceTimeline'a mühürlenir** (kanıt zinciri).
A3 · X sensörü (twscrape) kapıları taşır: kasa + hız + ENABLE_X_SENSOR.
A4 · Instagram ikinci kaynak (instagrapi) asla birincil değildir, kimlik bilgisi
     kanıta/telemetriye sızmaz.
A5 · Agent-Reach ve SearXNG: servis yokken dürüst `available=False`; uydurma yok.
A6 · SSRF guard: güvensiz URL hiçbir yetenekte geçmez.
"""

from __future__ import annotations

import re

import pytest

from agent_core.capabilities import (
    CapabilityContext,
    CapabilityRegistry,
    PolicyState,
    bootstrap,
    run_capability,
)
from agent_core.capabilities.adapters_sensors import (
    AgentReachCapability,
    InstagrapiCapability,
    SearXNGCapability,
    XTwscrapeCapability,
)
from agent_core.capabilities.adapters_web import (
    Crawl4AICapability,
    ScraplingCapability,
    TrafilaturaCapability,
    WEB_EXTRACTION_ORDER,
    extract_web_text,
)
from agent_core.capabilities.adapters_osint import MaigretCapability, SocidCapability
from agent_core.capabilities.base import CapabilityResult, make_evidence
from agent_core.capabilities.timeline_bridge import seal_items, seal_results, seal_summary

EVIDENCE_ID_RE = re.compile(r"^ev_[0-9a-f]{20}$")


# ------------------------------------------------- A1 · temiz metin omurgası
def test_default_registry_contains_full_retina_stack():
    reg = CapabilityRegistry()
    bootstrap(reg)
    for cap_id in (
        "extractor.web.trafilatura",
        "extractor.web.crawl4ai",
        "extractor.web.scrapling",
        "sensor.x.twscrape",
        "sensor.ig.instagrapi",
        "sensor.web.agent_reach",
        "sensor.search.searxng",
    ):
        assert reg.has(cap_id), f"{cap_id} kayıtlı değil"


def test_extraction_order_is_single_source_and_starts_with_trafilatura():
    assert WEB_EXTRACTION_ORDER[0] == "extractor.web.trafilatura"
    assert WEB_EXTRACTION_ORDER == (
        "extractor.web.trafilatura",
        "extractor.web.crawl4ai",
        "extractor.web.scrapling",
    )


@pytest.mark.asyncio
async def test_web_spine_falls_back_to_next_extractor():
    """İlk kademe boş dönerse ikinci devralır; kanıt ikinci kademeden gelir."""
    calls: list[str] = []

    class _FakeCapability:
        def __init__(self, cap_id: str, text: str) -> None:
            self.id = cap_id
            self.kind = __import__(
                "agent_core.capabilities.base", fromlist=["x"]
            ).CapabilityKind.EXTRACTOR
            self.license = "MIT"
            self.gates = frozenset()
            self._text = text

        def availability(self):
            from agent_core.capabilities.base import Availability

            return Availability.ok()

        async def run(self, ctx):
            calls.append(self.id)
            if not self._text:
                return CapabilityResult(
                    capability_id=self.id, available=False, unavailable_reason="empty_text"
                )
            item = make_evidence(
                content=self._text,
                source_engine=self.id,
                provenance_refs=[ctx.subject],
                scope={"kind": "web_text"},
            )
            return CapabilityResult(capability_id=self.id, available=True, items=(item,))

    reg = CapabilityRegistry()
    reg.register(_FakeCapability("extractor.web.trafilatura", ""))
    reg.register(_FakeCapability("extractor.web.crawl4ai", "temiz metin"))
    reg.register(_FakeCapability("extractor.web.scrapling", "kullanılmadı"))

    result = await extract_web_text("https://example.com/x", registry=reg)
    assert result.ok is True
    assert result.items[0].source_engine == "extractor.web.crawl4ai"
    assert calls == ["extractor.web.trafilatura", "extractor.web.crawl4ai"]
    assert [a["capability_id"] for a in result.notes["attempts"]] == calls


@pytest.mark.asyncio
async def test_web_spine_reports_reasons_when_all_extractors_fail():
    """Hiçbiri üretemezse: 0 kanıt + tüm denemelerin izi. Uydurma metin yok."""
    from agent_core.capabilities.base import Availability, CapabilityKind

    class _Dead:
        def __init__(self, cap_id: str) -> None:
            self.id = cap_id
            self.kind = CapabilityKind.EXTRACTOR
            self.license = "MIT"
            self.gates = frozenset()

        def availability(self):
            return Availability.unavailable("dependency_missing:x")

        async def run(self, ctx):  # pragma: no cover - hiç çağrılmamalı
            raise AssertionError("kapalı yetenek koşturulmaya çalışıldı")

    reg = CapabilityRegistry()
    for cap_id in WEB_EXTRACTION_ORDER:
        reg.register(_Dead(cap_id))

    result = await extract_web_text("https://example.com/x", registry=reg)
    assert result.ok is False
    assert result.items == ()
    assert result.unavailable_reason == "dependency_missing:x"
    assert len(result.notes["attempts"]) == len(WEB_EXTRACTION_ORDER)


@pytest.mark.asyncio
async def test_extractors_reject_unsafe_url_before_any_network():
    """SSRF guard: güvensiz URL hiçbir kademede ağa çıkmaz."""
    caps = (TrafilaturaCapability(), Crawl4AICapability(), ScraplingCapability())
    for cap in caps:
        result = await cap.run(CapabilityContext(subject="http://127.0.0.1:8000/admin"))
        assert result.available is False, f"{cap.id} güvensiz URL'i geçirdi"
        assert result.items == ()


@pytest.mark.asyncio
async def test_extractors_reject_invalid_scheme():
    cap = TrafilaturaCapability()
    result = await cap.run(CapabilityContext(subject="file:///etc/passwd"))
    assert result.available is False
    assert result.unavailable_reason == "invalid_scheme"


# ------------------------------------------- A2 · maigret/socid kanıt mührü
@pytest.mark.asyncio
async def test_identity_capabilities_seal_into_evidence_timeline(monkeypatch):
    """maigret bulgusu artık profile değil, MÜHÜRLÜ zaman çizelgesine girer."""
    from agent_core.services import maigret_scanner

    class _Hit:
        site = "example"
        url = "https://example.com/hedef"

    class _Scan:
        available = True
        reason = None
        provider = "maigret"
        found_sites = [_Hit(), _Hit()]
        scanned_count = 100
        error_count = 0

    async def _fake(username, **_kw):
        return _Scan()

    monkeypatch.setattr(maigret_scanner, "scan_username", _fake)
    result = await MaigretCapability().run(CapabilityContext(subject="hedef"))

    timeline = seal_results([result])
    assert len(timeline.entries) == 2
    assert all(timeline.entries[i].evidence_id for i in range(2))
    assert timeline.rejected_item_count == 0
    for entry in timeline.entries:
        assert entry.source_engine == "maigret"
        assert "https://example.com/hedef" in entry.provenance_refs


def test_seal_summary_reports_per_capability_state():
    ok = CapabilityResult(
        capability_id="sensor.identity.maigret",
        available=True,
        items=(
            make_evidence(content="bulundu", source_engine="maigret", provenance_refs=["https://a"]),
        ),
    )
    off = CapabilityResult(
        capability_id="extractor.identity.socid",
        available=False,
        unavailable_reason="dependency_missing:socid_extractor",
    )
    summary = seal_summary([ok, off])
    assert summary["sealed_count"] == 1
    assert summary["capabilities"][1]["reason"] == "dependency_missing:socid_extractor"
    assert summary["timeline"].schema_version == "evidence-timeline-v1"


def test_seal_items_rejects_empty_and_keeps_schema():
    timeline = seal_items([])
    assert timeline.entries == []
    assert timeline.schema_version == "evidence-timeline-v1"


# ------------------------------------------------------- A3 · X sensörü
def test_x_sensor_gates(monkeypatch):
    monkeypatch.delenv("ENABLE_X_SENSOR", raising=False)
    assert XTwscrapeCapability().availability().reason == "gate_disabled:ENABLE_X_SENSOR"


def test_x_sensor_carries_vault_and_rate_gates():
    gates = XTwscrapeCapability().gates
    assert {"vault", "rate"} <= gates
    assert "ENABLE_X_SENSOR" in gates


@pytest.mark.asyncio
async def test_x_sensor_requires_rate_state_fail_closed():
    """Hız durumu bilinmiyorsa X sensörü KOŞAMAZ (bilinmeyen kapı = ret)."""
    reg = CapabilityRegistry()
    reg.register(XTwscrapeCapability())
    import os

    old = os.environ.get("ENABLE_X_SENSOR")
    os.environ["ENABLE_X_SENSOR"] = "true"
    try:
        result = await run_capability(
            "sensor.x.twscrape",
            CapabilityContext(subject="hedef"),
            registry=reg,
            state=PolicyState(vault_locked=False),  # rate_ok=None
        )
    finally:
        if old is None:
            os.environ.pop("ENABLE_X_SENSOR", None)
        else:
            os.environ["ENABLE_X_SENSOR"] = old
    assert result.denied_by == "rate"
    assert result.unavailable_reason == "policy:rate_state_missing"
    assert result.items == ()


@pytest.mark.asyncio
async def test_x_sensor_produces_time_series_for_frequency_engine(monkeypatch):
    """X akışı yalnız kanıt değil, Frequency/timing için ZAMAN SERİSİ üretir."""
    import types

    class _Tweet:
        def __init__(self, tid, date, text):
            self.id = tid
            self.date = date
            self.rawContent = text
            self.likeCount = 3
            self.retweetCount = 1
            self.replyCount = 0
            self.quoteCount = 0

    from datetime import datetime, timezone

    d1 = datetime(2026, 10, 1, 22, 30, tzinfo=timezone.utc)
    d2 = datetime(2026, 10, 2, 3, 15, tzinfo=timezone.utc)

    tweets = [_Tweet(1, d1, "gece paylaşımı"), _Tweet(2, d2, "sabah paylaşımı")]

    async def _user_by_login(_username):
        return types.SimpleNamespace(id=42)

    async def _user_tweets(user_id, limit):  # gerçek twscrape: async generator
        for tweet in tweets[:limit]:
            yield tweet

    async def _gather(agen):
        return [tweet async for tweet in agen]

    fake_twscrape = types.SimpleNamespace(
        API=lambda: types.SimpleNamespace(
            user_by_login=_user_by_login,
            user_tweets=_user_tweets,
        ),
        gather=_gather,
    )

    import sys

    monkeypatch.setitem(sys.modules, "twscrape", fake_twscrape)
    monkeypatch.setattr(
        "agent_core.capabilities.adapters_sensors._module_available", lambda _n: True
    )
    monkeypatch.setattr(XTwscrapeCapability, "gates", frozenset())

    result = await XTwscrapeCapability().run(CapabilityContext(subject="hedef", params={"limit": 2}))
    assert result.ok is True
    series = result.payload["series"]
    assert len(series) == 2
    assert series[0]["created_at"] == d1.isoformat()
    assert series[0]["like_count"] == 3
    assert all(EVIDENCE_ID_RE.match(i.evidence_id) for i in result.items)


# ------------------------------------------- A4 · Instagram ikinci kaynak
def test_instagrapi_is_second_source_only(monkeypatch):
    monkeypatch.delenv("ENABLE_IG_SECONDARY", raising=False)
    cap = InstagrapiCapability()
    assert cap.availability().reason == "gate_disabled:ENABLE_IG_SECONDARY"
    assert "rate" in cap.gates and "vault" in cap.gates


def test_instagrapi_requires_credentials(monkeypatch):
    monkeypatch.setenv("ENABLE_IG_SECONDARY", "true")
    monkeypatch.delenv("IG_USERNAME", raising=False)
    monkeypatch.delenv("IG_PASSWORD", raising=False)
    monkeypatch.setattr(
        "agent_core.capabilities.adapters_sensors._module_available", lambda _n: True
    )
    assert InstagrapiCapability().availability().reason == (
        "credentials_missing:IG_USERNAME/IG_PASSWORD"
    )


@pytest.mark.asyncio
async def test_instagrapi_never_writes_credentials_into_evidence(monkeypatch):
    """Kimlik bilgisi kanıta, telemetriye veya rapora SIZAMAZ."""
    monkeypatch.setenv("IG_USERNAME", "operatör")
    monkeypatch.setenv("IG_PASSWORD", "gizli-sifre-123")

    class _Media:
        id = 1
        code = "ABC"
        caption_text = "merhaba dünya"
        taken_at = None
        like_count = 5
        comment_count = 1
        media_type = 1

    class _Info:
        full_name = "Hedef Kişi"
        biography = "biyografi"
        follower_count = 100
        following_count = 50
        is_private = False
        media_count = 12

    class _Client:
        def login(self, u, p):
            assert u == "operatör"
            self.ok = True

        def user_id_from_username(self, _u):
            return 7

        def user_info(self, _id):
            return _Info()

        def user_medias(self, _id, limit):
            return [_Media()]

    import sys
    import types

    monkeypatch.setitem(
        sys.modules,
        "instagrapi",
        types.SimpleNamespace(Client=lambda: _Client()),
    )
    monkeypatch.setattr(
        "agent_core.capabilities.adapters_sensors._module_available", lambda _n: True
    )
    monkeypatch.setattr(InstagrapiCapability, "gates", frozenset())

    result = await InstagrapiCapability().run(CapabilityContext(subject="hedef"))
    blob = str(result.items) + str(result.payload) + str(result.notes)
    assert "gizli-sifre-123" not in blob
    assert "operatör" not in blob
    assert result.items[0].scope["source_role"] == "secondary"


# -------------------------------------- A5 · Agent-Reach ve SearXNG dürüstlüğü
def test_agent_reach_and_searxng_report_missing_dependency(monkeypatch):
    monkeypatch.setenv("ENABLE_AGENT_REACH", "true")
    monkeypatch.setattr("agent_core.capabilities.adapters_sensors.shutil.which", lambda _n: None)
    assert AgentReachCapability().availability().reason == "dependency_missing:agent-reach"

    monkeypatch.setenv("ENABLE_SEARXNG", "true")
    monkeypatch.delenv("SEARXNG_BASE_URL", raising=False)
    assert SearXNGCapability().availability().reason == "config_missing:SEARXNG_BASE_URL"


@pytest.mark.asyncio
async def test_searxng_is_called_over_http_only(monkeypatch):
    """AGPL: kod gömülmez, yalnız HTTP. İstek doğru uçta ve JSON formatında."""
    seen = {}

    class _Response:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {"url": "https://kaynak.test/a", "title": "A", "content": "içerik a",
                     "engine": "duckduckgo"}
                ]
            }

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            seen["url"] = url
            seen["params"] = params
            return _Response()

    import agent_core.capabilities.adapters_sensors as sensors

    monkeypatch.setattr(sensors.httpx, "AsyncClient", _Client)
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("ENABLE_SEARXNG", "true")

    result = await SearXNGCapability().run(CapabilityContext(subject="hedef kişi"))
    assert result.ok is True
    assert seen["url"] == "http://127.0.0.1:8080/search"
    assert seen["params"]["q"] == "hedef kişi"
    assert seen["params"]["format"] == "json"
    assert result.items[0].provenance_refs == ["https://kaynak.test/a"]


@pytest.mark.asyncio
async def test_searxng_unreachable_is_honest(monkeypatch):
    import agent_core.capabilities.adapters_sensors as sensors

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(sensors.httpx, "AsyncClient", _Client)
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("ENABLE_SEARXNG", "true")

    result = await SearXNGCapability().run(CapabilityContext(subject="hedef"))
    assert result.available is False
    assert result.unavailable_reason == "service_unreachable"
    assert result.items == ()


# ------------------------------------------------------- A6 · kasa üstünlüğü
@pytest.mark.asyncio
async def test_vault_lock_blocks_whole_retina_stack():
    """Kasa kapalıyken Faz A'daki hiçbir yetenek koşamaz."""
    reg = CapabilityRegistry()
    bootstrap(reg)
    state = PolicyState(vault_locked=True, rate_ok=True)
    for cap in reg:
        result = await run_capability(
            cap.id, CapabilityContext(subject="hedef"), registry=reg, state=state
        )
        assert result.denied_by == "vault", f"{cap.id} kasa kilidini atladı"
        assert result.items == ()
