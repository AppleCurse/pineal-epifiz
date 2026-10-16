"""Faz 2 · P1 Derin Profilleme Hattı ve P2 Çapraz Profilleme Sözleşme Testleri.

Sözleşme kuralları:
1. P1.1 Holehe Kablo Bağlantısı:
   - Hedef e-postası (target_profile.email / bio / search_snippets) tespit edilirse Holehe'ye iletilir.
   - E-posta bulunamazsa sessizce kaybolmaz; dürüstçe 'no_target_email' gerekçesiyle not_run yazılır.
2. P1.2 detected_urls & SOCID Kablo Bağlantısı:
   - Arama sonuçlarından tespit edilen URL'ler omurgadan (extractor.identity.socid) çözülür.
   - Kasa kilitliyken dış istek yapılmaz (vault_locked).
   - Çıkarılan alanlar EvidenceItem (epistemic_type="observation") olarak kanıt zincirine ve zaman çizgisine girer.
   - profile.deep_scan kanalı "not_attempted" yerine gerçek koşu durumuyla güncellenir.
3. P2 Çapraz Profilleme:
   - Farklı platform hesapları deterministik kurallarla eşleştirilir (exact_handle, normalized_handle, cross_link).
   - Eşleşmeler EvidenceItem (epistemic_type="inference") olarak mühürlenir.
"""

import pytest
from unittest.mock import AsyncMock, patch

from agent_core.agents.osint_investigator import OsintInvestigatorAgent, OsintProfile
from agent_core.capabilities.base import Availability, CapabilityResult, make_evidence
from agent_core.domain.channel_status import ChannelRun
from agent_core.domain.evidence_models import EvidenceItem
from agent_core.services.cross_profiler import (
    CrossProfileCorrelation,
    _detect_platform_and_handle,
    _normalize_handle,
    correlate_profiles,
)
from agent_core.services.deep_profile_resolver import resolve_deep_profiles
from agent_core.services.holehe_scanner import HoleheScanResult, HoleheSiteHit
from agent_core.services.socid_enricher import SocidRecord


# ==============================================================================
# P1.1: E-Posta Tespiti & Holehe Bağlantısı
# ==============================================================================

class TestP1HolehePipeline:
    def test_extract_candidate_emails_from_various_sources(self):
        target = {
            "email": "primary@example.com",
            "bio": "Developer at Acme. Contact: dev_contact@company.org or invalid-email",
            "connected_emails": ["alt@domain.net"],
        }
        payload = {
            "search_snippets": [
                {"text": "Found personal site: reach out to freelance@work.io for inquiries."}
            ]
        }
        extracted = OsintInvestigatorAgent._extract_candidate_emails(target, payload)
        assert "primary@example.com" in extracted
        assert "alt@domain.net" in extracted
        assert "dev_contact@company.org" in extracted
        assert "freelance@work.io" in extracted
        assert len(extracted) == 4

    @pytest.mark.asyncio
    async def test_holehe_triggered_when_email_found_in_bio(self, monkeypatch):
        monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)
        monkeypatch.setenv("ENABLE_HOLEHE", "true")

        called_email = None

        async def _mock_apply_email_scan(profile, email, payload=None):
            nonlocal called_email
            called_email = email
            scan = HoleheScanResult(
                requested_email=email,
                available=True,
                found_sites=[HoleheSiteHit(site="github", domain="github.com")],
                scanned_count=10,
                error_count=0,
            )
            return profile.model_copy(update={
                "associated_platforms": ["github"],
                "data_confidence": True,
                "confidence": 0.5,
                "email_scan": scan.model_dump(),
            })

        agent = OsintInvestigatorAgent()
        monkeypatch.setattr(agent, "_apply_email_scan", _mock_apply_email_scan)

        payload = {
            "target_profile": {
                "username": "@johndoe",
                "bio": "Say hi at john.doe@example.com",
            }
        }
        res = await agent.execute(payload)
        assert called_email == "john.doe@example.com"
        assert res.connected_emails == ["john.doe@example.com"]
        assert "github" in res.associated_platforms
        assert res.email_scan is not None
        assert res.email_scan["available"] is True

    @pytest.mark.asyncio
    async def test_holehe_records_no_target_email_when_missing(self, monkeypatch):
        monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)

        agent = OsintInvestigatorAgent()
        payload = {
            "target_profile": {
                "username": "@cleanuser",
                "bio": "Just a user with no email listed",
            }
        }
        res = await agent.execute(payload)
        assert res.connected_emails == []
        assert res.email_scan is not None
        assert res.email_scan["available"] is False
        assert res.email_scan["reason"] == "no_target_email"


