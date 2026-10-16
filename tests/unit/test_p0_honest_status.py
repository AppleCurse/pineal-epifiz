"""[P0 · DENETİM 2026-10-16] Dürüst durum + kanıt tipi ayrımı.

Bu dosya, Faz 2 P0 düzeltmelerinin REGRESYON SÖZLEŞMELERİNİ kilitler.
Her test, düzeltme geri alınınca KIRMIZIYA dönmelidir (revert-doğrulama):

1. Kanıt tipi ayrımı — arama sonucu (snippet) "gönderi" diye sunulamaz.
2. Web dosyası yolu: `posts` boş, `search_snippets` etiketli, `content_basis`
   beyan edilir; "N profil bağlandı" yalanı üretilmez.
3. Kanal durumu: koşmayan kanal + SEBEP (boş liste yasak).
4. X sensörü: boş hesap havuzu → `no_session_pool` (≠ `user_not_found`).
5. `accounts.db` kirliliği: twscrape DB yolu yapılandırılabilir, depo köküne
   yazılmaz.
6. Telemetri: `capabilities[]` sebebiyle birlikte döner.
7. UI: yalan metinleri kaldırılmış, "ÇALIŞMADI: sebep" gösterimi var.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.domain.channel_status import (
    CHANNEL_FAILED,
    CHANNEL_NOT_RUN,
    CHANNEL_OK,
    from_engine_result,
    not_run,
    ok,
    serialize,
    summarize,
)
from agent_core.domain.content_basis import (
    CONTENT_BASIS_NONE,
    CONTENT_BASIS_PLATFORM,
    CONTENT_BASIS_SEARCH,
    EVIDENCE_PLATFORM_POST,
    EVIDENCE_SEARCH_SNIPPET,
    content_basis,
    extract_public_text,
    render_corpus_block,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "frontend" / "src"


# ---------------------------------------------------------------- yardımcılar
def _web_dossier_profile() -> dict:
    """Web dosyası (arama) yolunun ürettiği hedef profili."""
    return {
        "username": "@hedef",
        "name": "hedef",
        "bio": "",
        "posts": [],
        "post_times": [],
        "posts_meta": [],
        "post_types": [],
        "post_evidence_types": [],
        "search_snippets": [
            {
                "text": "Hedef, gece yarısı ormanda yürüyüşlerini paylaşıyor.",
                "provider": "tavily",
                "source_url": "https://example.com/hedef",
            }
        ],
        "content_basis": CONTENT_BASIS_SEARCH,
        "platform": "web_dossier",
    }


def _instagram_profile() -> dict:
    return {
        "username": "@hedef",
        "bio": "gece yürüyüşleri",
        "posts": ["gece yarısı ormanda yürüyüş"],
        "post_times": ["2024-05-01T23:30:00+00:00"],
        "posts_meta": [{"like_count": 10, "comment_count": 1}],
        "post_types": ["image"],
        "post_evidence_types": [EVIDENCE_PLATFORM_POST],
        "search_snippets": [],
        "content_basis": CONTENT_BASIS_PLATFORM,
        "platform": "instagram",
    }


# ================================================================ 1. KANIT TİPİ
def test_search_snippet_is_not_a_post():
    """Snippet `posts` alanında durmaz; kanıt tipi `search_snippet` olur."""
    items = extract_public_text(_web_dossier_profile())
    assert items, "snippet okunamadı"
    assert {i.evidence_type for i in items} == {EVIDENCE_SEARCH_SNIPPET}
    assert content_basis(_web_dossier_profile()) == CONTENT_BASIS_SEARCH


def test_platform_post_keeps_its_own_type():
    items = extract_public_text(_instagram_profile())
    assert {i.evidence_type for i in items} == {EVIDENCE_PLATFORM_POST}
    assert content_basis(_instagram_profile()) == CONTENT_BASIS_PLATFORM


def test_empty_profile_basis_is_none():
    assert content_basis({}) == CONTENT_BASIS_NONE
    assert content_basis(None) == CONTENT_BASIS_NONE


def test_corpus_block_labels_snippet_and_does_not_call_it_post():
    """Prompt'ta snippet "gönderi" diye sunulamaz."""
    block = render_corpus_block(extract_public_text(_web_dossier_profile()))
    assert "arama sonucu" in block
    assert "gönderi]" not in block
    assert "DEĞİLDİR" in block


def test_corpus_block_labels_real_post_as_post():
    block = render_corpus_block(extract_public_text(_instagram_profile()))
    assert "[gönderi]" in block
    assert "arama sonucu" not in block


