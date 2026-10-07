"""Maigret entegrasyon sözleşme testleri (FAZ 2).

İlkeler:
- Kapı (ENABLE_MAIGRET) kapalıyken davranış ESKİSİ GİBİ (pipeline değişmez).
- Kütüphane/DB/timeout hatalarında dürüst `available:false` + sebep; uydurma yok.
- Güvenilir yokluk yalnız sıfır hata koşulunda iddia edilir.
- Agent birleştirmesi: yalnız gerçek gözlemler platform listesine girer.
"""
import pytest
from unittest.mock import AsyncMock, patch

import asyncio

from agent_core.agents.osint_investigator import OsintInvestigatorAgent
from agent_core.services import maigret_scanner
from agent_core.services.maigret_scanner import (
    MaigretScanResult,
    MaigretSiteHit,
    sanitize_username,
    scan_username,
)
from agent_core.services.llm_gateway import LLMGateway


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)
    monkeypatch.setattr(LLMGateway, "query", AsyncMock(side_effect=RuntimeError("no llm")))
    monkeypatch.setattr(LLMGateway, "query_json", AsyncMock(side_effect=RuntimeError("no llm")))
    # [FAZ A] Ajan artık tarayıcıyı doğrudan değil CAPABILITY OMURGASINDAN
    # çağırıyor. Kütüphane yokluğu denetimi (`_module_available`) testte
    # aşılır; asıl davranış servis mock'uyla sınanır.
    from agent_core.capabilities import adapters_osint
    monkeypatch.setattr(adapters_osint, "_module_available", lambda _name: True)


def _res(username="soxoj", available=True, found=None, scanned=10, errors=0, reason=None):
    return MaigretScanResult(
        requested_username=username,
        available=available,
        reason=reason,
        found_sites=found or [],
        scanned_count=scanned,
        error_count=errors,
    )


class TestGate:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
        res = await scan_username("soxoj")
        assert res.available is False
        assert res.reason == "disabled"

    @pytest.mark.asyncio
    async def test_gate_on_runs_scan(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        called = {}

        from maigret.result import MaigretCheckStatus

        class _R:
            status = MaigretCheckStatus.AVAILABLE
            url_user = ""

        async def _fake_library(username, site_dict, timeout):
            called["ran"] = True
            return {"A": _R(), "B": _R()}

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"A": object(), "B": object()})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_library)
        res = await scan_username("soxoj", limit=2)
        assert called.get("ran") is True
        assert res.scanned_count == 2
        assert res.available is True  # sıfır hata + sıfır eşleşme = güvenilir yokluk
        assert res.found_sites == []

    @pytest.mark.asyncio
    async def test_empty_result_is_provider_error(self, monkeypatch):
        """Sağlayıcı hiç sonuç döndürmezse bu güvenilir yokluk DEĞİLDİR."""
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        async def _fake_library(username, site_dict, timeout):
            return {}

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"A": 1, "B": 2})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_library)
        res = await scan_username("soxoj", limit=2)
        assert res.available is False
        assert res.reason == "provider_errors"

    @pytest.mark.asyncio
    async def test_none_status_is_error_not_absence(self, monkeypatch):
        """[ADLI DUZELTME] status=None = checker future'i istisna ile oldu.
        Bu site HATA sayilir; yoksa sistem kontrolsuz 'iz yok' derdi (halusinasyon riski)."""
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        class _R:
            status = None  # future exception ornegi
            url_user = ""

        async def _scan(username, site_dict, timeout):
            return {"A": _R(), "B": _R()}

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"A": 1, "B": 2})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _scan)
        res = await scan_username("soxoj", limit=2)
        assert res.available is False
        assert res.reason == "provider_errors"
        assert res.error_count == 2
        assert res.scanned_count == 2


class TestSanitize:
    def test_strips_at(self):
        assert sanitize_username("@User.Name") == "User.Name"

    def test_rejects_invalid(self):
        assert sanitize_username("bad name!") is None
        assert sanitize_username("") is None
        assert sanitize_username("x" * 65) is None


