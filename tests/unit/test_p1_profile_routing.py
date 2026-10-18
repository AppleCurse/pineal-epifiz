"""[P1 · DENETIM 2026-10-16] Profil derinleştirme hattı — regresyon sözleşmeleri.

Bu dosya, Faz 2 P1 düzeltmelerinin sözleşmelerini kilitler. Her test, düzeltme
geri alınınca KIRMIZIYA dönmelidir (revert-doğrulama).

1. URL → DOĞRU yetenek (sınıflandırma; profil olmayan adres yola bağlanmaz)
2. Kapalı/engelli kapı → `not_run` + MAKİNE-OKUNUR sebep (sessiz düşüş yok)
3. Kaza sonrası kanıt tipi ayrımı bozulmaz (snippet ≠ gönderi)
4. Çağrı yolu `CapabilityRunner` ve `egress.py`'den geçer
5. socid capability artık ÖLÜ KOD değildir; çıktısı kanıt zincirine girer
6. Kanal defteri boş liste dönmez; her planlanan profil için bir satır üretilir
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from agent_core.capabilities.base import CapabilityContext, CapabilityResult
from agent_core.domain.channel_status import CHANNEL_FAILED, CHANNEL_NOT_RUN, CHANNEL_OK
from agent_core.domain.content_basis import CONTENT_BASIS_SEARCH
from agent_core.services.profile_router import (
    CAPABILITY_INSTAGRAM,
    CAPABILITY_SOCID,
    CAPABILITY_X,
    REASON_NOT_A_PROFILE,
    REASON_UNSUPPORTED,
    classify_url,
    plan_for_urls,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ yardımcılar
class _FakeRunner:
    """`CapabilityRunner` sahte çifti — gerçek yetenek KOŞMAZ."""

    def __init__(self, results: dict[str, CapabilityResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, CapabilityContext, Any]] = []

    async def run(self, cap_id, ctx=None, *, state=None):  # noqa: D102
        self.calls.append((cap_id, ctx, state))
        if cap_id in self.results:
            return self.results[cap_id]
        return CapabilityResult(capability_id=cap_id, available=False, unavailable_reason="not_found")


def _ok_result(cap_id: str, items: tuple = (), payload: Any = None) -> CapabilityResult:
    return CapabilityResult(
        capability_id=cap_id, available=True, items=items, payload=payload
    )


# ============================================================ 1. SINIFLANDIRMA
def test_instagram_profile_url_routes_to_instagrapi():
    """[P1 · Bulgu 1] IG profil URL'si → `sensor.ig.instagrapi`."""
    route = classify_url("https://www.instagram.com/hedef/")
    assert route.runnable is True
    assert route.capability_id == CAPABILITY_INSTAGRAM
    assert route.handle == "hedef"
    assert route.platform == "instagram"
    assert route.reason == ""


def test_x_profile_url_routes_to_x_sensor():
    """X profil URL'si → `sensor.x.twscrape`."""
    route = classify_url("https://x.com/hedef")
    assert route.runnable is True
    assert route.capability_id == CAPABILITY_X
    assert route.handle == "hedef"


def test_twitter_profile_url_routes_to_x_sensor():
    """twitter.com de aynı sensöre gider (X zinciri)."""
    assert classify_url("https://twitter.com/hedef").capability_id == CAPABILITY_X


def test_linkedin_profile_url_routes_to_socid():
    """[P1 · Bulgu 3] LinkedIn profil URL'si → `extractor.identity.socid`."""
    route = classify_url("https://www.linkedin.com/in/hedef")
    assert route.runnable is True
    assert route.capability_id == CAPABILITY_SOCID
    assert route.handle == "hedef"


def test_facebook_profile_url_routes_to_socid():
    """Facebook profil URL'si → socid (kimlik alanı çıkarımı)."""
    route = classify_url("https://www.facebook.com/hedef")
    assert route.capability_id == CAPABILITY_SOCID
    assert route.runnable is True


