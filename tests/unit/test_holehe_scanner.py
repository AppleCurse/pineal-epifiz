"""Holehe entegrasyon sözleşme testleri (FAZ 3).

İlkeler:
- Kapı (ENABLE_HOLEHE) kapalıyken davranış ESKİSİ GİBİ (pipeline değişmez).
- Kütüphane/timeout hatalarında dürüst `available:false` + sebep; uydurma yok.
- ADLİ KURAL: holehe launch_module istisnaları `rateLimit=True, exists=False`
  olarak yazar — bunlar HATA sayılır; kapalı ağ asla "kayıtlı değil" doğurmaz.
- Güvenilir yokluk yalnız sıfır hata koşulunda iddia edilir.
- Agent birleştirmesi: yalnız gerçek gözlemler platform listesine girer;
  güven mevcut değerin altına inmez.
"""
import pytest
from unittest.mock import AsyncMock, patch

from agent_core.agents.osint_investigator import OsintInvestigatorAgent
from agent_core.services import holehe_scanner
from agent_core.services.holehe_scanner import (
    HoleheScanResult,
    _classify,
    sanitize_email,
    scan_email,
)
from agent_core.services.llm_gateway import LLMGateway


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)
    monkeypatch.setattr(LLMGateway, "query", AsyncMock(side_effect=RuntimeError("no llm")))
    monkeypatch.setattr(LLMGateway, "query_json", AsyncMock(side_effect=RuntimeError("no llm")))
    # [FAZ A] Ajan taramayı doğrudan değil CAPABILITY OMURGASINDAN çağırır;
    # kütüphane yokluğu denetimi testte aşılır, davranış servis mock'uyla sınanır.
    from agent_core.capabilities import adapters_osint
    monkeypatch.setattr(adapters_osint, "_module_available", lambda _name: True)


def _fn_named(name, behavior, payload=None):
    """holehe launch_module'e uygun sahte modül: async fn(email, client, out).

    behavior: 'found' | 'clean' | 'raise' | 'silent' | 'weird'
    İsimler launch_module'ün domain sözlüğünde gerçek anahtar olmalı
    (istisna yolu orada isimle domain arıyor): amazon/twitter/github.
    """

    async def _fn(email, client, out):
        if behavior == "found":
            out.append({"name": name, "domain": payload or f"{name}.com",
                        "exists": True, "emailrecovery": None,
                        "phoneNumber": None, "others": None})
        elif behavior == "clean":
            out.append({"name": name, "domain": payload or f"{name}.com",
                        "exists": False, "rateLimit": False,
                        "emailrecovery": None, "phoneNumber": None, "others": None})
        elif behavior == "raise":
            raise ConnectionError("kapalı ağ (dürüst senaryo)")
        elif behavior == "silent":
            return  # hüküm yok
        elif behavior == "weird":
            out.append({"name": name, "exists": None})
    _fn.__name__ = name
    return _fn


def _res(email="a@b.com", available=True, found=None, scanned=10, errors=0, reason=None):
    return HoleheScanResult(
        requested_email=email,
        available=available,
        reason=reason,
        found_sites=found or [],
        scanned_count=scanned,
        error_count=errors,
    )