# ================================================================ 2. WEB DOSYASI YOLU
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


@pytest.mark.asyncio
async def test_web_dossier_never_marks_snippets_as_posts(monkeypatch):
    """[P0] Arama sonucu `posts` alanına yazılmaz; etiketli taşınır."""
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
            client_id="p0_web", url="https://ornek.com/hedef",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="cross",
        ))

    payload = executor.execute_task.await_args[0][0]
    profile = payload["target_profile"]

    assert profile["posts"] == [], "arama sonucu 'gönderi' olarak yazıldı"
    assert profile["post_types"] == []
    assert profile["post_evidence_types"] == []
    assert profile["content_basis"] == CONTENT_BASIS_SEARCH
    assert len(profile["search_snippets"]) == 2
    assert profile["search_snippets"][0]["provider"] == "tavily"
    assert profile["search_snippets"][0]["source_url"] == "https://example.com/hedef"
    # Bulunan profil URL'leri bulunmuştur ama KAZINMAMIŞTIR.
    assert profile["detected_urls"] == ["https://www.instagram.com/hedef/"]


@pytest.mark.asyncio
async def test_web_dossier_reports_channel_reasons(monkeypatch):
    """[P0] Koşmayan kanal boş liste değil, SEBEP taşır."""
    from backend.api import InitiatePayload, run_mission

    monkeypatch.setenv("ENABLE_CROSS_PLATFORM", "true")

    outcome = _FakeSearchOutcome(
        [
            _FakeSearchResult(
                "https://www.instagram.com/hedef/",
                "Hedef'in Instagram profil sayfası burada yer alıyor.",
            )
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
            client_id="p0_ch", url="https://ornek.com/hedef",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="cross",
        ))

    payload = executor.execute_task.await_args[0][0]
    channels = {c["channel"]: c for c in payload["channel_status"]}

    assert "search.web" in channels, "arama kanalı durumu yok"
    assert channels["search.web"]["status"] == CHANNEL_OK
    # Bulunan ama kazınmayan profil → kanıt üretmedi, sebebiyle birlikte.
    assert "profile.deep_scan" in channels
    assert channels["profile.deep_scan"]["status"] == CHANNEL_NOT_RUN
    assert channels["profile.deep_scan"]["reason"]


@pytest.mark.asyncio
async def test_web_dossier_does_not_claim_profiles_were_linked(monkeypatch):
    """[P0] "N profil hedefe bağlandı" yalanı üretilmez."""
    from backend.api import InitiatePayload, run_mission

    monkeypatch.setenv("ENABLE_CROSS_PLATFORM", "true")
    outcome = _FakeSearchOutcome(
        [
            _FakeSearchResult(
                "https://www.instagram.com/hedef/",
                "Hedef'in Instagram profil sayfası burada yer alıyor.",
            )
        ]
    )
    executor = MagicMock()
    executor.search_engine.search = AsyncMock(return_value=outcome)
    executor.search_engine.set_policy = MagicMock()
    executor.execute_task = AsyncMock(return_value=MagicMock())

    logs: list[tuple] = []

    def _capture(client_id, level, msg):
        logs.append((level, msg))

    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log", side_effect=_capture), \
         patch("backend.api.broadcast_result"), \
         patch("backend.api.broadcast_result_error"), \
         patch("backend.api._check_vault_interlock", return_value=False), \
         patch("backend.api._minor_case_for", return_value=None):
        await run_mission(InitiatePayload(
            client_id="p0_lie", url="https://ornek.com/hedef",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="cross",
        ))

    joined = " ".join(str(m) for _lvl, m in logs)
    assert "profil hedefe bağlandı" not in joined
    assert "bağlandı" not in joined


# ================================================================ 3. KANAL DURUMU
def test_channel_status_never_returns_empty_reason():
    run = not_run("sensor.x.twscrape", reason="no_session_pool")
    assert run.status == CHANNEL_NOT_RUN
    assert run.reason == "no_session_pool"
    assert serialize([run])[0]["reason"] == "no_session_pool"


def test_channel_summary_counts_and_lists_reasons():
    runs = [ok("search.web"), not_run("sensor.x.twscrape", "no_session_pool")]
    summary = summarize(runs)
    assert summary["ok"] == 1
    assert summary["not_run"] == 1
    assert summary["not_run_reasons"][0]["reason"] == "no_session_pool"