class TestHonestDegradation:
    @pytest.mark.asyncio
    async def test_library_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        def _boom(top):
            raise ModuleNotFoundError("maigret yok", name="maigret")

        monkeypatch.setattr(maigret_scanner, "_get_site_dict", _boom)
        res = await scan_username("soxoj")
        assert res.available is False
        assert res.reason == "library_missing"

    @pytest.mark.asyncio
    async def test_installed_dependency_import_crash_is_not_called_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        def _boom(top):
            raise ImportError("maigret internal import failed")

        monkeypatch.setattr(maigret_scanner, "_get_site_dict", _boom)
        res = await scan_username("soxoj")
        assert res.available is False
        assert res.reason == "dependency_broken"

    @pytest.mark.asyncio
    async def test_invalid_username(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        res = await scan_username("geçersiz isim!")
        assert res.available is False
        assert res.reason == "invalid_username"

    @pytest.mark.asyncio
    async def test_timeout_is_honest(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        async def _hang(username, site_dict, timeout):
            await asyncio.sleep(999)

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"A": 1, "B": 2, "C": 3})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _hang)
        monkeypatch.setattr(maigret_scanner, "_env_int", lambda name, default, maximum: 0.05 if name == "MAIGRET_TOTAL_TIMEOUT" else default)
        res = await scan_username("soxoj", limit=3)
        assert res.available is False
        assert res.reason == "timeout"

    @pytest.mark.asyncio
    async def test_all_provider_errors_not_claimed_as_absence(self, monkeypatch):
        """Tüm siteler hatalıysa 'hiç iz yok' ASLA denmez (dürüstlük çekirdeği)."""
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        class _Status:
            UNKNOWN = "unknown"

        class _R:
            def __init__(self, status):
                self.status = status
            url_user = ""

        from maigret.result import MaigretCheckStatus

        async def _fail_scan(username, site_dict, timeout):
            return {"A": _R(MaigretCheckStatus.UNKNOWN), "B": _R(MaigretCheckStatus.UNKNOWN)}

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"A": 1, "B": 2})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fail_scan)
        res = await scan_username("soxoj", limit=2)
        assert res.available is False
        assert res.reason == "provider_errors"
        assert res.error_count == 2

    @pytest.mark.asyncio
    async def test_found_sites_extracted(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")

        class _R:
            def __init__(self, status, url=""):
                self.status = status
                self.url_user = url

        from maigret.result import MaigretCheckStatus

        async def _scan(username, site_dict, timeout):
            return {
                "GitHub": _R(MaigretCheckStatus.CLAIMED, "https://github.com/soxoj"),
                "SiteX": _R(MaigretCheckStatus.AVAILABLE),
            }

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", lambda top: {"GitHub": 1, "SiteX": 2})
        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _scan)
        res = await scan_username("soxoj", limit=2)
        assert res.available is True
        assert len(res.found_sites) == 1
        assert res.found_sites[0].site == "GitHub"
        assert res.found_sites[0].url == "https://github.com/soxoj"
        assert res.scanned_count == 2


class TestAgentMerge:
    async def _fallback_profile(self):
        """`policy` alanı kasa gerçeğini taşır (üretimde api.py enjekte eder)."""
        agent = OsintInvestigatorAgent()
        return await agent.execute({
            "target_profile": {"username": "@soxoj", "bio": "x"},
            "policy": {"vault_locked": False},
        })

    @pytest.mark.asyncio
    async def test_gate_off_keeps_profile_unchanged(self, monkeypatch):
        monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
        profile = await self._fallback_profile()
        assert profile.data_confidence is False
        assert profile.fallback_reason == "provider_credentials_unavailable"
        assert profile.associated_platforms == []
        # Omurga reddi: kapı kapalı -> makine-okunur sebep, site UYDURULMAZ.
        assert "gate_disabled" in profile.username_scan["reason"]

    @pytest.mark.asyncio
    async def test_found_sites_merge_into_platforms(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        hit = MaigretSiteHit(site="GitHub", url="https://github.com/soxoj")
        scan = _res(found=[hit], scanned=10, errors=0)
        with patch("agent_core.services.maigret_scanner.scan_username", AsyncMock(return_value=scan)):
            profile = await self._fallback_profile()
        assert "GitHub" in profile.associated_platforms
        assert profile.data_confidence is True
        assert profile.confidence == 0.1  # 1/10 gözlenen kapsama
        assert profile.username_scan["found_sites"][0]["site"] == "GitHub"
        # [FAZ A] Aynı bulgu artık MÜHÜRLÜ KANIT: zaman çizelgesine girdi.
        assert profile.username_scan_sealed == 1
        entries = profile.username_scan_evidence["entries"]
        assert entries and entries[0]["source_engine"] == "maigret"

    @pytest.mark.asyncio
    async def test_unavailable_scan_keeps_profile_and_embeds_provenance(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        scan = _res(available=False, reason="provider_errors", scanned=10, errors=10)
        with patch("agent_core.services.maigret_scanner.scan_username", AsyncMock(return_value=scan)):
            profile = await self._fallback_profile()
        assert profile.data_confidence is False  # profil değişmedi
        assert profile.fallback_reason == "provider_credentials_unavailable"
        assert profile.username_scan["reason"] == "provider_errors"

    @pytest.mark.asyncio
    async def test_confident_absence_marks_no_match(self, monkeypatch):
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        scan = _res(available=True, found=[], scanned=8, errors=0)
        with patch("agent_core.services.maigret_scanner.scan_username", AsyncMock(return_value=scan)):
            profile = await self._fallback_profile()
        assert profile.data_confidence is True
        assert profile.confidence == 0.0
        assert profile.fallback_reason == "username_scan_no_match"


class TestEndpoint:
    def test_endpoint_disabled_by_default(self, monkeypatch, vault_open):
        from fastapi.testclient import TestClient
        from backend.api import app

        monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
        with TestClient(app) as client:
            r = client.post("/api/experimental/maigret/scan", json={"username": "soxoj"})
        assert r.status_code == 200
        assert r.json()["reason"] == "disabled"
