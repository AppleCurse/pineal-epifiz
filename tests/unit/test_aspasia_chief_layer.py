"""ASPASIA TRUE CHIEF LAYER — goal transport, kanonik sonuc dongusu, mismatch.

Zincir kabul kriteri:
  USER -> ASPASIA(intent+goals) -> COMMAND GATEWAY -> ORCHESTRATOR
       -> COGNITIVE ROUTER(goal-aware, evidence-gated) -> agents
ve  RESULT -> CanonicalMemory -> ASPASIA -> kullanici.

Kritik sinirler (testlerin kanitladigi):
- goal != agent listesi: router kanit/kabiliyet kapilarini korur; goal yalniz
  kullanici tercih daraltmasi saglar; semsiye/bos goal = eski davranis.
- Uydurma goal sema duzeyinde reddedilir; red dispatch uretmez.
- Sonuc icerigi icin paralel store YOK: tek kanonik kaynak CanonicalMemory.
- Kanit yoksa ZORLA ajan eklenmez: honest skip notu, sahte yurutme yok.
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import agent_core.services.llm_gateway as gwl
from agent_core.aspasia.interface import (
    AspasiaCommandGateway,
    FINAL_TASK_STATUSES,
    MissionResultReader,
    _GOAL_IDS,
    build_oversight_digest,
)
from agent_core.services.canonical_memory import CanonicalMemory, MemoryCorruptedError
from agent_core.services.cognitive_router import GOAL_FOCUS, CognitiveRouter
from agent_core.services.llm_gateway import LLMGateway


def run(coro):
    return asyncio.run(coro)


TARGET_INPUT = {
    "target_profile": {"username": "u1", "bio": "merhaba", "posts": ["p1"]},
    "user_profile": {"bio": "user-bio"},
}


def _plan(input_data):
    return run(CognitiveRouter().analyze(input_data))


# ----------------------------------------------------------- GOAL -> PLAN ---
def test_goal_vocabulary_single_source_no_drift():
    # Aspasia semasi router'in GOAL_FOCUS'indan TURETILIR; ikinci bir
    # sozluik yok — ikisi ayni olmak zorunda.
    assert _GOAL_IDS == tuple(GOAL_FOCUS.keys())
    # Sozlukte yalniz GERCEK router/registry uzmanlari var; executor
    # registry'sindeki ajan adlariyla kontrol edilir.
    import agent_core.task_executor as tex
    import inspect
    src = inspect.getsource(tex.PinealExecutor.__init__)
    for agents in GOAL_FOCUS.values():
        for a in agents:
            assert f'"{a}"' in src or f"'{a}'" in src or a in src, a


def test_no_goals_behaves_exactly_as_before():
    plan = _plan(dict(TARGET_INPUT))
    assert plan.agents == ["mirror_truth", "autonomous_verifier", "human_behavior",
                           "passion_mapper", "friction_detector", "cognitive_profiler",
                           "resonance_calc", "pattern_interrupt", "resonance_synthesizer"]


def test_goal_narrows_preference_legs_not_policy_legs():
    plan = _plan({**TARGET_INPUT, "aspasia_goals": ["behavioral_assessment"]})
    assert "human_behavior" in plan.agents
    # Daraltılan tercih bacakları plan dışı:
    assert "passion_mapper" not in plan.agents
    assert "friction_detector" not in plan.agents
    # POLICY bacagi (teyit) ve ayna ASLA dusmez:
    assert "autonomous_verifier" in plan.agents
    assert "mirror_truth" in plan.agents
    assert any("Aspasia amaç seti" in part for part in plan.reasoning.split(" | "))


def test_umbrella_goal_equals_full_plan():
    full = _plan(dict(TARGET_INPUT)).agents
    plan = _plan({**TARGET_INPUT, "aspasia_goals": ["profile_analysis", "contradiction_detection"]})
    assert plan.agents == full


def test_evidence_gate_beats_goal_honest_skip():
    # contradiction goal + gorsel kanit YOK -> authenticity ZORLA eklenmez,
    # reasoning'de dürüst skip notu var (sahte denetim yok).
    plan = _plan({**TARGET_INPUT, "aspasia_goals": ["contradiction_detection"]})
    assert "authenticity_auditor" not in plan.agents
    assert "ATLANDI" in plan.reasoning and "honest skip" in plan.reasoning
    # Kanit GELIRSE denetim goal'dan bagimsiz zaten planin parcasidir.
    with_ev = _plan({**TARGET_INPUT, "visual_evidence": {"images": ["x"]},
                     "aspasia_goals": ["behavioral_assessment"]})
    assert "authenticity_auditor" in with_ev.agents


def test_unknown_goal_never_changes_plan():
    plan = _plan({**TARGET_INPUT, "aspasia_goals": ["jailbreak_please", "autonomous_verification"]})
    assert "yok sayıldı" in plan.reasoning
    assert "autonomous_verifier" in plan.agents
    # Uydurma goal baska ajanlari EKLEMEZ/CIKARMAZ: semsiye goal gibi
    # (unknown daraltma yapmaz; bilinen tek goal 'verifier' zaten policy bacagi)
    assert "authenticity_auditor" not in plan.agents
    garbage = _plan({**TARGET_INPUT, "aspasia_goals": "not-a-list"})
    assert garbage.agents == _plan(dict(TARGET_INPUT)).agents


# --------------------------------------------------- GATEWAY GOAL TRANSPORT ---
class FakeGatewayHttp:
    def __init__(self, behavior=None):
        self.calls: list = []
        self._behavior = behavior or (lambda n: None)

    def factory(self, *, base_url, api_key, max_retries=0, **kw):
        outer = self

        class _C:
            def __init__(self, bu):
                self.chat = SimpleNamespace(completions=self._Comp(bu, outer))

            class _Comp:
                def __init__(self, bu, owner):
                    self.bu, self.owner = bu, owner

                async def create(self, **kwargs):
                    self.owner.calls.append((self.bu, kwargs))
                    outcome = self.owner._behavior(len(self.owner.calls))
                    if isinstance(outcome, Exception):
                        raise outcome
                    content, model = '{"a": 1}', kwargs["model"]
                    if isinstance(outcome, dict):
                        content = outcome.get("content", content)
                        model = outcome.get("model", model)
                    return SimpleNamespace(
                        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
                        model=model,
                        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                    )

        return _C(base_url)


@pytest.fixture()
def clean_env(monkeypatch):
    fake = FakeGatewayHttp()
    monkeypatch.setattr(gwl, "AsyncOpenAI", lambda **kw: fake.factory(**kw))
    for k in ("OPENROUTER_API_KEY", "GROQ_API_KEY", "NOUS_API_KEY", "CEREBRAS_API_KEY",
              "DEEPSEEK_API_KEY", "PINEAL_ALLOW_PAID_ESCALATION", "USE_LOCAL_LLM",
              "LIVE_LLM_E2E", "PINEAL_ROUTER_LIVE", "OPENROUTER_MAX_SPEND_USD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    return fake


def _gw():
    gw = LLMGateway()
    gw.live_unlocked = True
    return gw


def test_goals_survive_intent_to_dispatch(clean_env):
    gw = _gw()
    launched: list = []
    commands = AspasiaCommandGateway(dispatch=lambda spec: launched.append(spec) or "op_t1",
                                     gateway=gw)
    clean_env._behavior = lambda n: {"content": json.dumps({
        "intent": "run_profile_analysis",
        "target_url": "https://www.instagram.com/someuser/",
        "goals": ["profile_analysis", "contradiction_detection", "behavioral_assessment"],
    })}
    res = run(commands.submit("profili incele, çelişkileri bul ve davranışsal çıkar: "
                              "https://www.instagram.com/someuser/", client_id="cX"))
    assert res.accepted and res.task_id == "op_t1"
    assert launched[0]["goals"] == ["profile_analysis", "contradiction_detection",
                                    "behavioral_assessment"]
    assert launched[0]["client_id"] == "cX"
    # audit de amaci tasir (denetlenebilirlik):
    assert commands.audit()[-1]["goals"] == launched[0]["goals"]


def test_fabricated_goal_blocks_whole_intent(clean_env):
    gw = _gw()
    launched: list = []
    commands = AspasiaCommandGateway(dispatch=lambda spec: launched.append(spec), gateway=gw)
    clean_env._behavior = lambda n: {"content": json.dumps({
        "intent": "run_profile_analysis",
        "target_url": "https://www.instagram.com/someuser/",
        "goals": ["deep_mind_reading"],
    })}
    res = run(commands.submit("su profile bak: https://www.instagram.com/someuser/", client_id="c1"))
    assert not res.accepted and res.reason == "intent_unavailable"
    assert launched == []  # uydurma goal -> sifir dispatch


def test_intent_prompt_lists_only_real_goal_ids(clean_env):
    gw = _gw()
    commands = AspasiaCommandGateway(dispatch=lambda spec: None, gateway=gw)
    clean_env._behavior = lambda n: {"content": json.dumps({"intent": "none"})}
    run(commands.submit("selam", client_id="c1"))
    prompt = clean_env.calls[0][1]["messages"][-1]["content"]
    for goal in GOAL_FOCUS:
        assert goal in prompt
    assert "AJAN ISMI YAZMAZSIN" in prompt  # rol siniri talimatta da sabit


def test_api_dispatch_passes_goals_into_mission_payload(monkeypatch):
    # ORCHESTRATOR BAGI: _aspasia_command_dispatch, goals'i InitiatePayload'a
    # koyup run_mission'a aynen aktarmali (amaç kaybı fix'inin api bacagi).
    import backend.api as api

    captured: dict = {}
    room = {"mission_tasks": {}, "lifecycle": None}

    class _Reg:
        def transition(self, task_id, state):
            captured["transition"] = (task_id, state)

    async def fake_run_mission(req, task_id):
        captured["req"] = req

    monkeypatch.setattr(api, "get_room", lambda cid: room)
    monkeypatch.setattr(api, "_lifecycle", lambda r: _Reg())
    monkeypatch.setattr(api, "run_mission", fake_run_mission)
    monkeypatch.setattr(api, "broadcast_log", lambda *a, **k: None)

    async def _main():
        return api._aspasia_command_dispatch({
            "client_id": "c1",
            "target_url": "https://www.instagram.com/u/",
            "goals": ["contradiction_detection"],
        })

    task_id = run(_main())
    req = captured["req"]
    assert req.aspasia_goals == ["contradiction_detection"]
    assert captured["transition"][1] == "processing"
    assert task_id and task_id.startswith("op_")
    # run_mission'in kuracagi payload'da goal alani var (kaynak kilidi):
    src = Path("backend/api.py").read_text(encoding="utf-8")
    assert '"aspasia_goals": list(req.aspasia_goals or [])' in src


def test_initiate_payload_backward_compatible():
    import backend.api as api
    old = api.InitiatePayload(client_id="c", url="u", rituals="", playlist="", envies="")
    assert old.aspasia_goals == []  # eski istemciler aynen calisir


# -------------------------------------------------- CANONICAL RESULT LOOP ----
def test_mission_result_reader_real_canonical_memory(tmp_path):
    memory = CanonicalMemory(storage_path=str(tmp_path))
    # Kanonik sema: guven, result.icinde ya$ar (_calculate_overall_confidence).
    run(memory.merge_evidence("op_x1", [
        {"agent": "human_behavior", "result": {"confidence": 0.8}},
        {"agent": "mirror_truth", "result": {"confidence": 0.6}},
    ]))
    reader = MissionResultReader()
    doc = reader.read(SimpleNamespace(memory=memory), "op_x1")
    assert doc["state"] == "ok"
    assert doc["agents"] == ["human_behavior", "mirror_truth"]
    assert doc["evidence_count"] == 2
    assert doc["overall_confidence"] == pytest.approx(0.7)
    # Eksik kayit -> 'missing' (bosluk uydurulmaz), executor wrapper'i da calisir
    assert reader.read(SimpleNamespace(memory=memory), "op_yok")["state"] == "missing"


def test_corrupted_canonical_memory_is_not_silenced(tmp_path):
    memory = CanonicalMemory(storage_path=str(tmp_path))
    (tmp_path / "op_bad.json").write_text("{bozuk json", encoding="utf-8")
    with pytest.raises(MemoryCorruptedError):
        memory.get_task_memory("op_bad")
    doc = MissionResultReader().read(SimpleNamespace(memory=memory), "op_bad")
    assert doc["state"] == "corrupted"
    assert doc["error"]  # Aspasia'ya 'kurtarma gerekir' olarak yansir


def test_latest_finished_task_and_stale_flag():
    room = {"active_tasks": {
        "t1": SimpleNamespace(task_id="t1", status="completed", planned_agents=[],
                              completed_agents=["a"], current_agent=None, agent_runs={}),
    }}
    assert MissionResultReader.latest_finished_task_id(room) == "t1"
    live = {"active_tasks": {"t2": SimpleNamespace(
        task_id="t2", status="processing", planned_agents=["a"], completed_agents=[],
        current_agent="a", agent_runs={})}}
    assert MissionResultReader.latest_finished_task_id(live) is None
    from agent_core.aspasia.interface import AgentInspector
    st = AgentInspector(None).run_status(room)
    assert st["is_final"] is True and st["status"] == "completed"
    assert FINAL_TASK_STATUSES >= {"completed", "failed", "halted_critical"}


def test_digest_carries_canonical_result_and_stale_marker(tmp_path):
    memory = CanonicalMemory(storage_path=str(tmp_path))
    run(memory.merge_evidence("op_fin", [
        {"agent": "friction_detector", "result": {"r": 1}, "confidence": 0.9},
    ]))
    executor = SimpleNamespace(memory=memory, agents={"friction_detector": object()})
    room = {"active_tasks": {"op_fin": SimpleNamespace(
        task_id="op_fin", status="completed", planned_agents=["friction_detector"],
        completed_agents=["friction_detector"], current_agent=None, agent_runs={},
    )}}

    class _NoGw:  # routing okunamaz -> digest yalniz kanonik bloklari tasir
        pass

    digest = build_oversight_digest(_NoGw(), room, executor, None)
    assert "SONUÇ[op_fin]" in digest and "friction_detector" in digest
    assert "BAYAT-snapshot" in digest and "CanonicalMemory" in digest


def test_chat_prompt_shows_canonical_and_mismatch_detail(tmp_path):
    from agent_core.aspasia.aspasia_chief import AspasiaChief

    memory = CanonicalMemory(storage_path=str(tmp_path))
    run(memory.merge_evidence("op_last", [
        {"agent": "human_behavior", "result": {"r": 1}, "confidence": 0.85},
    ]))
    room = {"active_tasks": {"op_last": SimpleNamespace(
        task_id="op_last", status="completed", planned_agents=["human_behavior"],
        completed_agents=["human_behavior"], current_agent=None, agent_runs={},
    )}}
    captured: dict = {}

    class _Gw:
        call_log = [{"model": "m1", "requested_model": "claude-sonnet-5",
                     "actual_model": "other/model", "provider": "openrouter",
                     "error": "MODEL_SUBSTITUTION_DENIED: requested 'claude-sonnet-5' "
                              "but provider returned 'other/model'"}]

        def get_agent_chain(self, agent, task):
            return ["x-model"]

        def agent_route_variants(self, model):
            return []

        AGENT_CHAINS = {"friction_detector": ["x-model"]}

        def budget_status(self):
            return {"spend_usd": 0.0, "reserved_usd": 0.0, "cap_usd": None,
                    "active_reservations": 0}

        async def query_chain(self, **kwargs):
            captured.update(kwargs)
            return "ok"

    chief = AspasiaChief(llm_gateway=_Gw(), executor=SimpleNamespace(
        memory=memory, agents={}))
    chief._executor = SimpleNamespace(memory=memory, agents={})
    run(chief.chat("analiz sonucu ne?", room_state=room))
    prompt = captured["prompt"]
    # Faz-4: kanonik sonuc chat'e kadar geldi...
    assert "SONUÇ[op_last]" in prompt and "human_behavior" in prompt
    # Faz-5: requested != actual ayrintisi artik okunabilir.
    assert "SUBSTITUTION DENIED" in prompt and "other/model" in prompt


# ------------------------------------------------------- FRONTEND BRIDGE -----
#: [P6 · 2026-10-18] Sözleşme artık CANLI arayüze bağlıdır.
#: `UnifiedCompactPanel.svelte` (ölü) "komut önce, chat fallback" akışını
#: taşıyordu; PR #143'te yenilen kokpitte bu akış KURULMADI. Sözleşme ölü
#: dosyayı koruyup yeşil görünmemeli: yaşayan yüzey ne yapıyorsa O ölçülür.
#:   · canlı kokpit ASPASIA sohbetini /api/aspasia/chat üzerinden yapar
#:   · /api/aspasia/command backend'de DOKÜMANTED bir uç olarak durur
#:     (README:114) — UI henüz onu çağırmıyor; bu bir ÜRÜN boşluğudur,
#:     ölü kod değil (raporda kayıtlı).
COCKPIT = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"
           / "AtlasPinealCockpit.svelte").read_text(encoding="utf-8")


def test_frontend_natural_language_uses_aspasia_chat_endpoint():
    """Canlı arayüz ASPASIA'yı sohbet ucundan besler."""
    assert "/api/aspasia/chat" in COCKPIT, "canlı arayüz ASPASIA sohbetini çağırmıyor"


def test_aspasia_command_endpoint_is_still_documented_and_live():
    """Komut ucu backend'de yaşıyor (ölü kod DEĞİL); UI çağrısı yok."""
    from backend.api import app

    routes = {getattr(r, "path", "") for r in app.routes}
    assert "/api/aspasia/command" in routes
    assert "/api/aspasia/chat" in routes
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    assert "/api/aspasia/command" in readme, "doküman uçtan koptu (koyduğum şaşırtmasın)"


# --------------------------------------------------------- SECURITY GATE -----
def test_no_mutation_surface_added():
    src = Path("agent_core/aspasia/interface.py").read_text(encoding="utf-8")
    for token in (".set_key(", "record_success(", "record_failure(", "AsyncOpenAI",
                  "httpx", "open(", "write_text"):
        assert token not in src, f"interface.py yazma yuzeyi iceremez: {token}"
    # goal sozluğünün tek kaynagi router; interface'te hardcode ajan listesi yok:
    assert '"authenticity_auditor"' not in src


def test_intent_schema_rejects_fabricated_goal_directly():
    with pytest.raises(ValidationError):
        from agent_core.aspasia.interface import AspasiaIntent
        AspasiaIntent(intent="run_profile_analysis", goals=["impossible_power"])
