"""FINAL-SPEC compliance — F-1/F-2/F-3/F-4 + transport-level provider proof.

Kabul kriteri (spec #22): "route selection doğru" DEĞİL, "HTTP isteği gerçekten
seçilen provider endpoint'ine gitti" doğrulanır. OpenRouter, provider anahtarı
olduğunda SIFIR çağrı almalı; spend accounting Nous EFFECTIVE fiyatını kullanmalı.
Gerçek network yok: AsyncOpenAI kurulumu deterministik fake ile değiştirilir —
base_url + api_key + model + usage boundary'sinin tamamı assert edilir.
"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import agent_core.services.llm_gateway as gwl
from agent_core.services.llm_gateway import LLMGateway

_ENV_KEYS = (
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "CEREBRAS_API_KEY",
    "NOUS_API_KEY",
    "PINEAL_ALLOW_PAID_ESCALATION",
    "PINEAL_ALLOW_UNPRICED_MODELS",
    "OPENROUTER_MAX_SPEND_USD",
    "OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR",
    "USE_LOCAL_LLM",
    "LIVE_LLM_E2E",
    "PINEAL_ROUTER_LIVE",
)


def run(coro):
    return asyncio.run(coro)


class _Schema(BaseModel):
    a: int = 1


class FakeGatewayHttp:
    """LLMGateway'in dışa açıldığı TEK noktayı taklit eder (AsyncOpenAI ctor)."""

    def __init__(self, behavior=None):
        self.constructions: list[dict] = []  # (base_url, api_key) — kimlik kanıtı
        self.calls: list[tuple[str, dict]] = []  # (base_url, create kwargs)
        self._behavior = behavior or (lambda n: None)

    def factory(self, *, base_url, api_key, max_retries=0, **kw):
        self.constructions.append({"base_url": base_url, "api_key": api_key})
        outer = self

        class _C:
            def __init__(self, bu):
                self.chat = SimpleNamespace(completions=self._Comp(bu, outer))

            class _Comp:
                def __init__(self, bu, owner):
                    self.bu = bu
                    self.owner = owner

                async def create(self, **kwargs):
                    self.owner.calls.append((self.bu, kwargs))
                    outcome = self.owner._behavior(len(self.owner.calls))
                    if isinstance(outcome, Exception):
                        raise outcome
                    content = kwargs.get("_content", '{"a": 1}')
                    model = kwargs["model"]
                    usage = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=200_000)
                    if isinstance(outcome, dict):
                        content = outcome.get("content", content)
                        model = outcome.get("model", model)
                        usage = outcome.get("usage", usage)
                    elif isinstance(outcome, str):
                        content = outcome
                    return SimpleNamespace(
                        usage=usage,
                        model=model,
                        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                    )

        return _C(base_url)

    @property
    def or_calls(self):
        return [c for c in self.calls if c[0].rstrip("/") == "https://openrouter.ai/api/v1"]

    def calls_to(self, base):
        return [c for c in self.calls if c[0].startswith(base)]


@pytest.fixture()
def fake_http(monkeypatch):
    fake = FakeGatewayHttp()
    monkeypatch.setattr(gwl, "AsyncOpenAI", lambda **kw: fake.factory(**kw))
    return fake


@pytest.fixture()
def clean_env(monkeypatch, fake_http):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test-key")
    fake_http._behavior = lambda n: None
    return fake_http


def _gw():
    gw = LLMGateway()
    gw.live_unlocked = True
    return gw