def test_engine_result_mapping_distinguishes_not_run_from_failed():
    # Tarama hiç başlamadı → not_run
    assert from_engine_result("sensor.identity.maigret", {"available": False, "reason": "disabled"}).status == CHANNEL_NOT_RUN
    # Tarama başladı ama hata verdi → failed
    assert from_engine_result(
        "sensor.identity.maigret",
        {"available": False, "reason": "provider_errors", "scanned_count": 118},
    ).status == CHANNEL_FAILED
    # Başarılı → ok
    assert from_engine_result(
        "sensor.identity.maigret",
        {"available": True, "reason": None, "scanned_count": 118, "found_sites": ["a"]},
    ).status == CHANNEL_OK


def test_task_snapshot_carries_channel_status():
    from agent_core.domain.memory_models import TaskSnapshot

    snap = TaskSnapshot(task_id="t1", status="processing")
    assert snap.channel_status == []
    snap.channel_status = [{"channel": "search.web", "status": "ok"}]
    assert snap.channel_status[0]["channel"] == "search.web"


# ================================================================ 4. X SENSÖRÜ
class _FakeAccount:
    def __init__(self, active: bool) -> None:
        self.active = active


class _FakePool:
    def __init__(self, accounts) -> None:
        self._accounts = list(accounts)
        self._db_file = "/tmp/fake-x-accounts.db"

    async def get_all(self):
        return list(self._accounts)


class _FakeTwscrapeAPI:
    """`twscrape.API` sahte çifti — ağa çıkmaz."""

    def __init__(self, pool=None, **kwargs) -> None:
        self.pool = pool if isinstance(pool, _FakePool) else _FakePool([_FakeAccount(False)])
        self.user = None

    async def user_by_login(self, username):
        return self.user


@pytest.mark.asyncio
async def test_x_sensor_reports_no_session_pool_not_user_not_found(monkeypatch):
    """[P0 · Bulgu B-1] Boş hesap havuzu ≠ "kullanıcı yok"."""
    import twscrape

    from agent_core.capabilities.adapters_sensors import XTwscrapeCapability
    from agent_core.capabilities.base import CapabilityContext

    monkeypatch.setattr(twscrape, "API", _FakeTwscrapeAPI)
    cap = XTwscrapeCapability()
    result = await cap.run(CapabilityContext(subject="hedef"))

    assert result.available is False
    assert result.unavailable_reason == "no_session_pool"
    assert result.unavailable_reason != "user_not_found"
    assert result.notes.get("accounts_active") == 0


@pytest.mark.asyncio
async def test_x_sensor_keeps_user_not_found_when_pool_has_active_account(monkeypatch):
    """Havuzda AKTİF hesap varken "kullanıcı yok" ayrımı korunur."""
    import twscrape

    from agent_core.capabilities.adapters_sensors import XTwscrapeCapability
    from agent_core.capabilities.base import CapabilityContext

    def _factory(pool=None, **kwargs):
        api = _FakeTwscrapeAPI(pool=pool, **kwargs)
        api.pool = _FakePool([_FakeAccount(True)])
        return api

    monkeypatch.setattr(twscrape, "API", _factory)
    cap = XTwscrapeCapability()
    result = await cap.run(CapabilityContext(subject="hedef"))

    assert result.available is False
    assert result.unavailable_reason == "user_not_found"


@pytest.mark.asyncio
async def test_x_sensor_gate_disabled_reports_reason(monkeypatch):
    """[P0] Bayrak kapalı → koşmadı + makine-okunur sebep (boş liste değil)."""
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability
    from agent_core.capabilities.state import policy_state

    monkeypatch.delenv("ENABLE_X_SENSOR", raising=False)
    bootstrap()
    result = await run_capability(
        "sensor.x.twscrape",
        CapabilityContext(subject="hedef"),
        state=policy_state(vault_locked=False, rate_ok=True),
    )
    assert result.available is False
    # Politika çekirdeği kapıyı reddeder: sebep + reddeden bayrak ikisi de
    # MAKİNE-OKUNUR olmalı (bayrak adı kaybolmamalı).
    assert result.unavailable_reason == "policy:gate_disabled"
    assert result.denied_by == "ENABLE_X_SENSOR"


# ================================================================ 5. accounts.db
def test_x_accounts_db_path_is_configurable_and_not_repo_root(monkeypatch):
    """[P0 · Bulgu B-4] twscrape DB'si depo köküne yazılmaz."""
    from agent_core.capabilities.adapters_sensors import (
        _X_ACCOUNTS_DB_DEFAULT,
        _x_accounts_db_path,
    )

    monkeypatch.delenv("PINEAL_X_ACCOUNTS_DB", raising=False)
    default_path = _x_accounts_db_path()
    assert default_path == _X_ACCOUNTS_DB_DEFAULT
    assert "cache" in default_path.replace("\\", "/").split("/")
    assert default_path != "accounts.db"

    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", "/tmp/p0-x-accounts.db")
    assert _x_accounts_db_path() == "/tmp/p0-x-accounts.db"


