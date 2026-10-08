"""[BOSS-7 + BOSS-9] Kör ajanlar ve çift pattern çağrısı — sözleşme testleri.

BOSS-7: `pattern_interrupt` görev başına iki kez LLM'e gidiyordu (rota + ShadowExecutor).
Rota çıktısı `input_data["_pattern_interrupt"]` içine yazıldı; gölge katman onu tüketir.

BOSS-9: upstream bulgu bloğu yalnız `target_psyche_profiler` + (ölü) `resonance_synthesizer`
tarafından okunuyordu; mirror_truth, human_behavior, pattern_interrupt, depth_analyst ve
authenticity_auditor promptları bloğu hiç görmüyordu (ölçüm: 3 dolu / 1 boş tüketici).

Bu dosya iki davranışı da kilitler.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_core.shadow.shadow_executor import ShadowExecutor

REPO = Path(__file__).resolve().parents[2]

# BOSS-9 kablolaması yapılan modüller (her biri prompt'una bloğu basar).
WIRED_MODULES = {
    "agent_core/agents/mirror_truth.py": "upstream_block",
    "agent_core/agents/human_behavior.py": "upstream_block",
    "agent_core/agents/pattern_interrupt.py": "upstream_block",
    "agent_core/agents/depth_analyst.py": "upstream_block",
    "agent_core/agents/authenticity_auditor.py": "upstream_block",
}


def _shadow_with_strategy(vector: str = "direct") -> ShadowExecutor:
    shadow = ShadowExecutor(llm_gateway=MagicMock())
    shadow.dark_triad = MagicMock()
    shadow.dark_triad.analyze.return_value = MagicMock(
        model_dump=lambda: {"machiavellianism": 0.6, "narcissism": 0.4, "psychopathy": 0.2},
        machiavellianism=0.6,
        narcissism=0.4,
        psychopathy=0.2,
    )
    shadow.dark_triad.strategy_from_depth.return_value = {
        "vector": vector,
        "tactic": "grounded tactic",
    }
    shadow.mirror = MagicMock()
    shadow.mirror.execute = AsyncMock(return_value=MagicMock(model_dump=lambda: {"alignment_score": 0.5}))
    shadow.pattern = MagicMock()
    shadow.pattern.execute = AsyncMock(return_value=MagicMock(message="LLM mesajı"))
    return shadow


def _shadow_input(**extra) -> dict:
    payload = {
        "target_profile": {"bio": "Kahve ve mimari.", "posts": ["Sabah ışığı."]},
        "psychodynamic_depth": {"verdict": "ok"},
        "sacred_rules": "",
    }
    payload.update(extra)
    return payload


@pytest.mark.asyncio
async def test_shadow_reuses_routed_pattern_message_without_llm_call():
    shadow = _shadow_with_strategy()
    payload = _shadow_input(_pattern_interrupt={"message": "Rota mesajı: gözlemledim.", "source": "route"})

    result = await shadow.execute(payload)

    shadow.pattern.execute.assert_not_called()
    assert "Rota mesajı: gözlemledim." in result.message
    assert result.message != "LLM mesajı"


@pytest.mark.asyncio
async def test_shadow_still_calls_pattern_when_route_has_no_message():
    """Rota çıktısı yoksa eski davranış korunur (regresyon koruması)."""
    shadow = _shadow_with_strategy()

    result = await shadow.execute(_shadow_input())

    shadow.pattern.execute.assert_awaited_once()
    assert "LLM mesajı" in result.message


def test_upstream_block_is_wired_into_prompts():
    """Her hedef modül bloğu import eder ve prompt'unda kullanır."""
    missing = []
    for relative, variable in WIRED_MODULES.items():
        source = (REPO / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "agent_core.services.upstream_findings"
            and any(alias.name == "upstream_findings_block" for alias in node.names)
            for node in ast.walk(tree)
        )
        used = any(isinstance(node, ast.Name) and node.id == variable for node in ast.walk(tree))
        if not (imported and used):
            missing.append(f"{relative} (import={imported}, kullanım={used})")
    assert not missing, "upstream bloğu prompt'a girmiyor: " + ", ".join(missing)


@pytest.mark.asyncio
async def test_authenticity_auditor_prompt_carries_upstream_findings():
    """Kablolama gerçekten prompt metnine yansıyor (statik kontrol yetmez)."""
    from agent_core.agents.authenticity_auditor import AuthenticityAuditorAgent

    captured: dict = {}
    gateway = MagicMock()

    class _Result:
        authenticity_score = 0.8
        visual_text_gaps = []
        supported_claims = []
        confidence = 0.8
        data_confidence = True
        fallback_reason = None

    async def _capture(prompt=None, **kwargs):
        captured["prompt"] = prompt
        return _Result()

    gateway.query_json_chain = _capture
    agent = AuthenticityAuditorAgent(llm_gateway=gateway)

    payload = {
        "target_profile": {"bio": "Minimalist", "posts": ["kapalı mekan"]},
        "visual_evidence": {"detected_objects": ["laptop"], "environment_and_places": ["stüdyo"]},
        "_upstream_findings": [
            {
                "agent": "mirror_truth",
                "core": "yüzeysel persona ile çelişki",
                "epistemic_type": "inference",
                "verification_status": "unverified",
                "origin": "task_executor",
            }
        ],
    }
    await agent.execute(payload)

    assert "DİĞER AJANLARIN BULGULARI" in captured["prompt"]
    assert "[mirror_truth] [inference, doğrulanmamış] yüzeysel persona ile çelişki" in captured["prompt"]


@pytest.mark.asyncio
async def test_authenticity_auditor_prompt_stays_clean_without_findings():
    """Bulgu yoksa prompt'a boş blok başlığı bile eklenmez (uydurma yok)."""
    from agent_core.agents.authenticity_auditor import AuthenticityAuditorAgent

    captured: dict = {}
    gateway = MagicMock()

    class _Result:
        authenticity_score = 0.8
        visual_text_gaps = []
        supported_claims = []
        confidence = 0.8
        data_confidence = True
        fallback_reason = None

    async def _capture(prompt=None, **kwargs):
        captured["prompt"] = prompt
        return _Result()

    gateway.query_json_chain = _capture
    agent = AuthenticityAuditorAgent(llm_gateway=gateway)

    await agent.execute({
        "target_profile": {"bio": "Minimalist", "posts": ["kapalı mekan"]},
        "visual_evidence": {"detected_objects": ["laptop"]},
    })

    assert "DİĞER AJANLARIN BULGULARI" not in captured["prompt"]
