"""Kabul denetimi — “destekle devam etme” davranış testleri (A–I).

Ana hedef: kanıtsız başarı yasak; fakat görev sahipsiz bırakılmaz.
Bir engelde uygun alternatif denenir, alternatif yetersizse destek talebi
GERÇEKTEN oluşur (kayıt + ``AwaitingHumanEvent`` + log), destek gelince
görev ``resume_from`` ile kaldığı yerden devam eder.

Her test GERÇEK kontrol akışını kullanır (executor / search / vault_gate);
uydurma durum makinesi yoktur. Komutlar ve sonuçlar raporda kayıtlıdır.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from agent_core.capabilities import egress
from agent_core.agents.osint_investigator import OsintInvestigatorAgent
from agent_core.scraper.vault_gate import VaultLockedError
from agent_core.services.search_engine import SearchEngine, SearchResult
from agent_core.services.uncertainty_engine import UncertaintyReport
from agent_core.task_executor import AgentTimeoutError, PinealExecutor
from agent_core.schemas.telemetry import AwaitingHumanEvent

pytestmark = pytest.mark.asyncio


def _report(
    confidence: float = 0.95,
    *,
    suspicious: bool = False,
    reason: str = "yeterli kanıt",
) -> UncertaintyReport:
    return UncertaintyReport(
        is_suspicious=suspicious,
        confidence=confidence,
        reason=reason,
        data_score=0.9 if not suspicious else 0.3,
        breakdown={},
        no_decision=False,
    )


def _make_executor(evaluate) -> tuple[PinealExecutor, list]:
    events: list = []
    executor = PinealExecutor(emit_event_callback=events.append)
    executor.router.analyze = AsyncMock(
        return_value=type("R", (), {"agents": ["cognitive_profiler"]})()
    )
    executor.memory = MagicMock()
    executor.memory.merge_evidence = AsyncMock()
    executor.injector.fetch_active_rules = MagicMock(return_value={})
    if callable(evaluate):
        executor.uncertainty.evaluate = MagicMock(side_effect=evaluate)
    else:
        executor.uncertainty.evaluate = MagicMock(return_value=evaluate)
    return executor, events


class ResearchNote(BaseModel):
    summary: str = ""


class _CognitiveStyle(BaseModel):
    communication_tone: str = "analitik"
    complexity_level: str = "teknik"
    humor_style: str = "kuru mizah"
    social_orientation: str = "gözlemci"
    confidence: float = 0.9
    data_confidence: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# A. Birincil araç hata verir → izinli alternatif denenir
# ─────────────────────────────────────────────────────────────────────────────


async def test_a_primary_tool_fails_alternative_serves():
    # Ücretsiz omurga: SearXNG birincil → DuckDuckGo izinli alternatif.
    # (Anahtarla çalışan Tavily grubu 'if not tasks' dışında: alternatif
    # omurganın kendi içinde, asyncio.gather ile denenir.)
    engine = SearchEngine()
    engine.set_policy({"vault_locked": False})
    engine._searxng_enabled = lambda: True
    calls = {"searxng": 0, "duckduckgo": 0}

    async def broken_searxng(query, num_results, client=None):
        calls["searxng"] += 1
        raise RuntimeError("searxng_down")

    async def ok_duckduckgo(query, num_results, client=None):
        calls["duckduckgo"] += 1
        return [
            SearchResult(
                query=query,
                content="kaynak içerik",
                source_url="https://kaynak.test/1",
                provider="duckduckgo",
            )
        ]

    engine._search_searxng = broken_searxng
    engine._search_duckduckgo = ok_duckduckgo

    outcome = await engine.search("izinli alternatif sorgusu")
    assert calls["searxng"] == 1, "birincil sağlayıcı denenmedi"
    assert calls["duckduckgo"] == 1, "izinli alternatif denenmedi"
    assert outcome.available is True
    assert outcome.results and outcome.results[0].provider == "duckduckgo"
    # Hata da gizlenmez: PARTIAL + hata kodu taşır (sahte temizlik yok).
    assert outcome.status == "PARTIAL"
    assert outcome.error


# ─────────────────────────────────────────────────────────────────────────────
# B. Alternatif de başarısız → destek talebi gerçekten oluşturulur
# ─────────────────────────────────────────────────────────────────────────────


async def test_b_alternative_fails_real_support_request_created():
    executor, events = _make_executor(
        lambda result, agent_name: _report(
            0.95, suspicious=True, reason="kanıt şüpheli"
        )
    )
    # Alternatif doğrulama (deep research) de başarısız:
    executor._deep_research = AsyncMock(side_effect=RuntimeError("research_down"))
    executor.agents["cognitive_profiler"].execute = AsyncMock(
        return_value=_CognitiveStyle()
    )

    status = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_b"
    )

    # 1) Gerçek destek kaydı — sahipli, seçenekli, açık sonraki adımla:
    assert status.support_requests, "destek talebi oluşmadı"
    entry = status.support_requests[0]
    assert entry["status"] == "pending"
    assert entry["owner"] == "cognitive_profiler"
    assert entry["options"] and entry["next_action"]
    # 2) Operatör olayı WS akışına girdi (AwaitingHumanEvent):
    human_events = [e for e in events if isinstance(e, AwaitingHumanEvent)]
    assert human_events, "AwaitingHumanEvent yayınlanmadı"
    assert human_events[0].options == entry["options"]
    # 3) Koşu dürüst: gizli başarı yok, mühür sorumlulukta:
    run = status.agent_runs["cognitive_profiler"]
    assert run.status == "halted"
    assert run.error_code == "SUSPICIOUS_EVIDENCE"
    assert run.responsibility["integrity"]["claimed"] == "halted_evidence"
    assert any(
        r.get("agent") == "cognitive_profiler" for r in status.evidence_chain
    ) is False, "başarısız koşu kanıt zincirine sahte kanıt olarak girdi"


# ─────────────────────────────────────────────────────────────────────────────
# C. Destek sonucu gelir → görev kaldığı yerden devam eder
# ─────────────────────────────────────────────────────────────────────────────


async def test_c_support_arrives_task_resumes_where_it_left_off(monkeypatch):
    class Route(BaseModel):
        agents: list[str] = ["cognitive_profiler", "depth_analyst"]

    plan: Dict[str, float] = {
        "cognitive_profiler": 0.9,
        "depth_analyst": 0.1,  # düşük güven + graceful kapalı → görev durur
    }
    executor, events = _make_executor(
        lambda result, agent_name: _report(plan.get(agent_name, 0.95))
    )
    # Aşağılama davranışı KAPALI: kritik-agents dışındaki bu ajan da
    # düşük güvende görevi durdurur (config/decision_config.yaml ile aynı
    # pineal_7pillar: graceful_degradation:false semantiği).
    # DİKKAT: config süreç-geneli paylaşıldır → monkeypatch otomatik geri alır.
    _depth_cfg = executor.config.get_agent_config("depth_analyst")
    monkeypatch.setattr(_depth_cfg, "graceful_degradation", False)
    executor.router.analyze = AsyncMock(return_value=Route())
    counts: Dict[str, int] = {"cognitive_profiler": 0, "depth_analyst": 0}

    async def cog_mock(*args, **kwargs):
        counts["cognitive_profiler"] += 1
        return _CognitiveStyle()

    async def depth_mock(*args, **kwargs):
        counts["depth_analyst"] += 1
        return _CognitiveStyle()

    executor.agents["cognitive_profiler"].execute = cog_mock
    executor.agents["depth_analyst"].execute = depth_mock

    # 1. koşu: cognitive tamamlanır, depth_analyst güven yetersiz → HALT
    first = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_c"
    )
    assert first.status == "halted_evidence", first.status
    assert "cognitive_profiler" in first.completed_agents
    assert "depth_analyst" not in first.completed_agents
    assert first.support_requests and first.support_requests[0]["status"] == "pending"
    assert first.support_requests[0]["owner"] == "depth_analyst"
    assert any(isinstance(e, AwaitingHumanEvent) for e in events)
    assert counts == {"cognitive_profiler": 1, "depth_analyst": 1}

    # DESTEK GELDİ: operatör yanıtı KALICI KAYDA GEÇTİ → önceki TaskStatus
    # ile devam. (HTTP yolunda bu adımı gerçek rota yapar:
    # backend/checkpoint_store.record_support_response — B0 E2E paketinde
    # uçtan uca doğrulanır.) B0 sözleşmesi: kayıtsız resume REDDEDİLİR;
    # bu yüzden girişim ÖNCESİ ilgili talep çözülmüş olmalıdır.
    _req = first.support_requests[0]
    assert _req["blocks_resume"] is True and _req["status"] == "pending"
    _req.update(
        status="resolved",
        approved=True,
        responses=[{"action": "provide", "note": "destek sağlandı", "by": "operator"}],
        resolved_at="2026-10-14T00:00:00+00:00",
        resolution="verified_operator_response",
    )
    plan["depth_analyst"] = 0.93
    second = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}},
        "task_c2",
        resume_from=first,
    )

    # Tamamlanan ajan YENİDEN ÇALIŞMAZ (yan etki tekrarı yok — I da burada):
    assert counts["cognitive_profiler"] == 1, "tamamlanan ajan tekrar çalıştırıldı"
    assert counts["depth_analyst"] == 2, "destek sonrası engelli ajan devam etmedi"
    assert "cognitive_profiler" in second.completed_agents
    assert "depth_analyst" in second.completed_agents
    # Yutulan çıktı input_data'ya geri yüklendi (kaldığı yerden):
    ingested = second.ingested_outputs.get("cognitive_profiler", {})
    assert "cognitive" in ingested, second.ingested_outputs
    # Destek talebi çözüldü:
    assert all(r["status"] == "resolved" for r in second.support_requests)
    assert second.status in ("completed", "partially_completed"), second.status
    # Kanıt zinciri devralındı + yeni kanıt eklendi (boşaltılmadı):
    assert len(second.evidence_chain) >= len(first.evidence_chain)


# ─────────────────────────────────────────────────────────────────────────────
# D. Kanıt yetersiz → başarı verilmez; ek doğrulama başlatılır
# ─────────────────────────────────────────────────────────────────────────────


async def test_d_insufficient_evidence_starts_extra_verification():
    executor, _events = _make_executor(
        lambda result, agent_name: _report(
            0.9, suspicious=True, reason="şüpheli örüntü"
        )
    )
    executor.agents["cognitive_profiler"].execute = AsyncMock(
        return_value=_CognitiveStyle()
    )
    executor._deep_research = AsyncMock(
        return_value=ResearchNote(summary="ikincil doğrulama")
    )

    status = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_d"
    )

    executor._deep_research.assert_awaited_once()
    # Ek doğrulama kanıt zincirine kendi kimliğiyle girer:
    assert any(r.get("agent") == "deep_research" for r in status.evidence_chain)
    # Kanıt yetersizse "tamamlanmış" gösterilmez:
    run = status.agent_runs["cognitive_profiler"]
    assert run.status != "completed" or run.decision_grade is not None
    # Ek doğrulama BAŞARILI olunca destek talebi açılmaz:
    assert status.support_requests == []


# ─────────────────────────────────────────────────────────────────────────────
# E. Kasa kilitlidir → dış çağrı yapılmaz; yetki desteği beklenir
# ─────────────────────────────────────────────────────────────────────────────


async def test_e_locked_vault_no_external_call_and_authority_support(
    monkeypatch, caplog
):
    # 1) Arama omurgası: kilit TEK bayt dışarı çıkmaz.
    egress._reset_for_tests()
    engine = SearchEngine(tavily_key="t-v")  # policy boş → dar taraf: KİLİTLİ
    with caplog.at_level(logging.WARNING):
        outcome = await engine.search("gizli_hedef_aramasi")
    assert outcome.status == "VAULT_LOCKED"
    assert outcome.available is False
    assert egress.egress_attempts() == (), "kilitliyken istemci açıldı"
    assert "KASA KİLİTLİ" in caplog.text
    # Hassas bilgi denetim kaydında YOK (arama terimi sızmadı):
    assert "gizli_hedef_aramasi" not in caplog.text

    # 2) osint aiohttp yolu: istek HİÇ oluşturulmaz.
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_VAULT_FILE", "/nonexistent/vault.json")
    monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-test-key-123")
    from agent_core.scraper import vault_gate

    vault_gate._auth_ctx.set(None)

    class _BoomSession:
        def __init__(self, *a, **k):
            raise AssertionError("kilitliyken aiohttp oturumu açıldı")

    monkeypatch.setattr(
        "agent_core.agents.osint_investigator.aiohttp.ClientSession", _BoomSession
    )
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        profile = await OsintInvestigatorAgent().execute(
            {"target_profile": {"username": "hedef_kullanici"}}
        )
    assert profile.fallback_reason == "vault_locked"
    assert profile.error_code == "VAULT_LOCKED"
    assert profile.data_confidence is False
    assert "hedef_kullanici" not in caplog.text  # denetim izi hassas içerik taşımaz
    assert "osint" in caplog.text

    # 3) Görev seviyesi: VaultLockedError → destek talebi (yetki bekleniyor).
    executor, events = _make_executor(_report())
    executor.agents["cognitive_profiler"].execute = AsyncMock(
        side_effect=VaultLockedError("VAULT_LOCKED purpose=search")
    )
    status = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_e"
    )
    assert status.support_requests
    entry = status.support_requests[0]
    assert entry["options"] == ["open_vault", "grant_boundary_authority"]
    assert any(isinstance(e, AwaitingHumanEvent) for e in events)


# ─────────────────────────────────────────────────────────────────────────────
# F. Yetki sağlanır → eski yetki işareti kullanılmadan yeniden kontrol
# ─────────────────────────────────────────────────────────────────────────────


async def test_f_authorization_is_request_scoped_and_rechecked(monkeypatch):
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_VAULT_FILE", "/nonexistent/vault.json")
    from agent_core.scraper import vault_gate

    vault_gate._auth_ctx.set(None)
    egress._reset_for_tests()

    seen: dict[str, Any] = {}

    async def authorized_child():
        vault_gate.mark_vault_egress_authorized()  # sınır kapısı bu görev için açtı
        async with egress.open_client(
            purpose="osint", target="https://child.test"
        ):
            pass
        seen["child_attempts"] = [a.target for a in egress.egress_attempts()]

        async def grandchild():
            # Torun görev: işaret çocuk görevden ÖNCE kopyalanır → yetki devri
            async with egress.open_client(purpose="osint", target="https://gc.test"):
                pass
            return [a.target for a in egress.egress_attempts()]

        seen["grandchild"] = await asyncio.ensure_future(grandchild())

    # 1) Yetkili görev: mark yalnız kendi bağlamında — çocuk VE torun görür.
    await asyncio.ensure_future(authorized_child())
    assert seen["child_attempts"] == ["https://child.test"]
    assert seen["grandchild"] == ["https://child.test", "https://gc.test"]

    # 2) Sonradan kilit: YENİ görev eski işarete güvenmez → yeniden kontrol → ret.
    with pytest.raises(VaultLockedError):
        async with egress.open_client(purpose="osint", target="https://stale.test"):
            pass

    # 3) Görev bitince işaret SÜZÜLMÜŞ: test/iş parçacığı bağlamı temiz.
    assert vault_gate.vault_egress_authorized() is False
    assert egress.egress_attempts() == ()


# ─────────────────────────────────────────────────────────────────────────────
# G. Süre/maliyet sınırı → sınırsız tekrar yok; sahipli + açık sonraki adım
# ─────────────────────────────────────────────────────────────────────────────


async def test_g_time_and_cost_limits_hold_without_unbounded_retry():
    calls = {"n": 0}

    async def timing_out(*args, **kwargs):
        calls["n"] += 1
        raise AgentTimeoutError("ajan duvar saati aşıldı")

    executor, events = _make_executor(_report())
    executor.agents["cognitive_profiler"].execute = timing_out
    status = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_g_time"
    )
    run = status.agent_runs["cognitive_profiler"]
    assert run.status == "timed_out"
    assert calls["n"] == 1, "sınırsız tekrar var"
    # Sahipli + açık sonraki adım + destek talebi:
    assert run.responsibility is not None
    assert "agent:cognitive_profiler" in run.responsibility["attempted_paths"]
    assert run.responsibility["next_action"]
    assert any(
        "extend_timebox" in r["options"] for r in status.support_requests
    )

    # Maliyet sınırı: SpendCapExceeded → kırılgan retry yok, sahipli bekleme.
    from agent_core.services.llm_gateway import SpendCapExceeded

    cap_calls = {"n": 0}

    async def spend_capped(*args, **kwargs):
        cap_calls["n"] += 1
        raise SpendCapExceeded("harcama üst limiti aşıldı")

    executor2, _ev2 = _make_executor(_report())
    executor2.agents["cognitive_profiler"].execute = spend_capped
    status2 = await executor2.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_g_cost"
    )
    assert cap_calls["n"] == 1
    run2 = status2.agent_runs["cognitive_profiler"]
    assert run2.error_code == "SpendCapExceeded"
    assert run2.responsibility["next_action"]
    assert any(
        "raise_spend_cap" in r["options"] for r in status2.support_requests
    )


# ─────────────────────────────────────────────────────────────────────────────
# H. Eşzamanlı iki görev → yetki ve deneme izleri karışmaz
# ─────────────────────────────────────────────────────────────────────────────


async def test_h_concurrent_tasks_isolate_authority_and_attempts(monkeypatch):
    monkeypatch.setenv("PINEAL_ENV", "production")
    monkeypatch.setenv("PINEAL_VAULT_FILE", "/nonexistent/vault.json")
    from agent_core.scraper import vault_gate

    vault_gate._auth_ctx.set(None)
    egress._reset_for_tests()

    async def marked_task():
        vault_gate.mark_vault_egress_authorized()
        async with egress.open_client(purpose="osint", target="https://a.test"):
            pass
        return [a.target for a in egress.egress_attempts()]

    async def unmarked_task():
        try:
            async with egress.open_client(purpose="search", target="https://b.test"):
                pass
        except VaultLockedError:
            return "locked"
        return "leaked"

    first, second = await asyncio.gather(
        asyncio.ensure_future(marked_task()),
        asyncio.ensure_future(unmarked_task()),
    )
    # Yetki ve izler ayrık: işaretli görev yalnız kendi izini görür,
    # işaretsiz görev kilitli kalır (iz sızmaz, yetki sızmaz).
    assert first == ["https://a.test"]
    assert second == "locked"
    # Ana (test) bağımlılığına hiçbir iz/izin sızmadı:
    assert egress.egress_attempts() == ()
    assert vault_gate.vault_egress_authorized() is False


# ─────────────────────────────────────────────────────────────────────────────
# I. Aynı görev yeniden denenir → tamamlanmış yan etkiler tekrarlanmaz
# ─────────────────────────────────────────────────────────────────────────────


async def test_i_rerun_skips_completed_side_effects():
    class Route(BaseModel):
        agents: list[str] = ["cognitive_profiler"]

    executor, _events = _make_executor(_report())
    executor.router.analyze = AsyncMock(return_value=Route())
    calls = {"n": 0}

    async def counting(*args, **kwargs):
        calls["n"] += 1
        return _CognitiveStyle()

    executor.agents["cognitive_profiler"].execute = counting

    first = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}}, "task_i"
    )
    assert calls["n"] == 1
    assert "cognitive_profiler" in first.completed_agents

    second = await executor.execute_task(
        {"target_profile": {"bio": "x", "posts": []}},
        "task_i2",
        resume_from=first,
    )
    # Yan etki (execute çağrısı) TEKRARLANMADI:
    assert calls["n"] == 1, "tamamlanan yan etki gereksiz yine çalıştı"
    assert "cognitive_profiler" in second.completed_agents
    assert len(second.evidence_chain) >= 1
    # Aynı görev resume ile de sahte-completed DEĞİL: kanıt devralınmış.
    assert second.status in ("completed", "partially_completed"), second.status


# ─────────────────────────────────────────────────────────────────────────────
# C (CLI halkası): run_task "resume" anahtarını execute_task'a geçirir
# ─────────────────────────────────────────────────────────────────────────────

import json
import os
import subprocess
import sys


def _cli_run(payload: dict, tmp_path):
    repo = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return subprocess.run(
        [sys.executable, os.path.join(repo, "scripts", "run_task.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(tmp_path),
    )


async def test_c_cli_resume_passthrough(tmp_path):
    """Destek sonucu CLI'dan uygulanır: resume → RESUME akışı çalışır."""
    base = {
        "url": "",
        "rituals": [],
        "playlist": [],
        "envies": [],
        "target_profile": {"username": "", "bio": "x", "posts": []},
    }
    proc1 = _cli_run(dict(base), tmp_path)
    assert proc1.returncode == 0, proc1.stderr[-800:]
    line1 = proc1.stdout.strip().splitlines()[-1]
    data1 = json.loads(line1)
    # Ek uyumlu alanlar CLI çıktısında da görünür (istemci kırılmaz):
    assert "support_requests" in data1
    assert "ingested_outputs" in data1

    # Destek/sınır düzeltildi → operatör önceki TaskStatus ile devam ettirir:
    payload2 = dict(base)
    payload2["resume"] = data1
    proc2 = _cli_run(payload2, tmp_path)
    assert proc2.returncode == 0, proc2.stderr[-800:]
    # run_task logları stderr'e akar (sözleşme): RESUME akışı orada görünür.
    assert "RESUME:" in proc2.stderr, proc2.stderr[-2000:]
    data2 = json.loads(proc2.stdout.strip().splitlines()[-1])
    assert data2["status"] in (
        "completed",
        "partially_completed",
        "halted_evidence",
        "halted_critical",
        "timed_out",
        "failed",
    )