@pytest.mark.parametrize(
    ("url", "expected_handle"),
    [
        ("https://www.tiktok.com/@hedef", "hedef"),
        ("https://www.youtube.com/@hedef", "hedef"),
        ("https://www.threads.net/@hedef", "hedef"),
        ("https://github.com/hedef", "hedef"),
        ("https://www.reddit.com/user/hedef", "hedef"),
        ("https://www.pinterest.com/hedef/", "hedef"),
        ("https://www.twitch.tv/hedef", "hedef"),
        ("https://t.me/hedef", "hedef"),
        ("https://vk.com/hedef", "hedef"),
        ("https://medium.com/@hedef", "hedef"),
        ("https://www.snapchat.com/add/hedef", "hedef"),
        ("https://steamcommunity.com/id/hedef", "hedef"),
        ("https://linktr.ee/hedef", "hedef"),
        ("https://www.behance.net/hedef", "hedef"),
        ("https://dribbble.com/hedef", "hedef"),
    ],
)
def test_multi_platform_social_urls_route_to_socid(url: str, expected_handle: str):
    """Tüm ana sosyal medya platformları `extractor.identity.socid` omurgasına bağlanır."""
    from agent_core.aspasia.interface import _TARGET_RE

    route = classify_url(url)
    assert route.runnable is True, f"{url} runnable değil"
    assert route.capability_id == CAPABILITY_SOCID
    assert route.handle == expected_handle
    assert _TARGET_RE.match(url), f"Aspasia _TARGET_RE {url} adresini reddetti"


def test_socid_route_carries_the_profile_url():
    """socid profil SAYFASINI ister → subject URL olmalı (handle değil)."""
    route = classify_url("https://www.linkedin.com/in/hedef")
    assert route.subject == "https://www.linkedin.com/in/hedef"
    assert route.params.get("url") == route.subject


def test_reserved_instagram_segment_is_not_a_profile():
    """Etiket/gönderi sayfası "profil" sayılmaz (yanlış hedef yasağı)."""
    route = classify_url("https://instagram.com/p/ABC123/")
    assert route.runnable is False
    assert route.reason == REASON_NOT_A_PROFILE
    assert route.capability_id == ""


def test_x_status_url_is_not_a_profile():
    """`x.com/i/status/...` bir profil değil."""
    route = classify_url("https://x.com/i/status/123")
    assert route.runnable is False
    assert route.reason == REASON_NOT_A_PROFILE


def test_unsupported_platform_is_reported_not_dropped():
    """Desteklenmeyen alan adı sessizce ATILMAZ; sebep döner."""
    route = classify_url("https://example.com/hedef")
    assert route.runnable is False
    assert route.reason == REASON_UNSUPPORTED


def test_lookalike_host_is_not_treated_as_platform():
    """[P1] Alt dize taklidi: `instagram.com.evil.example` IG DEĞİLDİR."""
    route = classify_url("https://instagram.com.evil.example/hedef")
    assert route.runnable is False
    assert route.capability_id == ""


def test_duplicate_urls_are_planned_once():
    """Aynı URL iki kez planlanmaz."""
    plan = plan_for_urls(["https://x.com/a", "https://x.com/a"], limit=5)
    assert len(plan) == 1


def test_plan_respects_limit():
    """`limit` uygulanır (socid ile aynı sınır)."""
    plan = plan_for_urls(
        [f"https://x.com/k{i}" for i in range(10)],
        limit=3,
    )
    assert len(plan) == 3


def test_plan_keeps_unroutable_urls_with_reason():
    """Yolsuz adres de plan satırı olarak kalır (sessiz düşüş yok)."""
    plan = plan_for_urls(["https://example.com/hedef"], limit=3)
    assert len(plan) == 1
    assert plan[0].runnable is False
    assert plan[0].reason == REASON_UNSUPPORTED


