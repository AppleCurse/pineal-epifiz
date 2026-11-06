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


def test_direct_dispatch_does_not_fabricate_agent_results():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routes.commander import register_commander_routes

    app = FastAPI()
    register_commander_routes(app, rate_limit=lambda *_: True, rate_identity=lambda *_: "test",
                              gateway_provider=lambda: None)
    client = TestClient(app)
    for agent in ("aspasia", "lilith", "osint_investigator"):
        response = client.post("/api/commander/dispatch", json={"agent_id": agent,
                               "instruction": "araştır", "twin_url": "https://example.com/test"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DIRECT_AGENT_DISPATCH_UNAVAILABLE"
        assert "twin_verified" not in response.text
        assert "0.91" not in response.text


def test_generate_hook_separates_unverified_input_from_verified_evidence(client_app):
    """Dolu ama doğrulanmamış bio: input_data_present=True, fakat evidence_verification_status='unverified' ve data_confidence=False olmalı."""
    client, _ = client_app
    payload = {
        "client_id": "test_room",
        "intent": "authentic_connection",
        "target_username": "unverified_user",
        "target_profile": {"bio": "Sentetik doğrulanmamış biyografi metni"},
    }
    resp = client.post("/api/hook/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["input_data_present"] is True
    assert data["evidence_verification_status"] == "unverified"
    assert data["data_confidence"] is False


def test_generate_hook_rejects_whitespace_and_placeholder_as_input_data(client_app):
    """Boşluk veya placeholder metinler input_data_present=False üretmeli."""
    client, _ = client_app
    payload = {
        "client_id": "test_room",
        "intent": "authentic_connection",
        "target_username": "empty_user",
        "target_profile": {"bio": "   ", "posts": ["bilinmiyor", "yok"]},
        "passions": {"core_passions": ["-"]},
    }
    resp = client.post("/api/hook/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["input_data_present"] is False
    assert data["evidence_verification_status"] == "unverified"
    assert data["data_confidence"] is False


def test_generate_hook_grants_verified_status_only_when_task_verifier_report_verified(
    monkeypatch,
):
    """Yalnız görevde doğrulanmış VerifierReport varsa ve ham override enjekte edilmemişse evidence_verification_status='verified' olur."""
    from types import SimpleNamespace

    app = FastAPI()
    mock_gw = MagicMock(spec=LLMGateway)
    mock_gw.query_json_chain = AsyncMock(
        return_value=HookResult(
            opening_message="Doğrulanmış ortak nokta üzerinden mesaj.",
            opening_topic="Açık Kaynak Sistemler",
            rationale="Bağımsız doğrulanmış katkı geçmişi.",
            archetype="intellectual_collab",
            dialogue_tree=[],
            shared_points=["Rust"],
            confidence=0.88,
        )
    )
    fake_task = SimpleNamespace(
        target_profile={"bio": "Doğrulanmış açık kaynak geliştiricisi"},
        holistic_profile=SimpleNamespace(
            passions=SimpleNamespace(model_dump=lambda: {"core_passions": ["Rust"]}),
            frictions=None,
            cognitive=None,
        ),
        depth_report=None,
        verification_report=SimpleNamespace(
            status="VERIFIED",
            data_confidence=True,
        ),
    )
    fake_executor = SimpleNamespace(tasks={"task-verified-1": fake_task}, last_status=fake_task)

    register_hook_studio_routes(
        app,
        rate_limit=lambda ip, action: True,
        rate_identity=lambda req: "127.0.0.1",
        gateway_provider=lambda: mock_gw,
        get_executor=lambda client_id: fake_executor,
    )
    client = TestClient(app)

    # 1. Doğrulanmış görev verisiyle çağrı (ham override yok)
    resp = client.post(
        "/api/hook/generate",
        json={"client_id": "c1", "task_id": "task-verified-1", "intent": "intellectual_collab"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["input_data_present"] is True
    assert data["evidence_verification_status"] == "verified"
    assert data["data_confidence"] is True

    # 2. Aynı görev ID'sine dışarıdan doğrulanmamış bio enjekte edilirse unverified'a düşmeli
    resp_override = client.post(
        "/api/hook/generate",
        json={
            "client_id": "c1",
            "task_id": "task-verified-1",
            "intent": "intellectual_collab",
            "target_profile": {"bio": "Operatörün doğrulanmamış manuel girdisi"},
        },
    )
    assert resp_override.status_code == 200
    data_override = resp_override.json()
    assert data_override["input_data_present"] is True
    assert data_override["evidence_verification_status"] == "unverified"
    assert data_override["data_confidence"] is False
