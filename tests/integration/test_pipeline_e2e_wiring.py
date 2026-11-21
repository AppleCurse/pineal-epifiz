"""MOCK'SUZ Uçtan Uca (E2E) Gerçek Boru Hattı Bağlantı Kanıtı.

Bu dosyada kritik kablolar (PillarOrchestrator, follower_audit, timing_forensics,
psychodynamic_depth, cross_profiler, memory_crystal, graph_builder, ShadowExecutor,
LilithGrowthAgent, generate_hook_package, AspasiaChief.build_telemetry_summary,
/api/vault, /api/lilith/strategy, /api/brain/route) MOCK'LANMADAN gerçek sınıf
ve gerçek FastAPI HTTP uçlarıyla çalıştırılır.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_core.aspasia.aspasia_chief import AspasiaChief
from agent_core.services.canonical_memory import CanonicalMemory
from agent_core.services.graph_builder import build_evidence_graph
from agent_core.services.memory_crystal import recall as recall_memory_crystal
from agent_core.task_executor import PinealExecutor
from backend import api as backend_api


def _real_sample_input() -> dict:
    return {
        "target_url": "https://www.instagram.com/mimar_deniz/",
        "target_profile": {
            "username": "mimar_deniz",
            "name": "Deniz Kaya",
            "platform": "instagram",
            "bio": "Sistem mimarisi ve tipografi üzerine çalışıyorum. Stüdyo: @deniz_studio https://denizstudio.com",
            "followers": 4200,
            "following": 380,
            "detected_urls": [
                "https://github.com/mimar_deniz",
                "https://x.com/mimar_deniz",
            ],
            "post_times": [
                "2026-10-01T23:15:00Z",
                "2026-10-04T22:40:00Z",
                "2026-10-08T19:30:00Z",
                "2026-10-12T23:50:00Z",
                "2026-10-16T21:10:00Z",
            ],
            "posts_meta": [
                {"like_count": 210, "comment_count": 14},
                {"like_count": 285, "comment_count": 22},
                {"like_count": 340, "comment_count": 31},
                {"like_count": 195, "comment_count": 11},
                {"like_count": 410, "comment_count": 39},
            ],
            "posts": [
                {
                    "text": "Gece 02:15 — yeni tipografi ızgarasını bitirdim, mükemmeliyetçilik yine yoruyor.",
                    "timestamp": "2026-10-01T23:15:00Z",
                    "like_count": 210,
                    "comment_count": 14,
                },
                {
                    "text": "Tasarım sistemlerinde gereksiz süsleri attık, sadece saf işlev kaldı.",
                    "timestamp": "2026-10-04T22:40:00Z",
                    "like_count": 285,
                    "comment_count": 22,
                },
                {
                    "text": "İstanbul mimari fotoğraf serisinden yeni seçki yayınlandı.",
                    "timestamp": "2026-10-08T19:30:00Z",
                    "like_count": 340,
                    "comment_count": 31,
                },
                {
                    "text": "Sessiz çalışma saatleri olmadan derin üretim çıkmıyor.",
                    "timestamp": "2026-10-12T23:50:00Z",
                    "like_count": 195,
                    "comment_count": 11,
                },
                {
                    "text": "Açık kaynak araçlarla kurduğumuz yeni araştırma akışı yayında.",
                    "timestamp": "2026-10-16T21:10:00Z",
                    "like_count": 410,
                    "comment_count": 39,
                },
            ],
        },
        "public_osint": {
            "found_profiles": [
                {"platform": "github", "username": "mimar_deniz", "url": "https://github.com/mimar_deniz"},
                {"platform": "x", "username": "mimar_deniz", "url": "https://x.com/mimar_deniz"},
            ]
        },
    }


@pytest.mark.asyncio
async def test_zero_mock_executor_full_deterministic_cross_aspasia_and_lilith_flow(tmp_path):
    """ZERO MOCK: Tüm deterministik motorlar + çapraz profil + kristal + graf + Aspasia + Lilith gerçek koşar."""
    executor = PinealExecutor()
    # Yalnız disk izolasyonu (repo çalışma dizinine test verisi yazmamak için)
    executor.memory = CanonicalMemory(storage_path=str(tmp_path))

    inp = _real_sample_input()
    status = await executor.execute_task(inp, "tsk_real_nomock_1")

    # 1. Deterministik LLM'siz motorlar gerçek çıktı üretti
    assert status.follower_audit is not None
    assert status.timing_forensics is not None
    assert status.psychodynamic_depth is not None
    assert status.pillar_bundle is not None
    assert isinstance(status.evidence_chain, list) and len(status.evidence_chain) >= 4

    # 2. Çapraz profilleme gerçek eşleşme üretti
    cross_matches = inp.get("cross_profile_matches") or []
    assert len(cross_matches) >= 1, f"cross_profiler eşleşme üretmedi: {inp.keys()}"

    # 3. ShadowExecutor + LilithGrowthAgent gerçek sınıf olarak koştu (mock yok!)
    assert status.shadow_profile is not None
    assert "shadow_executor" in status.agent_runs
    assert status.lilith_report is not None
    assert "lilith_growth" in status.agent_runs
    nm = status.lilith_report.get("neuro_metrics")
    assert isinstance(nm, dict), f"NeuroMetrics boş: {status.lilith_report}"
    assert 0.5 <= nm["viral_coefficient_score"] <= 10.0

    # 4. Değişim İzleme (change_tracker) + Hafıza Kristali (memory_crystal) diskte gerçek olarak kaydoldu
    from agent_core.services.change_tracker import load_history
    history = load_history(str(tmp_path), "mimar_deniz")
    assert len(history) == 1, f"change_tracker anlık görüntü kaydetmedi: {history}"
    assert history[0].task_id == "tsk_real_nomock_1"

    recalled = recall_memory_crystal("mimar_deniz", "tipografi mimari", base=str(tmp_path))
    assert recalled.available is True, f"memory_crystal kristalleşmedi: {recalled.model_dump()}"
    assert len(recalled.hits) >= 1

    # 5. İlişki Grafı gerçek evidence_chain üzerinden düğüm ve bağ üretti
    graph = build_evidence_graph(status.evidence_chain)
    assert graph.available is True, f"graph_builder boş döndü: {graph.model_dump()}"
    assert graph.node_count >= 1

    # 6. Aspasia özet katmanı hedef + shadow + lilith çıktılarını gerçek olarak okuyor
    aspasia = AspasiaChief(llm_gateway=executor.llm_gateway)
    summary_text = aspasia.build_telemetry_summary(status)
    assert "mimar_deniz" in summary_text or "Deniz Kaya" in summary_text
    assert "[GÖLGE STRATEJİSİ]" in summary_text
    assert "[LILITH KARŞI-HAMLE & NÖRO]" in summary_text


def test_zero_mock_fastapi_vault_lilith_and_brain_hub_end_to_end(tmp_path, monkeypatch):
    """ZERO MOCK: Gerçek FastAPI app, gerçek /api/vault + /api/vault/unlock, gerçek Lilith + HookStudio + Brain Hub."""
    # Yalnız geçici kasa dosyası izolasyonu (repo köküne .pineal_vault.json bırakmamak için)
    monkeypatch.setattr(backend_api, "VAULT_FILE", str(tmp_path / "vault.json"))
    client = TestClient(backend_api.app)
    room_id = "nomock_e2e_room"

    # 0. Gerçek güvenlik kapısı: kasa kilitliyken /api/lilith/strategy 423 ile reddeder
    locked_resp = client.post(
        "/api/lilith/strategy",
        json={"client_id": room_id, "instruction": "Karşı hamle üret", "target_username": "mimar_deniz"},
    )
    assert locked_resp.status_code == 423, locked_resp.text

    # 1. Gerçek /api/vault + /api/vault/unlock HTTP akışıyla kilidi aç
    # (Gerçek VaultPayload şeması: `api_key` alanı, _is_real_key doğrulamasından geçer)
    seal = client.post(
        "/api/vault",
        json={"client_id": room_id, "api_key": "sk-or-v1-9f8e7d6c5b4a3210fedcba9876543210"},
    )
    assert seal.status_code == 200, seal.text
    unlock = client.post("/api/vault/unlock", json={"client_id": room_id})
    assert unlock.status_code == 200, unlock.text

    # 2. Gerçek /api/brain/capabilities (2-profil durumu + bağlı motorlar)
    cap_resp = client.get(f"/api/brain/capabilities?client_id={room_id}")
    assert cap_resp.status_code == 200
    cap_data = cap_resp.json()
    assert cap_data["vault_locked"] is False
    # wired_pipelines artık TÜRETİLMİŞ envanter: giriş başına {"available", "reason"}
    assert cap_data["wired_pipelines"]["lilith_strategy"]["available"] is True
    assert cap_data["wired_pipelines"]["hook_studio"]["available"] is True
    for name, entry in cap_data["wired_pipelines"].items():
        assert set(entry) >= {"available", "reason"}, f"{name}: türetilmişenvanter şeması eksik"
        if not entry["available"]:
            assert entry["reason"], f"{name}: kapalıysa sebep yazılmalıdır"
    assert cap_data["profiles"]["local_core"]["total_count"] == 7
    assert cap_data["profiles"]["consent_only"]["total_count"] == 1
    assert cap_data["profiles"]["consent_only"]["flags"]["ENABLE_CROSS_PLATFORM"] is False
    assert cap_data["profiles"]["external_keyed"]["total_count"] == 9

    # 3. Gerçek /api/lilith/strategy (LilithGrowthAgent + ShadowExecutor + gerçek generate_hook_package)
    sample = _real_sample_input()
    l_resp = client.post(
        "/api/lilith/strategy",
        json={
            "client_id": room_id,
            "instruction": "İlk temas kancası ve 3 dallı karşı hamle hazırla",
            "target_username": "mimar_deniz",
            "target_profile": sample["target_profile"],
        },
    )
    assert l_resp.status_code == 200, l_resp.text
    l_data = l_resp.json()
    assert l_data["status"] == "ok"
    assert l_data["agent"] == "lilith"
    assert l_data["evidence_grounded"] is True
    # Görev motoru KOŞMADAN çağrılan strateji hattında motor sinyali YOKTUR:
    # nöro formülü UYDURULMAZ — metrics üretilmez, açık sebep yazılır.
    # (Gerçek motor sinyaliyle NeuroMetrics üretimi test_zero_mock_executor_*
    # fonksiyonunda uçtan uca doğrulanır.)
    assert l_data["neuro_metrics"] is None
    assert l_data["metrics_source"] == "engine_signals_missing"
    assert isinstance(l_data["hook_studio"], dict)
    assert l_data["hook_studio"]["opening_message"]
    assert len(l_data["counter_moves"]) == 3
    assert {m["scenario"] for m in l_data["counter_moves"]} == {"savunmaci", "agresif", "merakli"}
    # Dürüstlük: dış LLM anahtarı geçersiz/ulaşılmazsa sessizce başarı iddia etmez, fallback_reason yazar
    assert l_data["hook_studio"]["fallback_reason"] is not None or l_data["hook_studio"]["data_confidence"] is not None

    # 4. Gerçek /api/brain/route → Lilith / Graph / Memory / Company (kapalı kapı dürüst bildirimi)
    br_lilith = client.post(
        "/api/brain/route",
        json={"client_id": room_id, "message": "Lilith buna karşı hamle hazırla", "target": "mimar_deniz"},
    )
    assert br_lilith.status_code == 200
    assert br_lilith.json()["route"] == "lilith"
    assert len(br_lilith.json()["result"]["counter_moves"]) == 3

    br_graph = client.post(
        "/api/brain/route",
        json={"client_id": room_id, "message": "İlişki grafını çiz"},
    )
    assert br_graph.status_code == 200
    assert br_graph.json()["route"] == "graph"

    br_company = client.post(
        "/api/brain/route",
        json={"client_id": room_id, "message": "denizstudio.com şirket taraması yap"},
    )
    assert br_company.status_code == 200
    comp_body = br_company.json()
    assert comp_body["route"] == "company"
    assert comp_body["domain"] == "denizstudio.com"
    # strict profilde kapı kapalıysa dürüstçe available=False + reason döner (hata yutulmaz!)
    assert "available" in comp_body["result"]
    if not comp_body["result"]["available"]:
        assert comp_body["result"]["reason"], "Kapalı kapıda sebep boş bırakılamaz!"


def test_zero_mock_aspasia_command_enforces_minor_and_vault_gates(tmp_path, monkeypatch):
    """ZERO MOCK: /api/aspasia/command ve _aspasia_command_dispatch reşitlik (451) + kasa (423) kapılarını atlayamaz."""
    monkeypatch.setattr(backend_api, "VAULT_FILE", str(tmp_path / "vault_cmd.json"))
    client = TestClient(backend_api.app)
    room_id = "nomock_aspasia_cmd_gates"

    # 1. Çocuk vakası beyan edilmişse (şartsız) → 451 (kasa kapısından bile ÖNCE reddeder)
    minor_set = client.post(
        "/api/minor/case",
        json={"client_id": room_id, "subject_is_minor": True},
    )
    assert minor_set.status_code == 200, minor_set.text
    blocked_minor = client.post(
        "/api/aspasia/command",
        json={
            "client_id": room_id,
            "user_message": "https://www.instagram.com/mimar_deniz/ profilini analiz et",
        },
    )
    assert blocked_minor.status_code == 451, blocked_minor.text
    # Doğrudan iç dispatch fonksiyonu da reddetmeli (savunma derinliği)
    assert (
        backend_api._aspasia_command_dispatch(
            {"client_id": room_id, "target_url": "https://www.instagram.com/mimar_deniz/", "goals": []}
        )
        is None
    )

    # 2. Çocuk vakası temizlenince kasa hâlâ kilitli → 423 VAULT_LOCKED
    minor_clr = client.post("/api/minor/clear", json={"client_id": room_id})
    assert minor_clr.status_code == 200, minor_clr.text
    blocked_vault = client.post(
        "/api/aspasia/command",
        json={
            "client_id": room_id,
            "user_message": "https://www.instagram.com/mimar_deniz/ profilini analiz et",
        },
    )
    assert blocked_vault.status_code == 423, blocked_vault.text
    assert blocked_vault.json()["error"]["code"] == "VAULT_LOCKED"
    assert (
        backend_api._aspasia_command_dispatch(
            {"client_id": room_id, "target_url": "https://www.instagram.com/mimar_deniz/", "goals": []}
        )
        is None
    )

    # 3. Gerçek /api/vault + /api/vault/unlock sonrası kapılardan geçer ve komut katmanına ulaşır
    seal = client.post(
        "/api/vault",
        json={"client_id": room_id, "api_key": "sk-or-v1-9f8e7d6c5b4a3210fedcba9876543210"},
    )
    assert seal.status_code == 200, seal.text
    unlock = client.post("/api/vault/unlock", json={"client_id": room_id})
    assert unlock.status_code == 200, unlock.text

    # URL içermeyen komut: kapılardan geçti (423/451 değil, 200) ve gerçek AspasiaCommandGateway reddi döndü
    passed_gates = client.post(
        "/api/aspasia/command",
        json={"client_id": room_id, "user_message": "Sadece merhaba"},
    )
    assert passed_gates.status_code == 200, passed_gates.text
    body = passed_gates.json()
    assert body["accepted"] is False
    assert body["reason"]

