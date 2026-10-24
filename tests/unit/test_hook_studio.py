"""Hook Studio uç nokta testleri — ``/api/hook/archetypes`` ve ``/api/hook/generate``."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.hook_studio import register_hook_studio_routes, HookResult, DialogueBranch
from agent_core.services.llm_gateway import LLMGateway


@pytest.fixture
def client_app():
    app = FastAPI()
    mock_gw = MagicMock(spec=LLMGateway)
    mock_gw.query_json_chain = AsyncMock(return_value=HookResult(
        opening_message="Fotoğraflarınızdaki ışık dengesi çok etkileyici.",
        opening_topic="Sokak Estetiği",
        rationale="Görsel duyarlılığa saygılı ilk temas.",
        archetype="authentic_connection",
        dialogue_tree=[
            DialogueBranch(
                scenario="savunmaci",
                target_reaction="Beni nereden tanıyorsun?",
                our_counter_move="Paylaşımlarınıza denk geldim, tebrik etmek istedim.",
            )
        ],
        shared_points=["Fotoğraf"],
        confidence=0.95,
    ))

    register_hook_studio_routes(
        app,
        rate_limit=lambda ip, action: True,
        rate_identity=lambda req: "127.0.0.1",
        gateway_provider=lambda: mock_gw,
        get_executor=None,
    )
    return TestClient(app), mock_gw


def test_list_archetypes(client_app):
    client, _ = client_app
    resp = client.get("/api/hook/archetypes")
    assert resp.status_code == 200
    data = resp.json()
    assert "archetypes" in data
    ids = [a["id"] for a in data["archetypes"]]
    assert "authentic_connection" in ids
    assert "business_collab" in ids
    assert "pattern_interrupt" in ids
    assert "shadow_hook" in ids


def test_generate_hook_success(client_app):
    client, mock_gw = client_app
    payload = {
        "client_id": "test_room",
        "intent": "business_collab",
        "target_username": "test_target",
        "target_profile": {"bio": "Yazılım mimarı", "posts": ["Rust ile sistem programlama"]},
        "passions": {"core_passions": ["Rust", "Yüksek Başarım"]},
    }
    resp = client.post("/api/hook/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["opening_message"] == "Fotoğraflarınızdaki ışık dengesi çok etkileyici."
    assert data["archetype"] == "business_collab"
    assert len(data["dialogue_tree"]) >= 1


def test_generate_hook_llm_failure_returns_honest_fallback():
    app = FastAPI()
    mock_gw = MagicMock(spec=LLMGateway)
    mock_gw.query_json_chain = AsyncMock(side_effect=RuntimeError("LLM Hatası"))

    register_hook_studio_routes(
        app,
        rate_limit=lambda ip, action: True,
        rate_identity=lambda req: "127.0.0.1",
        gateway_provider=lambda: mock_gw,
        get_executor=None,
    )
    client = TestClient(app)

    payload = {
        "client_id": "test_room",
        "intent": "authentic_connection",
        "target_username": "dev_ali",
        "passions": {"core_passions": ["Fotoğrafçılık"]},
    }
    resp = client.post("/api/hook/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "@dev_ali" in data["opening_message"]
    assert data["fallback_reason"] == "llm_unavailable_template_fallback"
    assert len(data["dialogue_tree"]) == 3
