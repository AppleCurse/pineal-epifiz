"""FINAL-KARAR-MATRIX policy contracts: free-first firewall, pricing, quotas.

The policy module speaks ``model@provider`` canonical keys and fails closed by
construction: unknown model/price/provider/quota is DENY (never free, never
unlimited), paid/frontier routes are gated by default, and task-group integrity
is validated at import time.
"""

import pytest

from agent_core.services.final_routing_policy import (
    QUOTA_UNKNOWN,
    QUOTAS,
    ROUTES,
    TASK_GROUPS,
    PaidEscalationDenied,
    RouteSpec,
    UnknownModelDenied,
    UnknownQuotaDenied,
    assert_executable,
    assert_known_model,
    effective_pricing,
    executable_task_groups,
    is_free,
    is_paid,
    list_pricing,
    model_substitution_allowed,
    paid_escalation_enabled,
    quota_limit,
    quota_limit_or_zero,
)


# --------------------------------------------------------------------------- #
# Cost firewall (free-first)
# --------------------------------------------------------------------------- #
def test_paid_escalation_is_denied_by_default(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    assert paid_escalation_enabled() is False
    with pytest.raises(PaidEscalationDenied):
        assert_executable("openai/gpt-5.6-luna", "nous-research")


def test_paid_escalation_requires_explicit_switch(monkeypatch):
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    assert assert_executable("openai/gpt-5.6-luna", "nous-research").tier == "paid"


def test_frontier_requires_env_even_with_explicit_bypass(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    # explicit=True alone must not arm a frontier route.
    with pytest.raises(PaidEscalationDenied):
        assert_executable("openai/gpt-5.6-sol-pro", "openrouter", explicit=True)
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    assert assert_executable(
        "openai/gpt-5.6-sol-pro", "openrouter", explicit=True
    ).tier == "frontier"


def test_explicit_non_frontier_paid_is_audited_but_allowed(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    assert assert_executable("openai/gpt-5.6-luna", "nous-research", explicit=True).tier == "paid"


def test_free_routes_never_select_a_paid_model(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    groups = executable_task_groups()
    assert "fast" in groups
    assert all(ROUTES[route].is_free() for route in groups["fast"])
    # research keeps free candidates only while escalation is off.
    assert all(ROUTES[route].is_free() for route in groups["research"])
    assert all(
        marker not in route
        for route in groups["research"]
        for marker in ("stepfun", "solar-pro4", "longcat", "luna")
    )


def test_paid_escalation_enabled_opens_policy_paid_routes_only(monkeypatch):
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    research = executable_task_groups()["research"]
    assert "stepfun/step-3.7-flash@nous-research" in research
    assert "upstage/solar-pro4@nous-research" in research
    assert "meituan/longcat-2.0@nous-research" in research
    assert "openai/gpt-5.6-luna@nous-research" in research


def test_free_routes_come_first_even_when_escalation_enabled(monkeypatch):
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    research = executable_task_groups()["research"]
    paid = {
        "stepfun/step-3.7-flash@nous-research",
        "upstage/solar-pro4@nous-research",
        "meituan/longcat-2.0@nous-research",
        "openai/gpt-5.6-luna@nous-research",
    }
    first_paid = next((index for index, route in enumerate(research) if route in paid), None)
    assert first_paid is not None
    assert all(ROUTES[route].is_free() for route in research[:first_paid])


def test_paid_only_tasks_are_empty_without_escalation(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    groups = executable_task_groups()
    assert groups["frontier_sol_pro"] == []
    assert groups["frontier_daily"] == []
    assert groups["frontier_reasoning"] == []
    assert groups["video"] == []
    assert groups["vision"] == []


# --------------------------------------------------------------------------- #
# Unknown model / unknown price / unknown quota => DENY (fail-closed)
# --------------------------------------------------------------------------- #
def test_unknown_model_is_denied():
    with pytest.raises(UnknownModelDenied):
        assert_executable("nous-research/naked-alias", "nous-research")
    assert effective_pricing("some/unknown-model", "some-provider") is None
    assert is_paid("some/unknown-model") is True  # unknown enters the paid firewall


def test_unknown_price_is_not_reported_as_free():
    assert effective_pricing("glm-5.3-flash", "nous-research") is None
    with pytest.raises(UnknownModelDenied):
        assert_executable("glm-5.3-flash", "nous-research")


def test_forbidden_aliases_are_denied():
    for alias in ("poolside/laguna:free", "laguna:free", "xs:free", "ling:free"):
        with pytest.raises(UnknownModelDenied):
            assert_known_model(alias, "nous-research")


def test_unknown_quota_is_never_unlimited():
    assert QUOTA_UNKNOWN is None
    assert QUOTAS["groq"]["tpm"] is None and QUOTAS["groq"]["tpd"] is None
    assert QUOTAS["cerebras"]["rpd"] is None
    with pytest.raises(UnknownQuotaDenied):
        quota_limit("groq", "tpm")
    with pytest.raises(UnknownQuotaDenied):
        quota_limit("nonexistent-provider", "rpm")
    assert quota_limit("groq", "rpm") == 30
    assert quota_limit_or_zero("groq", "tpm") == 0


# --------------------------------------------------------------------------- #
# Pricing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "model, provider, expected",
    [
        ("stepfun/step-3.7-flash", "nous-research", (0.20, 1.15)),
        ("upstage/solar-pro4", "nous-research", (0.03, 0.12)),
        ("meituan/longcat-2.0", "nous-research", (0.30, 1.20)),
        ("openai/gpt-5.6-luna", "nous-research", (0.20, 1.20)),
        ("anthropic/claude-sonnet-5", "nous-research", (1.60, 8.00)),
        ("google/gemini-3.7-flash", "openrouter", (0.75, 3.75)),
        # [2026-10-14 · canlı teyit] CI'ın canlı OpenRouter çapraz kontrolü
        # $2/$10 promo'sunun sona erdiğini gösterdi: $4/$20 (iki ardışık koşu).
        # Bu satır fiyatın BEŞİNCİ kopyasıdır; pinlerle birlikte güncellenir.
        ("openai/gpt-5.6-sol-pro", "openrouter", (4.0, 20.0)),
    ],
)
def test_effective_prices_match_decision_matrix(model, provider, expected):
    assert effective_pricing(model, provider) == expected


def test_luna_discount_cost_example():
    in_rate, out_rate = effective_pricing("openai/gpt-5.6-luna", "nous-research")
    assert 2 * in_rate + 0.4 * out_rate == pytest.approx(0.88)


def test_sonnet_discount_cost_example():
    in_rate, out_rate = effective_pricing("anthropic/claude-sonnet-5", "nous-research")
    assert 1 * in_rate + 0.2 * out_rate == pytest.approx(3.20)


def test_free_routes_have_zero_effective_price():
    for model in ("poolside/laguna-s-2.1:free", "poolside/laguna-xs-2.1:free", "inclusionai/ling-3.0-flash-fin:free"):
        assert effective_pricing(model, "nous-research") == (0.0, 0.0)


def test_list_pricing_records_nous_discounts():
    assert list_pricing("openai/gpt-5.6-luna", "nous-research") == (1.00, 6.00)
    assert list_pricing("anthropic/claude-sonnet-5", "nous-research") == (2.00, 10.00)
    # Routes without a list discount fall back to the effective price.
    assert list_pricing("stepfun/step-3.7-flash", "nous-research") == (0.20, 1.15)


def test_list_pricing_requires_both_or_neither():
    with pytest.raises(ValueError):
        RouteSpec(
            "m", "p", "paid", 0.1, 0.1,
            list_input_per_million_usd=1.0,
            list_output_per_million_usd=None,
        )


# --------------------------------------------------------------------------- #
# Provider quotas
# --------------------------------------------------------------------------- #
def test_groq_account_quota_is_recorded():
    assert QUOTAS["groq"]["rpm"] == 30
    assert QUOTAS["groq"]["rpd"] == 14_400
    assert QUOTAS["groq"]["tpm"] is None
    assert QUOTAS["groq"]["tpd"] is None


def test_cerebras_account_quota_is_recorded():
    assert QUOTAS["cerebras"]["rpm"] == 5
    assert QUOTAS["cerebras"]["tpm"] == 30_000
    assert QUOTAS["cerebras"]["tpd"] == 1_000_000
    assert QUOTAS["cerebras"]["rpd"] is None


# --------------------------------------------------------------------------- #
# Model availability / capability / verification
# --------------------------------------------------------------------------- #
def test_verified_routes_are_available_and_free_routes_executable(monkeypatch):
    monkeypatch.delenv("PINEAL_ALLOW_PAID_ESCALATION", raising=False)
    assert_executable("poolside/laguna-s-2.1:free", "nous-research")
    assert_executable("openai/gpt-oss-120b", "groq")
    # FAZ-2-P3 (2026-09-08): Cerebras açık free katmanı 21.07.2026'da kapandı —
    # gpt-oss-120b@cerebras artık PAID ($0.35/$0.75); escalation'sız DENY.
    with pytest.raises(PaidEscalationDenied):
        assert_executable("gpt-oss-120b", "cerebras")
    monkeypatch.setenv("PINEAL_ALLOW_PAID_ESCALATION", "1")
    spec = assert_executable("gpt-oss-120b", "cerebras")
    assert spec.tier == "paid"
    assert (spec.input_per_million_usd, spec.output_per_million_usd) == (0.35, 0.75)


def test_discovered_but_unverified_route_is_denied():
    with pytest.raises(UnknownModelDenied):
        assert_executable("poolside/laguna:free", "nous-research")


def test_provider_default_substitution_is_denied():
    assert model_substitution_allowed("openai/gpt-oss-120b", "openai/gpt-oss-120b")
    assert not model_substitution_allowed("openai/gpt-oss-120b", "some-provider-default-model")


def test_vision_task_routes_are_vision_capable():
    assert "vision" in ROUTES["google/gemini-3.7-flash@openrouter"].capabilities
    assert "vision" in ROUTES["anthropic/claude-sonnet-5@nous-research"].capabilities
    assert "vision" in ROUTES["stepfun/step-3.7-flash@nous-research"].capabilities
    assert "vision" not in ROUTES["meituan/longcat-2.0@nous-research"].capabilities
    assert "vision" not in ROUTES["poolside/laguna-s-2.1:free@nous-research"].capabilities


def test_video_task_route_is_video_capable():
    assert "video" in ROUTES["stepfun/step-3.7-flash@nous-research"].capabilities


def test_frontier_routes_are_explicit_paid():
    assert is_paid("openai/gpt-5.6-sol-pro", "openrouter")
    assert is_paid("anthropic/claude-sonnet-5", "nous-research")
    assert ROUTES["openai/gpt-5.6-sol-pro@openrouter"].tier == "frontier"


def test_is_free_and_is_paid_fail_closed():
    assert is_free("poolside/laguna-s-2.1:free", "nous-research")
    assert is_free("openai/gpt-oss-120b", "groq")
    assert not is_free("completely-unknown-model")
    assert not is_free("openai/gpt-5.6-luna", "nous-research")
    assert is_paid("completely-unknown-model") is True
    assert is_paid("glm-5.3-flash") is True
    assert not is_paid("poolside/laguna-s-2.1:free", "nous-research")


def test_route_table_is_well_formed():
    for spec in ROUTES.values():
        assert spec.tier in {"free", "paid", "frontier"}
        if spec.tier == "free":
            assert spec.input_per_million_usd == 0.0
            assert spec.output_per_million_usd == 0.0
        assert spec.verification_status == "verified"


def test_task_groups_resolve_to_verified_routes():
    # _validate_catalog() already runs at import; this locks the same contract
    # from the test side.
    for candidates in TASK_GROUPS.values():
        for model, provider in candidates:
            key = f"{model}@{provider}"
            assert key in ROUTES
            assert ROUTES[key].verification_status == "verified"


def test_verification_status_defaults_to_unverified():
    spec = RouteSpec("brand-new-model", "brand-new-provider", "free", 0.0, 0.0)
    assert spec.verification_status == "unverified"
