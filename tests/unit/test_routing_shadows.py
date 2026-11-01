"""Routing-shadow contract locks (snapshot + generator + tiers).

- committed shadows == fresh generator output (byte-identical, hermetic env)
- 4 precedence sources producible AND script's layer list matches them
- every routed agent has a tier (coverage ratchet — fails on untiered agent)
- snapshot schema/serializability/task-independence/contextvar preservation
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import agent_core.services.llm_gateway as gwl
from agent_core.services.llm_gateway import LLMGateway

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_routing_shadows.py"
#: [P6 · 2026-10-18] Svelte gölge hedefi OPSİYONEL: canlı arayüzde statik
#: ajan-model tablosu yok (model/via koşunun provenance'ından gelir). Ölü
#: `UnifiedCompactPanel.svelte` silindi; gölge artık yalnız RUNBOOK'da üretilir.
SVELTE_CANDIDATES = (ROOT / "frontend/src/components/UnifiedCompactPanel.svelte",)
RUNBOOK = ROOT / "RUNBOOK.md"

EXPECTED_SOURCES = {"env_override", "task_routing", "agent_matrix", "task_chain"}


def _load_script():
    spec = importlib.util.spec_from_file_location("gen_shadows", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _hermetic_shadow_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("OPENROUTER_AGENT_CHAIN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("PINEAL_TASK_ROUTING_PATH", raising=False)
    monkeypatch.delenv("PINEAL_AGENT_TIERS_PATH", raising=False)
    yield


def test_committed_shadows_match_fresh_generator_output():
    """--check: commit'li gölgeler taze üretimle bayt-bayt aynı olmalı."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, f"--check red:\n{proc.stdout}\n{proc.stderr}"


def test_generator_is_idempotent():
    """generate → --check yeşil: üretim kararlı (sabit-nokta)."""
    gen = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert gen.returncode == 0, gen.stderr
    chk = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], cwd=ROOT, capture_output=True, text=True, timeout=120
    )
    assert chk.returncode == 0, f"üretim sonrası --check red:\n{chk.stdout}\n{chk.stderr}"


def test_all_four_precedence_sources_producible_and_script_lists_them(tmp_path, monkeypatch):
    gw = LLMGateway()
    seen = set()

    monkeypatch.setenv("OPENROUTER_AGENT_CHAIN_XFRESH", "a/b")
    gw.get_agent_chain("xfresh", "depth")
    seen.add(gwl._active_chain_source.get())

    routing = tmp_path / "r.json"
    routing.write_text(json.dumps({"xfresh2": ["grok_4_6"]}), encoding="utf-8")
    monkeypatch.setenv("PINEAL_TASK_ROUTING_PATH", str(routing))
    gw.get_agent_chain("xfresh2", "depth")
    seen.add(gwl._active_chain_source.get())

    monkeypatch.delenv("PINEAL_TASK_ROUTING_PATH")
    gw.get_agent_chain("friction_detector", "depth")
    seen.add(gwl._active_chain_source.get())
    gw.get_agent_chain("yok-boyle-ajan", "depth")
    seen.add(gwl._active_chain_source.get())

    assert seen == EXPECTED_SOURCES
    script_sources = [name for name, _ in _load_script().LAYER_DOCS]
    assert script_sources == ["env_override", "task_routing", "agent_matrix", "task_chain"]
    assert set(script_sources) == seen


def test_every_routed_agent_has_tier():
    """Coverage ratchet: snapshot'taki her ajan tiers dosyasında olmalı."""
    snapshot = LLMGateway().effective_routing_snapshot()
    untiered = [v for v in snapshot["tier_violations"] if v["rule"] == "untiered"]
    assert untiered == []


def test_snapshot_schema_serializable_and_consistent():
    snapshot = LLMGateway().effective_routing_snapshot()
    json.dumps(snapshot)  # JSON-uyumlu olmalı
    assert snapshot["schema_version"] == 1
    assert set(snapshot) == {"schema_version", "registry", "agents", "routes", "tiers", "tier_violations"}
    assert set(snapshot["registry"]) == set(LLMGateway.MODEL_REGISTRY)
    for agent, row in snapshot["agents"].items():
        assert set(row) == {"chain", "chain_keys", "source"}, agent
        assert row["source"] in EXPECTED_SOURCES, agent
        if row["source"] == "task_routing":
            assert row["chain_keys"] is not None, agent
            assert [snapshot["registry"][k] for k in row["chain_keys"]] == row["chain"], agent
    for v in snapshot["tier_violations"]:
        assert set(v) == {"agent", "rule", "detail"}, v


def test_snapshot_preserves_chain_source_contextvar():
    before = gwl._active_chain_source.get()
    gwl._active_chain_source.set("marker-x")
    try:
        LLMGateway().effective_routing_snapshot()
        assert gwl._active_chain_source.get() == "marker-x"
    finally:
        gwl._active_chain_source.set(before)


def test_snapshot_layer_attribution_is_task_independent():
    gw = LLMGateway()
    for agent in ("depth_analyst", "friction_detector", "dialogue_manager"):
        results = set()
        for task in ("depth", "vision", "dialogue"):
            chain = gw.get_agent_chain(agent, task)
            results.add((tuple(chain), gwl._active_chain_source.get()))
        assert len(results) == 1, agent


def test_shadow_markers_present():
    """RUNBOOK gölgesi canlıdır (marker 1'er). Svelte hedefi varsa o da 1'er."""
    assert RUNBOOK.read_text(encoding="utf-8").count("<!-- ROUTING-GENERATED-START do-not-edit -->") == 1
    assert RUNBOOK.read_text(encoding="utf-8").count("<!-- ROUTING-GENERATED-END -->") == 1
    for cand in SVELTE_CANDIDATES:
        if cand.exists():
            assert cand.read_text(encoding="utf-8").count("// <ROUTING-GENERATED-START do-not-edit>") == 1
            assert cand.read_text(encoding="utf-8").count("// <ROUTING-GENERATED-END>") == 1


def test_generator_runs_without_svelte_target():
    """[P6] Svelte hedefi yokken üretici ÇÖKMEZ; RUNBOOK gölgesini üretir.

    Ölü frontend bileşeni silindiğinde CI adımı (routing shadows) kırılmasın.
    """
    mod = _load_script()
    assert mod.SVELTE is None, "ölü UnifiedCompactPanel artık depoda olmamalı"
    assert mod.generate(check_only=True) is False, "RUNBOOK gölgesi taze olmalı"