# ==============================================================================
# P1.2: detected_urls & SOCID Omurga Bağlantısı
# ==============================================================================

class TestP1DeepProfileResolver:
    @pytest.mark.asyncio
    async def test_resolver_enforces_vault_lock(self):
        urls = ["https://twitter.com/testuser", "https://instagram.com/testuser"]
        payload = {"policy": {"vault_locked": True}}

        items, channels, idents = await resolve_deep_profiles(urls, payload=payload)
        assert items == []
        assert idents == []
        assert len(channels) == 1
        assert channels[0].status == "not_run"
        assert channels[0].reason == "vault_locked"

    @pytest.mark.asyncio
    async def test_resolver_reports_dependency_missing(self, monkeypatch):
        urls = ["https://github.com/coder"]
        payload = {"policy": {"vault_locked": False}}

        from agent_core.capabilities import adapters_osint
        monkeypatch.setattr(adapters_osint, "_module_available", lambda name: False if name == "socid_extractor" else True)

        items, channels, idents = await resolve_deep_profiles(urls, payload=payload)
        assert items == []
        assert idents == []
        assert len(channels) == 1
        assert channels[0].status == "not_run"
        assert channels[0].reason == "dependency_missing:socid_extractor"

    @pytest.mark.asyncio
    async def test_resolver_extracts_evidence_items_when_available(self, monkeypatch):
        urls = ["https://site.test/photoguy", "https://other.test/photoguy"]
        payload = {"policy": {"vault_locked": False}}

        ev_item = make_evidence(
            content="profile identity extracted from https://site.test/photoguy: id=123",
            source_engine="socid_extractor",
            epistemic_type="observation",
            provenance_refs=["https://site.test/photoguy"],
        )
        fake_record = SocidRecord(
            source_url="https://site.test/photoguy",
            available=True,
            fields={"user_id": "123", "username": "photoguy"},
        )
        fake_result = CapabilityResult(
            capability_id="extractor.identity.socid",
            available=True,
            items=(ev_item,),
            payload=fake_record,
        )

        async def _mock_run_cap(cap_id, ctx, state=None):
            if ctx.subject == "https://site.test/photoguy":
                return fake_result
            return CapabilityResult(
                capability_id=cap_id,
                available=True,
                items=(),
                payload=SocidRecord(source_url=ctx.subject, available=False, reason="no_record"),
            )

        monkeypatch.setattr("agent_core.services.deep_profile_resolver.run_capability", _mock_run_cap)
        from agent_core.capabilities import adapters_osint
        monkeypatch.setattr(adapters_osint, "_module_available", lambda _: True)

        items, channels, idents = await resolve_deep_profiles(urls, payload=payload)
        assert len(items) == 1
        assert items[0].epistemic_type == "observation"
        assert items[0].source_engine == "socid_extractor"
        assert len(idents) == 1
        assert idents[0]["fields"]["user_id"] == "123"
        scan_ch = next(c for c in channels if c.channel == "profile.deep_scan")
        assert scan_ch.status == "ok"
        assert "1/2 profilden" in scan_ch.detail

    def test_url_classified_to_correct_sensor(self):
        """P1: URL -> doğru platform ve sensör/çıkarıcı eşleşmesi."""
        from agent_core.services.platform_registry import classify_profile_url

        x_info = classify_profile_url("https://x.com/cyber_target")
        assert x_info["platform"] == "x"
        assert x_info["handle"] == "cyber_target"
        assert x_info["sensor_id"] == "sensor.x.twscrape"
        assert x_info["extractor_id"] == "extractor.identity.socid"

        ig_info = classify_profile_url("https://instagram.com/visual_target")
        assert ig_info["platform"] == "instagram"
        assert ig_info["handle"] == "visual_target"
        assert ig_info["sensor_id"] == "sensor.ig.instagrapi"

        web_info = classify_profile_url("https://github.com/coder_target")
        assert web_info["platform"] == "web"
        assert web_info["sensor_id"] is None
        assert web_info["extractor_id"] == "extractor.identity.socid"

    @pytest.mark.asyncio
    async def test_sensor_disabled_reports_not_run_with_reason(self, monkeypatch):
        """P1: Sensör kapalıysa P0 not_run + sebep üretilir, sessizce yutulmaz."""
        monkeypatch.delenv("ENABLE_X_SENSOR", raising=False)
        from agent_core.capabilities import adapters_osint
        monkeypatch.setattr(adapters_osint, "_module_available", lambda _: True)

        urls = ["https://x.com/target_x"]
        payload = {"policy": {"vault_locked": False, "rate_ok": True}}

        items, channels, idents = await resolve_deep_profiles(urls, payload=payload)
        ch_map = {c.channel: c for c in channels}
        assert "sensor.x.twscrape" in ch_map
        assert ch_map["sensor.x.twscrape"].status == "not_run"
        assert "gate_disabled" in (ch_map["sensor.x.twscrape"].reason or "")

    @pytest.mark.asyncio
    async def test_call_path_uses_egress(self, monkeypatch):
        """P1: Profil çıkarma çağrı yolu egress.py'den geçer ve deneme kaydı bırakır."""
        from agent_core.capabilities.egress import drain_egress_attempts, egress_attempts
        from agent_core.services.socid_enricher import extract_profile

        drain_egress_attempts()

        # Sahte HTTP yanıtı taklidi (mock safe_get)
        dummy_resp = type("Resp", (), {"status_code": 200, "text": "<html><div data-id='test'>info</div></html>"})()
        monkeypatch.setattr("agent_core.utils.security.safe_get", AsyncMock(return_value=dummy_resp))
        monkeypatch.setattr("agent_core.services.socid_enricher.extract_from_html",
                            lambda html, source_url: SocidRecord(source_url=source_url, available=True, fields={"uid": "99"}))

        rec = await extract_profile("https://example.com/test_user")
        assert rec.available is True

        attempts = drain_egress_attempts()
        assert len(attempts) >= 1
        assert attempts[0]["purpose"] == "osint"
        assert "example.com" in attempts[0]["target"]