class TestGate:
    @pytest.mark.asyncio
    async def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_HOLEHE", raising=False)
        res = await scan_email("a@b.com")
        assert res.available is False
        assert res.reason == "disabled"
        assert res.found_sites == []

    @pytest.mark.asyncio
    async def test_gate_on_runs_injected_modules(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        res = await scan_email(
            "a@b.com",
            modules=[_fn_named("amazon", "found"), _fn_named("twitter", "clean")],
            site_timeout=5,
        )
        assert res.available is True
        assert res.reason is None
        assert [h.site for h in res.found_sites] == ["amazon"]
        assert res.scanned_count == 2
        assert res.error_count == 0


class TestSanitize:
    def test_strips_whitespace(self):
        assert sanitize_email("  a@b.co  ") == "a@b.co"

    @pytest.mark.parametrize("bad", ["", "not-an-email", "a@b", "@b.com",
                                     "a b@c.com", "x" * 250 + "@b.com"])
    def test_rejects_invalid(self, bad):
        assert sanitize_email(bad) is None

    @pytest.mark.asyncio
    async def test_invalid_email_reason(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        res = await scan_email("kesinlikle-eposta-degil")
        assert res.available is False
        assert res.reason == "invalid_email"


class TestHonestFailures:
    @pytest.mark.asyncio
    async def test_library_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")

        def _boom(limit):
            raise ModuleNotFoundError("holehe yok", name="holehe")

        monkeypatch.setattr(holehe_scanner, "_load_modules", _boom)
        res = await scan_email("a@b.com")
        assert res.available is False
        assert res.reason == "library_missing"

    @pytest.mark.asyncio
    async def test_installed_dependency_import_crash_is_not_called_missing(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")

        def _boom(limit):
            raise ImportError("holehe internal import failed")

        monkeypatch.setattr(holehe_scanner, "_load_modules", _boom)
        res = await scan_email("a@b.com")
        assert res.available is False
        assert res.reason == "dependency_broken"

    @pytest.mark.asyncio
    async def test_module_load_crash_is_scan_error(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")

        def _boom(limit):
            raise RuntimeError("modül ağacı bozuk")

        monkeypatch.setattr(holehe_scanner, "_load_modules", _boom)
        res = await scan_email("a@b.com")
        assert res.reason == "scan_error"

    @pytest.mark.asyncio
    async def test_modules_limit_clamped_to_max(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        monkeypatch.setenv("HOLEHE_MODULES_LIMIT", "99999")
        seen = {}

        def _spy(limit):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(holehe_scanner, "_load_modules", _spy)
        res = await scan_email("a@b.com")
        assert seen["limit"] == holehe_scanner.MAX_MODULES_LIMIT
        # Boş modül listesi tarama DEĞİL: scanned=0 -> dürüst başarısızlık.
        assert res.available is False
        assert res.reason == "provider_errors"


class TestForensicClassification:
    """launch_module'ün rateLimit maskesi asla 'yokluk' sayılmaz."""

    @pytest.mark.asyncio
    async def test_raising_module_is_error_not_absence(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        res = await scan_email(
            "a@b.com",
            modules=[_fn_named("github", "raise"), _fn_named("twitter", "clean")],
            site_timeout=5,
        )
        assert res.error_count == 1
        assert res.scanned_count == 2
        # Eşleşme yok + hata var: güvenilir yokluk DEĞİL, dürüst başarısızlık.
        assert res.available is False
        assert res.reason == "provider_errors"
        assert res.found_sites == []

    @pytest.mark.asyncio
    async def test_all_raising_modules_never_claim_absence(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        res = await scan_email(
            "a@b.com",
            modules=[_fn_named("github", "raise"), _fn_named("twitter", "raise"),
                     _fn_named("amazon", "raise")],
            site_timeout=5,
        )
        assert res.available is False
        assert res.reason == "provider_errors"
        assert res.found_sites == []
        assert res.error_count == res.scanned_count == 3

    def test_missing_verdict_is_error(self):
        fns = [_fn_named("twitter", "silent")]
        found, scanned, errors = _classify(fns, out=[], stalled=[])
        assert (found, scanned, errors) == ([], 1, 1)

    def test_unknown_shape_is_error(self):
        fns = [_fn_named("twitter", "weird")]
        found, scanned, errors = _classify(fns, out=[], stalled=[])
        assert scanned == 1
        assert errors == 1
        assert found == []

    def test_stalled_module_is_error(self):
        fns = [_fn_named("twitter", "clean"), _fn_named("amazon", "found")]
        found, scanned, errors = _classify(
            fns, out=[{"name": "amazon", "domain": "amazon.com", "exists": True}],
            stalled=["twitter"],
        )
        assert scanned == 2
        assert errors == 1
        assert [h.site for h in found] == ["amazon"]

    @pytest.mark.asyncio
    async def test_reliable_absence_requires_zero_errors(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        res = await scan_email(
            "a@b.com",
            modules=[_fn_named("twitter", "clean"), _fn_named("github", "clean")],
            site_timeout=5,
        )
        assert res.available is True
        assert res.reason is None  # güvenilir yokluk
        assert res.found_sites == []
        assert res.error_count == 0


class TestAgentMerge:
    #: Kasa gerçeği payload'dan gelir (üretimde api.py enjekte eder).
    POLICY = {"policy": {"vault_locked": False}}

    def _profile(self, **kw):
        from agent_core.agents.osint_investigator import OsintProfile
        base = dict(connected_emails=["victim@example.com"])
        base.update(kw)
        return OsintProfile(**base)

    @pytest.mark.asyncio
    async def test_gate_off_provenance_only(self, monkeypatch):
        monkeypatch.delenv("ENABLE_HOLEHE", raising=False)
        profile = await OsintInvestigatorAgent()._apply_email_scan(
            self._profile(), "victim@example.com", self.POLICY)
        assert profile.associated_platforms == []
        assert profile.data_confidence is True
        # Omurga reddi: kapı kapalı -> makine-okunur sebep, site UYDURULMAZ.
        assert "gate_disabled" in profile.email_scan["reason"]

    @pytest.mark.asyncio
    async def test_found_sites_merge_and_confidence_monotone(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        from agent_core.services.holehe_scanner import HoleheSiteHit
        scan = _res(found=[HoleheSiteHit(site="Amazon", domain="amazon.com")],
                    scanned=10, errors=0)
        profile = self._profile(associated_platforms=["GitHub"], confidence=0.5)
        with patch("agent_core.services.holehe_scanner.scan_email",
                   AsyncMock(return_value=scan)):
            merged = await OsintInvestigatorAgent()._apply_email_scan(
                profile, "victim@example.com", self.POLICY)
        assert sorted(merged.associated_platforms) == ["Amazon", "GitHub"]
        assert merged.confidence == 0.5  # 1/10 kapsama mevcut 0.5'in altında -> ezilmez
        assert merged.email_scan["found_sites"][0]["site"] == "Amazon"
        # [FAZ A] Aynı bulgu artık MÜHÜRLÜ KANIT: zaman çizelgesine girdi.
        assert merged.email_scan_sealed == 1
        entries = merged.email_scan_evidence["entries"]
        assert entries and entries[0]["source_engine"] == "holehe"

    @pytest.mark.asyncio
    async def test_confident_absence_marks_no_match(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        scan = _res(available=True, found=[], scanned=8, errors=0)
        with patch("agent_core.services.holehe_scanner.scan_email",
                   AsyncMock(return_value=scan)):
            merged = await OsintInvestigatorAgent()._apply_email_scan(
                self._profile(), "victim@example.com", self.POLICY)
        assert merged.data_confidence is True
        assert merged.confidence == 0.0
        assert merged.fallback_reason == "email_scan_no_match"

    @pytest.mark.asyncio
    async def test_unavailable_scan_keeps_profile_fields(self, monkeypatch):
        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        scan = _res(available=False, reason="provider_errors", scanned=8, errors=8)
        with patch("agent_core.services.holehe_scanner.scan_email",
                   AsyncMock(return_value=scan)):
            merged = await OsintInvestigatorAgent()._apply_email_scan(
                self._profile(), "victim@example.com", self.POLICY)
        assert merged.associated_platforms == []
        assert merged.fallback_reason is None
        assert merged.email_scan["reason"] == "provider_errors"


class TestEndpoint:
    def test_endpoint_disabled_by_default(self, monkeypatch):
        from fastapi.testclient import TestClient
        from backend.api import app

        monkeypatch.delenv("ENABLE_HOLEHE", raising=False)
        with TestClient(app) as client:
            r = client.post("/api/experimental/holehe/scan",
                            json={"email": "a@b.com"})
        assert r.status_code == 200
        assert r.json()["reason"] == "disabled"

    def test_endpoint_gate_on_uses_scanner(self, monkeypatch):
        from fastapi.testclient import TestClient
        from backend.api import app

        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        scan = _res(available=False, reason="provider_errors", scanned=5, errors=5)
        with patch("agent_core.services.holehe_scanner.scan_email",
                   AsyncMock(return_value=scan)):
            with TestClient(app) as client:
                r = client.post("/api/experimental/holehe/scan",
                                json={"email": "a@b.com", "limit": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["provider"] == "holehe"
        assert body["reason"] == "provider_errors"
        assert body["error_count"] == 5