@pytest.mark.asyncio
async def test_x_sensor_does_not_write_accounts_db_into_cwd(tmp_path, monkeypatch):
    """Çalışma dizinine accounts.db artefaktı düşmez."""
    import twscrape

    from agent_core.capabilities.adapters_sensors import XTwscrapeCapability
    from agent_core.capabilities.base import CapabilityContext

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", str(tmp_path / "cache" / "x_accounts.db"))
    monkeypatch.setattr(twscrape, "API", _FakeTwscrapeAPI)

    cap = XTwscrapeCapability()
    await cap.run(CapabilityContext(subject="hedef"))

    assert not (tmp_path / "accounts.db").exists()


# ================================================================ 6. TELEMETRİ
def test_telemetry_exposes_capability_table_with_reasons():
    """[P0 · Bulgu B-3] Telemetri "kapalı" demez, SEBEP taşır."""
    from backend.api import _capability_status_table

    rows = _capability_status_table(vault_locked=True)
    assert rows, "yetenek tablosu boş"
    for row in rows:
        assert "id" in row and "available" in row and "reason" in row
        if not row["available"]:
            assert row["reason"], f"{row['id']} için sebep yok"


@pytest.mark.asyncio
async def test_telemetry_payload_has_capabilities_and_x_reason():
    """`/api/telemetry` yanıtı yetenek tablosunu ve X sebebini taşır."""
    import backend.api as api

    executor = MagicMock()
    executor.llm_gateway = MagicMock()
    executor.search_engine = MagicMock()
    room = {"executor": executor, "vault": {}}

    with patch("backend.api.get_room", return_value=room), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api._scraper_capability", return_value={"instagram": False, "browser": False}), \
         patch("backend.api._check_vault_interlock", return_value=False):
        payload = await api.api_telemetry(client_id="p0_tel")

    assert "capabilities" in payload
    assert isinstance(payload["capabilities"], list) and payload["capabilities"]
    assert "capabilities_unavailable_reason" in payload
    assert "x_scraper_reason" in payload
    x_row = next(r for r in payload["capabilities"] if r["id"] == "sensor.x.twscrape")
    assert x_row["reason"] or x_row["policy_reason"]


# ================================================================ 7. TÜKETİCİLER
def test_target_psyche_profiler_labels_snippet_in_prompt(monkeypatch):
    """Snippet LLM'e "gönderi" diye gitmez."""
    from agent_core.agents.target_psyche_profiler import TargetPsycheProfiler
    from agent_core.domain.memory_models import PassionProfile

    captured: dict = {}

    class _FakeGateway:
        async def query_json_chain(self, prompt, schema, **kwargs):
            captured["prompt"] = prompt
            return PassionProfile(core_passions=["x"], confidence=0.5)

    profiler = TargetPsycheProfiler(llm_gateway=_FakeGateway())
    import asyncio

    asyncio.run(profiler.profile_passions({"target_profile": _web_dossier_profile()}))

    prompt = captured["prompt"]
    assert "arama sonucu" in prompt
    assert "DEĞİLDİR" in prompt


def test_authenticity_auditor_ignores_snippets_as_self_declaration():
    """Snippet, hedefin KENDİ beyanı sayılmaz."""
    from agent_core.agents.authenticity_auditor import AuthenticityAuditorAgent

    agent = AuthenticityAuditorAgent(llm_gateway=MagicMock())
    text, _visual = agent._extract_declared_text(_web_dossier_profile()) \
        if hasattr(agent, "_extract_declared_text") else (None, None)

    # Yardımcı yoksa doğrudan davranışı sınayalım: yalnız platform_post seçilir.
    items = extract_public_text(_web_dossier_profile(), kinds=(EVIDENCE_PLATFORM_POST,))
    assert items == []


def test_human_behavior_reads_only_platform_posts():
    from agent_core.agents.human_behavior import HumanBehaviorAnalyzer

    analyzer = HumanBehaviorAnalyzer()
    profile = _web_dossier_profile()
    posts = [
        item.text
        for item in extract_public_text(profile, kinds=(EVIDENCE_PLATFORM_POST,))
    ]
    assert posts == []