# ==============================================================================
# P2: Çapraz Profilleme Motoru (Cross-Profiler)
# ==============================================================================

class TestP2CrossProfiler:
    def test_normalize_handle(self):
        assert _normalize_handle("@John.Doe_99") == "johndoe99"
        assert _normalize_handle("alice-smith") == "alicesmith"

    def test_detect_platform_and_handle(self):
        plat, handle, u = _detect_platform_and_handle("https://twitter.com/dev_guru")
        assert plat == "x"
        assert handle == "dev_guru"

        plat, handle, u = _detect_platform_and_handle("https://instagram.com/travel_nomad")
        assert plat == "instagram"
        assert handle == "travel_nomad"

        plat, handle, u = _detect_platform_and_handle("https://linkedin.com/in/corp-exec")
        assert plat == "linkedin"
        assert handle == "corp-exec"

    def test_correlate_profiles_exact_match(self):
        tp = {
            "username": "@cyber_alice",
            "platform": "instagram",
            "detected_urls": [
                "https://x.com/cyber_alice",
                "https://github.com/cyber_alice",
            ],
        }
        res = correlate_profiles(tp)
        assert isinstance(res, CrossProfileCorrelation)
        assert res.cluster_count >= 2
        # Exact match confidence is 0.85
        for m in res.matches:
            assert m.match_method == "exact_handle"
            assert m.confidence == 0.85
            assert m.epistemic_type == "inference"

        assert len(res.items) == res.cluster_count
        for item in res.items:
            assert isinstance(item, EvidenceItem)
            assert item.epistemic_type == "inference"
            assert item.source_engine == "cross_profiler"
            assert "Çapraz profil korelasyonu" in item.content

    def test_correlate_profiles_bio_cross_link_gives_highest_confidence(self):
        tp = {
            "username": "@main_hero",
            "platform": "instagram",
            "bio": "Follow my work on https://github.com/main_hero_codes and x.com/main_hero",
            "detected_urls": [
                "https://github.com/main_hero_codes",
            ],
        }
        res = correlate_profiles(tp)
        bio_matches = [m for m in res.matches if m.match_method == "cross_link"]
        assert len(bio_matches) >= 1
        assert bio_matches[0].confidence == 0.95
        assert bio_matches[0].epistemic_type == "inference"

    def test_correlate_profiles_normalized_match(self):
        tp = {
            "username": "@john_doe",
            "platform": "instagram",
            "detected_urls": [
                "https://x.com/johndoe",
            ],
        }
        res = correlate_profiles(tp)
        norm_matches = [m for m in res.matches if m.match_method == "normalized_handle"]
        assert len(norm_matches) == 1
        assert norm_matches[0].confidence == 0.70
        assert norm_matches[0].epistemic_type == "inference"