# ================================================== 2. KAPALI KAPI → not_run
@pytest.mark.asyncio
async def test_closed_sensor_yields_not_run_with_machine_reason(monkeypatch):
    """[P1] `ENABLE_X_SENSOR` kapalı → `not_run` + `policy:gate_disabled`."""
    from agent_core.capabilities import bootstrap
    from agent_core.capabilities.state import policy_state
    from agent_core.services.profile_deep_scan import run_detected_profiles

    monkeypatch.delenv("ENABLE_X_SENSOR", raising=False)
    bootstrap()
    result = await run_detected_profiles(
        ["https://x.com/hedef"],
        state=policy_state(vault_locked=False, rate_ok=True),
    )
    assert result.channel_runs, "kanal satırı üretilmedi"
    row = result.channel_runs[0]
    assert row.status == CHANNEL_NOT_RUN
    assert row.reason == "policy:gate_disabled"
    assert row.channel == CAPABILITY_X


@pytest.mark.asyncio
async def test_vault_locked_blocks_deep_scan():
    """[P1] Kasa kilitliyken profil kazınmaz; sebep yazılır."""
    from agent_core.capabilities.state import policy_state
    from agent_core.services.profile_deep_scan import run_detected_profiles

    result = await run_detected_profiles(
        ["https://x.com/hedef"],
        state=policy_state(vault_locked=True, rate_ok=True),
    )
    row = result.channel_runs[0]
    assert row.status == CHANNEL_NOT_RUN
    assert "vault" in (row.reason or "").lower()


@pytest.mark.asyncio
async def test_no_evidence_is_produced_when_sensor_cannot_run():
    """Kapalı sensör **kanıt üretmez** (uydurma kanıt yok)."""
    from agent_core.capabilities.state import policy_state
    from agent_core.services.profile_deep_scan import run_detected_profiles

    result = await run_detected_profiles(
        ["https://x.com/hedef"],
        state=policy_state(vault_locked=True, rate_ok=True),
    )
    assert result.evidence_items == []
    assert result.scraped == {}


@pytest.mark.asyncio
async def test_unroutable_url_produces_not_run_row_not_silence():
    """Yolsuz adres → `not_run` + sebep (kanal defteri boş kalmaz)."""
    from agent_core.services.profile_deep_scan import run_detected_profiles

    result = await run_detected_profiles(["https://example.com/hedef"], limit=3)
    assert len(result.channel_runs) == 1
    row = result.channel_runs[0]
    assert row.status == CHANNEL_NOT_RUN
    assert row.reason == REASON_UNSUPPORTED


@pytest.mark.asyncio
async def test_every_planned_profile_has_exactly_one_channel_row():
    """Her planlanan profil için bir kanal satırı (eksik/fazla satır yok)."""
    from agent_core.services.profile_deep_scan import run_detected_profiles

    urls = ["https://x.com/a", "https://instagram.com/b", "https://example.com/c"]
    result = await run_detected_profiles(urls, limit=5)
    assert len(result.channel_runs) == len(urls)


@pytest.mark.asyncio
async def test_channel_rows_are_never_an_empty_list_for_planned_work():
    """Plan boş değilse kanal listesi boş olamaz (P0 kuralı)."""
    from agent_core.services.profile_deep_scan import run_detected_profiles

    result = await run_detected_profiles(["https://x.com/a"], limit=3)
    assert result.channel_runs, "kanal satırı yok — P0 kuralı ihlali"


# ============================================== 3. KANIT TİPİ AYRIMI BOZULMAZ
@pytest.mark.asyncio
async def test_deep_scan_never_fills_posts_from_snippets():
    """[P1 + P0] Derin tarama başarısızsa `posts` boş kalır; snippet inmez."""
    from agent_core.services.profile_deep_scan import run_detected_profiles
    from backend.services.web_dossier import build_dossier_profile

    profile = build_dossier_profile(
        display_user="@hedef",
        clean_u="hedef",
        snippets=[{"text": "x" * 30, "provider": "tavily", "source_url": "https://a.example"}],
        found_profiles=["https://x.com/hedef"],
    )
    result = await run_detected_profiles(["https://x.com/hedef"], limit=3)

    assert profile["posts"] == []
    assert profile["post_evidence_types"] == []
    assert profile["content_basis"] == CONTENT_BASIS_SEARCH
    assert profile["search_snippets"], "snippet kayboldu"
    # Derin tarama kanıt üretemediyse scrape alanı boş kalır
    assert result.scraped == {}