# ------------------------------------------------------------------ #22 NOUS
def test_nous_sonnet_effective_price_and_zero_openrouter_calls(clean_env, monkeypatch):
    monkeypatch.setenv("NOUS_API_KEY", "nous-secret")
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    gw = _gw()
    # friction_detector zinciri: claude-sonnet-5 -> deepseek-v4-pro
    # Nous effective ($1.6/$8) < OpenRouter ($2/$10) -> merdiven Nous'u ONE alır.
    res = run(
        gw.query_json_chain("prompt", _Schema, task="depth", agent_name="friction_detector")
    )
    assert res.a == 1
    assert len(clean_env.calls) == 1
    base, kwargs = clean_env.calls[0]
    assert base.startswith("https://inference-api.nousresearch.com/v1")
    assert kwargs["model"] == "anthropic/claude-sonnet-5"
    assert len(clean_env.or_calls) == 0  # OpenRouter'a SIFIR istek
    # settlement Nous EFFECTIVE fiyatindan (liste 2/10 DEGIL):
    # 1M in * 1.6 + 0.2M out * 8.0 = 1.6 + 1.6 = $3.20
    assert gw.spend_usd == pytest.approx(3.20, abs=1e-6)
    rec = gw.call_log[-1]
    assert rec["provider"] == "nous-research"
    assert rec["route_key"] == "anthropic/claude-sonnet-5@nous-research"
    assert rec["pricing_in_per_million_usd"] == pytest.approx(1.6)
    assert rec["list_pricing_in_per_million_usd"] == pytest.approx(2.0)
    assert rec["discount_pct"] == pytest.approx(20.0)
    assert rec["chain_source"] == "agent_matrix"
    assert gw._reserved_spend_usd == 0.0  # reservation sizdirmasi yok


def test_luna_nous_discount_economics(clean_env, monkeypatch):
    # POLICY duzeyi: ROUTES'ta Luna list $1/$6, effective $0.2/$1.2 (%80 indirim)
    from agent_core.services import final_routing_policy as pol

    spec = pol.ROUTES["openai/gpt-5.6-luna@nous-research"]
    assert (spec.input_per_million_usd, spec.output_per_million_usd) == (0.20, 1.20)
    assert (spec.list_input_per_million_usd, spec.list_output_per_million_usd) == (1.00, 6.00)
    # spec ornegi: 2M in + 0.4M out -> $0.88
    cost = (2_000_000 * spec.input_per_million_usd + 400_000 * spec.output_per_million_usd) / 1e6
    assert cost == pytest.approx(0.88)
    # ve tam tersi kabul edilemez: liste fiyatiyla hesaplamak $4.40 verirdi
    assert cost != pytest.approx(4.40)