# ==============================================================================
# Pipeline Entegrasyon Doğrulaması (TaskExecutor)
# ==============================================================================

class TestP1P2ExecutorIntegration:
    @pytest.mark.asyncio
    async def test_executor_integrates_deep_scan_and_cross_profiling(self, monkeypatch):
        """TaskExecutor'ın detected_urls ve çapraz profil kanıtlarını zincire bağladığını doğrular."""
        from agent_core.task_executor import PinealExecutor
        from agent_core.services.llm_gateway import LLMGateway

        # Hermetik LLM guard
        monkeypatch.setattr(LLMGateway, "query", AsyncMock(return_value="Analiz metni"))
        monkeypatch.setattr(LLMGateway, "query_json", AsyncMock(return_value={}))
        monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)

        ev_item = make_evidence(
            content="profile identity extracted from https://x.com/alice_in_chains: user_id=42",
            source_engine="socid_extractor",
            epistemic_type="observation",
            provenance_refs=["https://x.com/alice_in_chains"],
        )
        fake_record = SocidRecord(
            source_url="https://x.com/alice_in_chains",
            available=True,
            fields={"user_id": "42", "username": "alice_in_chains"},
        )
        fake_result = CapabilityResult(
            capability_id="extractor.identity.socid",
            available=True,
            items=(ev_item,),
            payload=fake_record,
        )

        async def _mock_run_cap(cap_id, ctx, state=None):
            return fake_result

        monkeypatch.setattr("agent_core.services.deep_profile_resolver.run_capability", _mock_run_cap)
        from agent_core.capabilities import adapters_osint
        monkeypatch.setattr(adapters_osint, "_module_available", lambda _: True)

        executor = PinealExecutor()

        # Sahte minimal payload
        payload = {
            "target_profile": {
                "username": "@alice_in_chains",
                "name": "Alice",
                "bio": "Audio engineer and coder. Contact: alice@audio.test",
                "platform": "instagram",
                "posts": ["post 1"],
                "detected_urls": ["https://x.com/alice_in_chains"],
            },
            "policy": {"vault_locked": False},
        }

        # Sadece discovery ve forensic adımlarını kontrol etmek için execute_task çalıştır
        res = await executor.execute_task(payload, "test-task-p1-p2")

        # 1. Kanal durumunda holehe ve deep_scan olmalı
        channels = {c.get("channel"): c for c in getattr(res, "channel_status", [])}
        assert "profile.deep_scan" in channels
        assert channels["profile.deep_scan"]["status"] == "ok"
        assert "sensor.identity.holehe" in channels

        # 2. Forensic evidence içinde socid observation ve cross_profiler inference olmalı
        forensic_items = payload.get("forensic_evidence") or []
        engines = [item.get("source_engine") for item in forensic_items if isinstance(item, dict)]
        assert "socid_extractor" in engines
        assert "cross_profiler" in engines

        # 3. Çapraz profil çıkarım tipi "inference" olmalı
        cross_items = [item for item in forensic_items if item.get("source_engine") == "cross_profiler"]
        assert len(cross_items) >= 1
        assert cross_items[0]["epistemic_type"] == "inference"