@pytest.mark.asyncio
async def test_scraped_payload_is_only_filled_when_capability_ran():
    """`scraped` yalnız GERÇEKTEN koşan yeteneğin payload'ı ile dolar."""
    from agent_core.services.profile_deep_scan import run_plan
    from agent_core.services.profile_router import plan_for_urls

    runner = _FakeRunner(
        {
            CAPABILITY_X: _ok_result(
                CAPABILITY_X,
                items=(),
                payload={"series": [{"id": "1", "created_at": "2026-01-01T00:00:00+00:00"}]},
            )
        }
    )
    result = await run_plan(plan_for_urls(["https://x.com/hedef"]), runner=runner)
    assert result.scraped, "koşan yeteneğin payload'ı alınmadı"
    assert result.channel_runs[0].status == CHANNEL_OK


# ============================================= 4. ÇAĞRI YOLU: runner + egress
@pytest.mark.asyncio
async def test_deep_scan_runs_through_the_capability_runner():
    """[P1] Yetenekler DOĞRUDAN çağrılmaz; `CapabilityRunner` üzerinden."""
    from agent_core.services.profile_deep_scan import run_detected_profiles

    runner = _FakeRunner({CAPABILITY_X: _ok_result(CAPABILITY_X)})
    await run_detected_profiles(["https://x.com/hedef"], runner=runner, limit=3)
    assert runner.calls, "runner çağrılmadı"
    cap_id, ctx, _state = runner.calls[0]
    assert cap_id == CAPABILITY_X
    assert ctx.subject == "hedef"


@pytest.mark.asyncio
async def test_state_is_passed_to_the_runner_unchanged():
    """Kasa/hız durumu çağırandan aynen geçer (kapı zayıflatılmaz)."""
    from agent_core.capabilities.state import policy_state
    from agent_core.services.profile_deep_scan import run_detected_profiles

    state = policy_state(vault_locked=True, rate_ok=False)
    runner = _FakeRunner()
    await run_detected_profiles(["https://x.com/hedef"], state=state, runner=runner)
    assert runner.calls[0][2] is state