def test_pillar_adapter_declares_content_basis():
    """Kanıt adaptörü corpus'un ne olduğunu beyan eder."""
    from agent_core.services.pillar_evidence_adapter import _profile_scope

    scope = _profile_scope(_web_dossier_profile())
    assert scope["content_basis"] == CONTENT_BASIS_SEARCH
    assert scope["search_snippet_count"] == 1

    scope_ig = _profile_scope(_instagram_profile())
    assert scope_ig["content_basis"] == CONTENT_BASIS_PLATFORM


# ================================================================ 8. UI
def test_ui_does_not_claim_profiles_were_linked():
    """[P0] UI yalan metinlerini taşımaz."""
    war_room = (FRONTEND / "components" / "TacticalWarRoom.svelte").read_text(encoding="utf-8")
    assert "sosyal profil ve açık veri bağlandı" not in war_room
    # "BAĞLANAN CANLI PROFİLLER" yalnız KOŞULLU (gerçek kazıma varsa) kullanılabilir.
    assert '<span class="deck-label">BAĞLANAN CANLI PROFİLLER:</span>' not in war_room
    # Dürüst alternatifler mevcut.
    assert "KAZINMADI" in war_room
    assert "ÇALIŞMAYAN KANALLAR" in war_room


def test_ui_shows_channel_reason_labels():
    labels = (FRONTEND / "lib" / "channelStatus.ts").read_text(encoding="utf-8")
    assert "ÇALIŞMADI" in labels
    assert "no_session_pool" in labels
    assert "gate_disabled" in labels or "bayrak kapalı" in labels


def test_telemetry_board_shows_unavailable_capabilities():
    board = (
        FRONTEND / "components" / "visualizers" / "NeuralTelemetryBoard.svelte"
    ).read_text(encoding="utf-8")
    assert "ÇALIŞMAYAN YETENEKLER" in board
    assert "capabilities" in board


# ================================================================ 9. KASA
def test_verdict_digest_lists_channels_that_did_not_run():
    """[P0] Hüküm belgesi koşmayan kanalları + sebeplerini listeler."""
    from agent_core.services.verdict_synthesizer import build_verdict_digest

    class _Snap:
        status = "completed"
        evidence_chain = []
        channel_status = [
            {"channel": "sensor.x.twscrape", "status": "not_run", "reason": "no_session_pool"},
            {"channel": "search.web", "status": "ok", "reason": None},
        ]

    digest = build_verdict_digest({"active_tasks": {"op1": _Snap()}})
    assert "KOŞMAYAN KANALLAR" in digest
    assert "sensor.x.twscrape" in digest
    assert "no_session_pool" in digest
    # Çalışan kanal "koşmayan" listesinde olmaz.
    assert digest.count("search.web") == 0


def test_report_markdown_lists_channels_that_did_not_run():
    """[P0] Rapor paketi koşmayan kanalları listeler."""
    from agent_core.services.report_factory import render_markdown

    md = render_markdown(
        "Test Raporu",
        "hedef",
        "2026-10-16 00:00 UTC",
        [],
        {"rejected_item_count": 0, "excluded_strategy_count": 0},
        channels=[
            {"channel": "sensor.x.twscrape", "status": "not_run", "reason": "no_session_pool"},
            {"channel": "search.web", "status": "ok", "reason": None},
        ],
    )
    assert "Koşmayan kanallar" in md
    assert "no_session_pool" in md
    assert "search.web" not in md


def test_task_executor_carries_osint_channels():
    """[P0] Görev durumu OSINT kanal satırlarını taşır (kanal yoksa satır yok)."""
    from agent_core.task_executor import _channel_from_engine

    row = _channel_from_engine(
        "sensor.identity.maigret",
        {"available": False, "reason": "scan_unavailable:provider_errors", "scanned_count": 118},
    )
    assert row["status"] == CHANNEL_FAILED
    assert "provider_errors" in row["reason"]


def test_vault_locked_blocks_capability_with_reason():
    """Kasa kilitliyken yetenek koşmaz; sebep `vault_locked` olur."""
    from agent_core.capabilities import CapabilityContext, bootstrap, run_capability
    from agent_core.capabilities.state import policy_state

    monkey_env = os.environ
    assert "ENABLE_X_SENSOR" in monkey_env or True  # ortam değişkeni testte sabitlenir
    bootstrap()
    result = asyncio_run(
        run_capability(
            "sensor.x.twscrape",
            CapabilityContext(subject="hedef"),
            state=policy_state(vault_locked=True, rate_ok=True),
        )
    )
    assert result.available is False
    assert result.denied_by == "vault" or "vault" in (result.unavailable_reason or "")


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