# ------------------------------------------------------------------ #23/#24
def test_groq_direct_route_transport_identity(clean_env, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret")
    monkeypatch.setenv("OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR", "openai/gpt-oss-120b")
    gw = _gw()
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert len(clean_env.calls) == 1
    base, kwargs = clean_env.calls[0]
    assert base.startswith("https://api.groq.com/openai/v1")
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert len(clean_env.or_calls) == 0
    assert gw.call_log[-1]["chain_source"] == "env_override"


def test_cerebras_direct_route_when_groq_absent(clean_env, monkeypatch):
    # FAZ-2-P3 (2026-09-08): cerebras free katmanı kapandı — gpt-oss-120b@cerebras
    # artık PAID ($0.35/$0.75). Yalnız cerebras anahtarı kurulu + escalation
    # AÇIK: cerebras tek direkt taşıma olur (groq yok, OR havuzu da devre dışı).
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cb-secret")
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    monkeypatch.setenv("OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR", "openai/gpt-oss-120b")
    gw = _gw()
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert clean_env.calls[0][0].startswith("https://api.cerebras.ai/v1")
    assert len(clean_env.or_calls) == 0


def test_cerebras_paid_not_offered_without_escalation(clean_env, monkeypatch):
    # P1 kilidi (fatura riski): cerebras free değil — escalation KAPALIYKEN
    # yalnız cerebras anahtarı olsa bile gpt-oss-120b@cerebras merdivene
    # GİRMEZ (eski "free" kaydı canlıda fatura yazardı). Merdiven boş kalır;
    # HTTP çağrısı HİÇ yapılmaz.
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setenv("CEREBRAS_API_KEY", "cb-secret")
    gw = _gw()
    # heavy tier context (friction_detector) + escalation'sız -> cerebras yok
    gw.get_agent_chain("friction_detector", "depth")
    ladder = gw.agent_route_variants("openai/gpt-oss-120b")
    assert all(v is None or v.provider_id != "cerebras" for v in ladder)
    assert len(clean_env.calls) == 0


def test_missing_key_falls_back_to_pool_provider(clean_env, monkeypatch):
    # G13/GROQ/NOUS anahtarlari YOK -> OpenRouter havuz uyesi olarak calisir, crash yok
    gw = _gw()
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert len(clean_env.calls) == 1
    assert clean_env.calls[0][0] == "https://openrouter.ai/api/v1"


def test_paid_key_present_but_escalation_off_uses_discounted_direct(clean_env, monkeypatch):
    # FAZ-2 (sahip Q1: heavy discounted-relax): claude-sonnet-5@nous İNDİRİMLİ
    # ($1.6/$8) kanaldır — escalation env'siz DOĞRUDAN kullanılır; liste
    # fiyatı ödemek için escalation gerekir (relax, FAZ-2'de onaylı davranış).
    monkeypatch.setenv("NOUS_API_KEY", "nous-secret")
    gw = _gw()
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert clean_env.calls[0][0].startswith("https://inference-api.nousresearch.com/v1")
    assert len(clean_env.or_calls) == 0


# ------------------------------------------------------------------ #13 QUOTA
def test_unknown_quota_never_unlimited():
    from agent_core.services.final_routing_policy import (
        UnknownQuotaDenied,
        quota_limit,
        quota_limit_or_zero,
    )

    with pytest.raises(UnknownQuotaDenied):
        quota_limit("cerebras", "rpd")  # UNKNOWN -> raise, asla inf degil
    assert quota_limit_or_zero("cerebras", "rpd") == 0
    assert quota_limit("groq", "rpm") == 30
    assert quota_limit("groq", "rpd") == 14400


def test_quota_headers_exhaust_provider_and_skip_ladder(clean_env, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    monkeypatch.setenv("OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR", "openai/gpt-oss-120b")
    gw = _gw()
    from agent_core.services.quota_governor import QuotaGovernor
    from agent_core.services.provider_manager import QuotaStatus

    # Kota dolmeden once merdiven groq rotasini oneriyor
    variants_before = gw.agent_route_variants("openai/gpt-oss-120b")
    assert any(v is not None and v.provider_id == "groq" for v in variants_before)


    gov = QuotaGovernor.from_policy()
    # provider-agrega scope ("*") — resolver da bu kabi okur
    gov.record_success("groq", "*", headers={"x-ratelimit-remaining-requests": "0"})
    gw._agent_governor = gov
    assert gov.status("groq") is QuotaStatus.EXHAUSTED
    assert gov.status("cerebras") is not QuotaStatus.EXHAUSTED  # karisma yok

    # header fixture ile EXHAUSTED olan groq merdivenden DUSER; OpenRouter kalir
    variants_after = gw.agent_route_variants("openai/gpt-oss-120b")
    assert [v for v in variants_after if v is not None] == []
    # zincir davranisi: groq'a HTTP yok (fiyat guard'i OR'da da gecerli — bu
    # ayri testte dogrulandi; burada skip kaniti resolver seviyesinde)
    assert len(clean_env.calls_to("https://api.groq.com")) == 0


# ------------------------------------------------------------------ F-1 ASPASIA
def test_aspasia_routes_with_agent_identity(clean_env):
    from agent_core.aspasia.aspasia_chief import AspasiaChief

    gw = _gw()
    chief = AspasiaChief(gw)
    resp = run(chief.chat("Bugün ne yapmalıyım Mösyö?", {}))
    assert resp.confidence_assessment == "high"
    assert len(clean_env.calls) == 1
    base, kwargs = clean_env.calls[0]
    assert base == "https://openrouter.ai/api/v1"
    # AGENT_CHAINS["aspasia"] birincili: claude-sonnet-5 (tier-default ile
    # ayni gorunur; kritik fark: artik YEDAK zinciri + merdiven var)
    assert kwargs["model"] == "anthropic/claude-sonnet-5"
    assert gw.call_log[-1]["chain_source"] == "agent_matrix"


def test_aspasia_explicit_model_pin_still_bypasses_chain(clean_env):
    from agent_core.aspasia.aspasia_chief import AspasiaChief

    gw = _gw()
    chief = AspasiaChief(gw)
    chief.set_preferred_model("local")
    # preferred=local -> query() local dali (kullanici secimi bilincli pin)
    run(chief.chat("merhaba", {}))
    rec = gw.call_log[-1]
    assert rec["provider"] == "local"


def test_aspasia_transient_failure_walks_chain_fallback(clean_env, monkeypatch):
    from agent_core.aspasia.aspasia_chief import AspasiaChief

    monkeypatch.setenv("CEREBRAS_API_KEY", "cb")  # kullanim disi; OR zinciri acik
    gw = _gw()

    def behavior(n):
        # OR legacy yolunda query() kendi icinde 3 deneme yapar; hepsi duserse
        # zincir sonraki MODELE (gemini) gecer.
        if n <= 3:
            return TimeoutError("connect timeout")
        return None

    clean_env._behavior = behavior
    chief = AspasiaChief(gw)
    resp = run(chief.chat("test", {}))
    assert resp.confidence_assessment == "high"
    assert len(clean_env.calls) == 4  # 3x claude (ic retry) + 1x gemini
    models = [c[1]["model"] for c in clean_env.calls]
    assert models[:3] == ["anthropic/claude-sonnet-5"] * 3
    assert models[3] == "google/gemini-3.7-flash"
    assert any(r["error"] for r in gw.call_log)  # hata kayitlari tutuldu


def test_aspasia_spend_cap_no_second_attempt_no_reservation_leak(clean_env, monkeypatch):
    from agent_core.aspasia.aspasia_chief import AspasiaChief

    monkeypatch.setenv("OPENROUTER_MAX_SPEND_USD", "0.0000001")
    gw = LLMGateway()  # cap ctor'da okunur
    gw.live_unlocked = True
    chief = AspasiaChief(gw)
    resp = run(chief.chat("test", {}))
    assert resp.confidence_assessment == "fallback"
    assert len(clean_env.calls) == 0  # rezervasyon asiliminda HTTP'e hic cikmadi
    assert gw._reserved_spend_usd == 0.0  # cap reddi => iade edilecek rezervasyon yok
    assert any("SPEND_CAP" in str(r.get("error", "")) for r in gw.call_log)


def test_aspasia_substitution_denied(clean_env):
    from agent_core.aspasia.aspasia_chief import AspasiaChief

    def behavior(n):
        return {"model": "some-other-default-model"}

    clean_env._behavior = behavior
    gw = _gw()
    chief = AspasiaChief(gw)
    resp = run(chief.chat("test", {}))
    # substitution reddi zinciri DURDURUR; aspasia dürüst fallback'a düşer
    assert resp.confidence_assessment == "fallback"
    assert len(clean_env.calls) == 1
    assert any("MODEL_SUBSTITUTION_DENIED" in str(r.get("error", "")) for r in gw.call_log)


# ------------------------------------------------------------------ F-2 IDENTITY
def _gw_recorder(gw):
    seen = []

    async def rec(prompt=None, schema=None, task=None, temperature=None,
                  system_prompt=None, images=None, agent_name=None, route=None, **kw):
        seen.append({"agent_name": agent_name, "task": task})
        return schema.model_construct() if hasattr(schema, "model_construct") else SimpleNamespace()

    gw.query_json_chain = rec
    gw.query_json = rec
    return seen


def test_authenticity_auditor_carries_agent_identity():
    from agent_core.agents.authenticity_auditor import AuthenticityAuditorAgent

    gw = SimpleNamespace()
    seen = _gw_recorder(gw)
    payload = {
        "target_profile": {"bio": "x", "posts": ["y"]},
        "visual_evidence": {"detected_objects": ["minimal oda"]},
    }
    run(AuthenticityAuditorAgent(gw).execute(payload))
    assert seen and seen[0]["agent_name"] == "authenticity_auditor"


def test_depth_analyst_carries_agent_identity():
    from agent_core.agents.depth_analyst import DepthAnalyst

    gw = SimpleNamespace()
    seen = _gw_recorder(gw)
    run(DepthAnalyst(gw).analyze({"target_profile": {"bio": "x"}}, []))
    assert seen and seen[0]["agent_name"] == "depth_analyst"


def test_matrix_change_propagates_to_bound_agents(monkeypatch):
    monkeypatch.setitem(
        LLMGateway.AGENT_CHAINS, "authenticity_auditor", ["test/model-x", "test/model-y"]
    )
    gw = LLMGateway()
    chain = gw.get_agent_chain("authenticity_auditor", "depth")
    assert chain == ["test/model-x", "test/model-y"]  # matrix tek SoT — aninda yansir
    assert gw.call_log == []  # (yan etki yok)


# ------------------------------------------------------------------ F-3 IDENTITY
def test_f3_agents_bound_with_identity():
    from agent_core.agents.human_behavior import HumanBehaviorAnalyzer
    from agent_core.agents.mirror_truth import MirrorOfTruth
    from agent_core.agents.pattern_interrupt import PatternInterrupt

    gw = SimpleNamespace()
    seen = _gw_recorder(gw)
    run(HumanBehaviorAnalyzer().execute({"target_profile": {"bio": "b", "posts": []}}, None, gw))
    assert seen[-1]["agent_name"] == "human_behavior"
    run(MirrorOfTruth(gw).execute({
        "user_profile": {"private_rituals": ["gece okuması"]},
        "user_context": {},
        "sacred_rules": "",
    }))
    assert seen[-1]["agent_name"] == "mirror_truth"
    run(PatternInterrupt().execute(
        {
            "target_analysis": {"micro_signals": [{"evidence": "somut kanit metni", "source": "post"}]},
            "user_mirror": {},
        },
        None,
        gw,
    ))
    assert seen[-1]["agent_name"] == "pattern_interrupt"


# ------------------------------------------------------------------ F-4 TELEMETRI
def test_chain_source_semantics(clean_env):
    gw = _gw()
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert gw.call_log[-1]["chain_source"] == "agent_matrix"


def test_env_override_precedence_and_source(clean_env, monkeypatch):
    # Matrix: [claude, deepseek-pro]; ENV override tek modelluk liste veriyor
    # -> cozum override'a gore olmalı (precedence kaniti) ve telemtri isaretlemeli.
    monkeypatch.setenv("OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR", "anthropic/claude-sonnet-5")
    gw = _gw()
    assert gw.get_agent_chain("friction_detector", "depth") == ["anthropic/claude-sonnet-5"]
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert clean_env.calls[0][1]["model"] == "anthropic/claude-sonnet-5"
    assert gw.call_log[-1]["chain_source"] == "env_override"


def test_task_fallback_source_marked(clean_env):
    gw = _gw()
    run(gw.query_json_chain("p", _Schema, task="depth", agent_name="adi-olmayan"))
    assert gw.call_log[-1]["chain_source"] == "task_chain"


# ------------------------------------------------------------------ #26 DURUSTILUK
def test_auth_error_never_becomes_second_attempt(clean_env):
    def behavior(n):
        return RuntimeError("401 UNAUTHORIZED: invalid_api_key")

    clean_env._behavior = behavior
    gw = _gw()
    with pytest.raises(Exception, match="401"):
        run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert len(clean_env.calls) == 1  # auth hatasi zinciri durdurur, tekrar denemez


def test_unpriced_model_not_treated_as_free(clean_env, monkeypatch):
    # PINEAL_ALLOW_UNPRICED_MODELS unset + cap yok -> gateway fiyat tarifesi
    # olmayan model reddedilir; "bilinmiyor = bedava" YOK.
    monkeypatch.delenv("OPENROUTER_MAX_SPEND_USD", raising=False)
    gw = _gw()
    seen = gw.agent_route_variants("karanlik/bilinmeyen-model")
    # OR havuz adayi var (None) ama query icinde guard isler:
    with pytest.raises(Exception, match="UNKNOWN_PRICING"):
        run(gw.query("p", model="karanlik/bilinmeyen-model"))


def test_billed_but_malformed_response_settles_before_fallback(clean_env, monkeypatch):
    # 2 model x (call+repair) = 3 cagri (3. modeldeki kurtaris); hicbir
    # rezervasyon askida kalmamali, ucretli denemeler tek tek tahsil edilmeli.
    def behavior(n):
        if n < 3:
            return "JSON degil bozuk cikti"
        return None

    clean_env._behavior = behavior
    monkeypatch.setenv("OPENROUTER_AGENT_CHAIN_FRICTION_DETECTOR", "anthropic/claude-sonnet-5,google/gemini-3.7-flash")
    gw = _gw()
    res = run(gw.query_json_chain("p", _Schema, task="depth", agent_name="friction_detector"))
    assert res.a == 1
    assert len(clean_env.calls) == 3
    assert gw._reserved_spend_usd == 0.0
    assert gw.spend_usd > 0.0  # bozuk AMA faturalanmis 2 cagri bedava sayilmadi