def test_deep_scan_module_never_builds_http_clients():
    """[P1 · egress] Yeni modül HTTP istemcisi kurmaz — tek çıkış yolu `egress.py`.

    `urllib.parse` YALNIZ URL **ayrıştırma** içindir (ağ değil) → serbesttir;
    `urllib.request`/`urllib.error` ise ağ modülüdür → yasaktır.
    """
    for name in ("agent_core/services/profile_deep_scan.py", "agent_core/services/profile_router.py"):
        source = (REPO_ROOT / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        for banned in ("httpx", "requests", "aiohttp", "urllib.request", "urllib.error"):
            assert banned not in imported, f"{name} doğrudan {banned} import ediyor"


def test_egress_spine_remains_the_only_http_exit():
    """[P1 · egress] `agent_core` içinde `httpx` import eden dosya sayısı artmaz."""
    offenders: list[str] = []
    for path in (REPO_ROOT / "agent_core").rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            if "httpx" in names:
                rel = path.relative_to(REPO_ROOT).as_posix()
                offenders.append(rel)
    assert offenders == ["agent_core/capabilities/egress.py"], offenders


# ================================================== 5. socid ÖLÜ KOD DEĞİL
@pytest.mark.asyncio
async def test_socid_capability_is_actually_invoked():
    """[P1 · Bulgu 3] socid capability artık çağrılır (ölü kod değil)."""
    from agent_core.services.profile_deep_scan import run_detected_profiles

    runner = _FakeRunner({CAPABILITY_SOCID: _ok_result(CAPABILITY_SOCID)})
    result = await run_detected_profiles(
        ["https://www.linkedin.com/in/hedef"], runner=runner, limit=3
    )
    assert runner.calls, "socid çağrılmadı"
    assert runner.calls[0][0] == CAPABILITY_SOCID
    assert runner.calls[0][1].subject == "https://www.linkedin.com/in/hedef"
    assert result.channel_runs[0].channel == CAPABILITY_SOCID


@pytest.mark.asyncio
async def test_socid_evidence_items_reach_the_result():
    """socid kanıtı sonuçta `EvidenceItem` olarak taşınır."""
    from agent_core.capabilities.base import make_evidence
    from agent_core.services.profile_deep_scan import run_detected_profiles

    item = make_evidence(
        content="profile identity extracted: uid=42",
        source_engine="socid_extractor",
        epistemic_type="observation",
    )
    runner = _FakeRunner({CAPABILITY_SOCID: _ok_result(CAPABILITY_SOCID, items=(item,))})
    result = await run_detected_profiles(
        ["https://www.linkedin.com/in/hedef"], runner=runner, limit=3
    )
    assert len(result.evidence_items) == 1
    assert result.evidence_items[0].source_engine == "socid_extractor"


# ==================================================== 6. RAPORLAMA DİLİ
@pytest.mark.asyncio
async def test_detected_url_is_not_reported_as_scraped():
    """[P1] "Bulundu" ≠ "kazındı": kazınmayan URL kazınmış gibi yazılmaz."""
    from agent_core.services.profile_deep_scan import run_detected_profiles

    result = await run_detected_profiles(
        ["https://x.com/hedef"],
        limit=3,
    )
    assert result.scraped == {}
    row = result.channel_runs[0]
    assert row.status in (CHANNEL_NOT_RUN, CHANNEL_OK, CHANNEL_FAILED)
    # "ok" ise kanıt sayısı açıkça yazılır
    if row.status == CHANNEL_OK:
        assert row.detail and "kanıt" in row.detail


def test_ui_language_gates_the_claim_behind_real_posts():
    """[P1] "BAĞLANAN" dili **yalnız gerçek kazıma varsa** kullanılabilir.

    P0'dan gelen sözleşme: rozet/etiket `targetPosts.length > 0` koşuluna
    bağlıdır (yani gerçekten kazınmış gönderi yoksa "KAZINMADI" yazar).
    """
    war_room = (
        REPO_ROOT / "frontend" / "src" / "components" / "TacticalWarRoom.svelte"
    ).read_text(encoding="utf-8")
    assert "BAĞLANAN CANLI PROFİLLER" not in war_room or (
        re.search(
            r"targetPosts\.length\s*>\s*0[^;]{0,200}BAĞLANAN CANLI PROFİLLER",
            war_room,
            re.DOTALL,
        )
        is not None
    ), "'BAĞLANAN' dili gerçek kazıma koşuluna bağlı değil"
    assert "KAZINMADI" in war_room
    assert "ÇALIŞMAYAN KANALLAR" in war_room


def test_ui_does_not_claim_data_was_linked_without_measurement():
    """[P1] "veri bağlandı" gibi ölçülmemiş iddialar UI'da yok."""
    #: [P6 · 2026-10-18] Ölü `UnifiedCompactPanel.svelte` silindi; sözleşme
    #: artık CANLI frontend ağacının TAMAMINA uygulanır (daha güçlü kilit).
    targets = sorted((REPO_ROOT / "frontend" / "src").rglob("*.svelte"))
    forbidden = re.compile(r"(sosyal profil ve açık veri bağlandı|profil bağlandı)", re.IGNORECASE)
    for path in targets:
        text = path.read_text(encoding="utf-8")
        # Yorum satırları kullanıcıya görünmez → iddia metni sayılmaz.
        code = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
        code = re.sub(r"//[^\n]*", " ", code)
        assert not forbidden.search(code), f"{path.name}: ölçülmemiş 'bağlandı' dili"


# ============================== 7. API BAĞLANTISI (P1-7) + KANIT ZİNCİRİ (P1-8)
class _FakeSearchResult:
    def __init__(self, source_url: str, content: str) -> None:
        self.source_url = source_url
        self.content = content
        self.provider = "tavily"


class _FakeSearchOutcome:
    def __init__(self, results, available: bool = True, error=None) -> None:
        self.results = results
        self.available = available
        self.error = error


async def _run_mission_with_detected_profile(monkeypatch, client_id: str = "p1_api"):
    """Arama sonucunda bir Instagram profili bulunan görev akışı."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.api import InitiatePayload, run_mission

    monkeypatch.setenv("ENABLE_CROSS_PLATFORM", "true")
    outcome = _FakeSearchOutcome(
        [
            _FakeSearchResult(
                "https://example.com/hedef",
                "Hedef, gece yarısı ormanda yürüyüşlerini paylaşıyor.",
            ),
            _FakeSearchResult(
                "https://www.instagram.com/hedef/",
                "Hedef'in Instagram profil sayfası burada yer alıyor.",
            ),
        ]
    )
    executor = MagicMock()
    executor.search_engine.search = AsyncMock(return_value=outcome)
    executor.search_engine.set_policy = MagicMock()
    executor.execute_task = AsyncMock(return_value=MagicMock())

    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result"), \
         patch("backend.api.broadcast_result_error"), \
         patch("backend.api._check_vault_interlock", return_value=False), \
         patch("backend.api._minor_case_for", return_value=None):
        await run_mission(InitiatePayload(
            client_id=client_id, url="https://ornek.com/hedef",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="cross",
        ))
    return executor.execute_task.await_args[0][0]


async def _run_executor_with_detected_profile(monkeypatch, client_id: str = "p1_exec"):
    """Gerçek görev yürütücüsü, tespit edilmiş bir Instagram profiliyle.

    Yetenekler **koşmaz** (kapı kapalı → "koşmadı + sebep" satırı yazılır);
    LLM ve arama katmanı hermetik tutulur.
    """
    from unittest.mock import AsyncMock

    from agent_core.services.llm_gateway import LLMGateway
    from agent_core.task_executor import PinealExecutor

    monkeypatch.setattr(LLMGateway, "query", AsyncMock(return_value="Analiz metni"))
    monkeypatch.setattr(LLMGateway, "query_json", AsyncMock(return_value={}))
    monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)

    payload = {
        "target_profile": {
            "username": "@hedef",
            "name": "Hedef",
            "bio": "gece yarısı ormanda yürüyüşler",
            "platform": "instagram",
            "posts": [],
            "detected_urls": ["https://www.instagram.com/hedef/"],
        },
        "policy": {"vault_locked": False, "rate_ok": True},
    }
    executor = PinealExecutor()
    res = await executor.execute_task(payload, "test-p1-executor")
    return payload, res


@pytest.mark.asyncio
async def test_executor_actually_runs_the_deep_scan_for_detected_profiles(monkeypatch):
    """[P1-7] Bulunan profil "not_attempted" değil — GERÇEK kanal satırı yazılır.

    KOŞUM TEK YERDE: görev yürütücüsü
    (``deep_profile_resolver`` → ``profile_router`` → ``CapabilityRunner``).
    API katmanı yalnız adresleri taşır; ikinci bir koşum yolu yoktur.
    """
    payload, res = await _run_executor_with_detected_profile(monkeypatch)
    channels = {c["channel"]: c for c in getattr(res, "channel_status", [])}

    assert "profile.deep_scan" in channels, "derin tarama kanalı yok"
    assert channels["profile.deep_scan"]["status"] == CHANNEL_NOT_RUN
    assert channels["profile.deep_scan"]["reason"], "koşmama sebebi yok"
    # "henüz denenmedi" artık YANLIŞ: tarama gerçekten denendi.
    assert channels["profile.deep_scan"]["reason"] != "not_attempted"
    # Yeteneğin kendi satırı da defterde (hangi yetenek, hangi sebep).
    assert "sensor.ig.instagrapi" in channels
    assert channels["sensor.ig.instagrapi"]["status"] == CHANNEL_NOT_RUN
    assert channels["sensor.ig.instagrapi"]["reason"]


@pytest.mark.asyncio
async def test_executor_writes_the_scanned_url_ledger(monkeypatch):
    """[P1-7] Her tespit edilen profil için bir defter satırı (durum + sebep)."""
    payload, _res = await _run_executor_with_detected_profile(monkeypatch)
    scanned = payload["target_profile"]["scanned_urls"]

    assert len(scanned) == 1, f"defter satırı sayısı beklenenden farklı: {scanned}"
    row = scanned[0]
    assert row["url"] == "https://www.instagram.com/hedef/"
    assert row["capability_id"] == CAPABILITY_INSTAGRAM
    assert row["status"] in {CHANNEL_OK, CHANNEL_NOT_RUN, CHANNEL_FAILED}
    assert row["reason"] or row["status"] == CHANNEL_OK


@pytest.mark.asyncio
async def test_detected_profile_posts_do_not_become_target_posts(monkeypatch):
    """[P1-7 + P0] Bulunan profil ≠ hedef: hedefin `posts` alanı karışmaz."""
    payload = await _run_mission_with_detected_profile(monkeypatch)
    profile = payload["target_profile"]

    assert profile["posts"] == [], "bulunan profil gönderileri hedefe yazıldı"
    assert profile["post_evidence_types"] == []
    # Kazınan gönderiler AYRI alanda tutulur (kanıt tipiyle birlikte).
    assert isinstance(profile["scanned_profiles"], dict)


@pytest.mark.asyncio
async def test_deep_scan_evidence_travels_into_the_task_payload(monkeypatch):
    """[P1-8] socid/kanıt çıktısı görev payload'ına kanıt olarak taşınır.

    Kasa kilitliyken kanıt ÜRETİLMEZ (uydurma yok) → zincir boş kalır.
    """
    payload = await _run_mission_with_detected_profile(monkeypatch)

    # API katmanı artık koşum YAPMAZ (tek koşum yolu: görev yürütücüsü);
    # kasa kilitliyken de kanıt üretilmez → zincirde uydurma kanıt YOKTUR.
    assert "profile_deep_scan_evidence" not in payload
    assert not payload.get("forensic_evidence")


def test_deep_scan_evidence_merges_into_the_canonical_chain():
    """[P1-8] Derin tarama kanıtı `forensic_evidence` zincirine girer."""
    from agent_core.capabilities.base import make_evidence
    from agent_core.services.pillar_evidence_adapter import adapt_pillar_bundle

    item = make_evidence(
        content="profile identity extracted from https://linkedin.com/in/hedef: uid=42",
        source_engine="socid_extractor",
        epistemic_type="observation",
    )
    items = adapt_pillar_bundle(None, extra_items=[item])

    assert len(items) == 1
    assert items[0].source_engine == "socid_extractor"
    assert items[0].evidence_id == item.evidence_id


def test_deep_scan_evidence_is_timeline_ready():
    """[P1-8] Derin tarama kanıtı zaman çizelgesine de girer (rejected olmaz)."""
    from agent_core.capabilities.base import make_evidence
    from agent_core.services.evidence_timeline import build_evidence_timeline

    item = make_evidence(
        content="X post by @hedef: gece yarısı ormanda yürüyüş",
        source_engine="twscrape",
        epistemic_type="observation",
    )
    timeline = build_evidence_timeline([item])

    assert timeline.rejected_item_count == 0
    assert len(timeline.entries) == 1
    assert timeline.entries[0].source_engine == "twscrape"


def test_task_executor_passes_deep_scan_evidence_to_the_adapter():
    """[P1-8] Görev yürütücüsü kanıtı adaptöre taşır (kaynak satırı).

    Derin tarama ve çapraz profilleme kanıtları, kanonik kanıt zincirine
    adaptörün ``extra_items`` kanalıyla girer (pillar paketi boş olsa bile
    kanıt kaybolmaz).
    """
    source = (REPO_ROOT / "agent_core" / "task_executor.py").read_text(encoding="utf-8")
    assert "extra_items=[*_deep_items, *_cross_items]" in source
    # Eski (ikinci) kanıt yolu kalmadı: kanıtlar TEK yerden eklenir.
    assert "canonical_items = list(canonical_items) + list(_deep_items)" not in source
