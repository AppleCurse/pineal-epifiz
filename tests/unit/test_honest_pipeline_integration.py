"""[PR #136 · DEVAM] Dürüst pipeline regresyon paketi — eski kusurlar geri gelemez.

PR #136 ("Fix OSINT status honesty and continue configured sensor pipeline")
kalan görev listesindeki davranışların GERÇEK regresyon testleri. Her test,
düzeltme geri alınınca KIRMIZIYA dönmelidir (revert-doğrulama):

1. **Arama snippet'ı "gönderi" değildir** — `posts` alanına girmez;
   `search_snippets` altında, kanıt tipiyle taşınır (`content_basis` beyanı).
2. **Sağlayıcı başarısı sensörleri DEVRE DIŞI BIRAKMAZ** — OSINT Industries
   200 döndüğünde bile Maigret/Holehe koşulur (koşullu: Holehe yalnız gerçek
   e-posta girdisi varsa) ve provenance'ları (`username_scan`/`email_scan`)
   profile yazılır.
3. **Boş sağlayıcı verisi "veri güveni" sayılmaz** — 200 + boş gözlem →
   `data_confidence=False` + `fallback_reason="provider_returned_no_observations"`.
4. **Sağlayıcı HATA yolu da sensörleri atlamaz** — HTTP hata / timeout / ağ
   hatası erken `return` ile Maigret/Holehe'yi görünmez kılamaz; hata
   `fallback_reason="api_error"` + `error_code` ile AÇIK kalır.
5. **Holehe koşmadıysa "koşmuş gibi görünmez"** — e-posta yoksa
   `email_scan.reason="no_target_email"` (`not_run`); kanal durumu çevirisi
   `ok / not_run / failed` gerçek durumu yansıtır.
6. **Sensör birleştirmesi güveni EZMEZ** — maigret/holehe kapsamı, sağlayıcı
   gözleminin üzerine en fazla yazılır (monoton; holehe kuralıyla aynı).

Ayrıca doküman sözleşmesi korunur: reddedilen tarama mühürlü kanıtta kalır
(`tests/unit/test_p4_documentation.py` bu dosyanın kaynak metnini de denetler).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agent_core.agents.osint_investigator import OsintInvestigatorAgent
from agent_core.domain.channel_status import (
    CHANNEL_FAILED,
    CHANNEL_NOT_RUN,
    CHANNEL_OK,
    from_engine_result,
)
from agent_core.domain.content_basis import (
    CONTENT_BASIS_NONE,
    CONTENT_BASIS_SEARCH,
)
from agent_core.services.holehe_scanner import HoleheScanResult
from agent_core.services.llm_gateway import LLMGateway
from agent_core.services.maigret_scanner import MaigretSiteHit, MaigretScanResult
from backend.services.web_dossier import (
    build_dossier_failure_profile,
    build_dossier_profile,
)


# --- HERMETIC TEST GUARD: canlı LLM/arama çağrısını kapatır ---
@pytest.fixture(autouse=True)
def _hermetic_guard(monkeypatch):
    async def _blocked(self, *a, **k):
        raise RuntimeError("REAL_LLM_CALL_NOT_EXECUTED: unit test kipi")

    monkeypatch.setattr(LLMGateway, "query", _blocked)
    monkeypatch.setattr(LLMGateway, "query_json", _blocked)
    # Kapılar bilinçli olarak KAPALI başlar: test yalnız kendi açtığı kapıyla
    # koşar; ortam sızıntısı varsayılanı değiştiremez.
    monkeypatch.delenv("OSINT_INDUSTRIES_KEY", raising=False)
    monkeypatch.delenv("ENABLE_MAIGRET", raising=False)
    monkeypatch.delenv("ENABLE_HOLEHE", raising=False)


def _provider_response(status: int, payload: dict | None = None, text: str = ""):
    mock_resp = AsyncMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=payload or {})
    mock_resp.text = AsyncMock(return_value=text)
    return mock_resp


# ================================================================ 1. SNIPPET ≠ GÖNDERİ
class TestSearchSnippetContract:
    def test_build_dossier_never_writes_snippets_into_posts(self):
        """[PR #136 · patch 1/4] Snippet `posts`'a girmez; `search_snippets`'a yazılır."""
        snippets = [
            {
                "text": "Hedef, gece yarısı ormanda yürüyüşlerini paylaşıyor.",
                "provider": "tavily",
                "source_url": "https://example.com/hedef",
            }
        ]
        profile = build_dossier_profile(
            display_user="@hedef",
            clean_u="hedef",
            snippets=snippets,
            found_profiles=["https://www.instagram.com/hedef/"],
        )
        assert profile["posts"] == []
        assert profile["post_types"] == []
        assert profile["post_times"] == []
        assert profile["search_snippets"] == snippets
        assert profile["content_basis"] == CONTENT_BASIS_SEARCH
        # Bulunan URL "bağlanan profil" DEĞİL, yalnızca tespit edilmiş adrestir.
        assert profile["detected_urls"] == ["https://www.instagram.com/hedef/"]

    def test_build_dossier_failure_profile_is_honest_empty(self):
        profile = build_dossier_failure_profile(clean_u="hedef", error_type="Timeout")
        assert profile["posts"] == []
        assert profile["search_snippets"] == []
        assert profile["content_basis"] == CONTENT_BASIS_NONE


# ================================================================ 2-4. SAĞLAYICI → SENSÖR
class TestProviderSensorContinuation:
    @pytest.mark.asyncio
    async def test_provider_success_still_runs_independent_sensors(self, monkeypatch):
        """[PR #136 · patch 3/4] 200 yanıtı Maigret/Holehe'yi sessizce geçersiz kılamaz."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        agent = OsintInvestigatorAgent()

        spy_username = AsyncMock(side_effect=lambda p, *a, **k: p)
        spy_email = AsyncMock(side_effect=lambda p, e, *a, **k: p.model_copy(update={"email_scan": {"requested_email": e}}))
        monkeypatch.setattr(agent, "_apply_username_scan", spy_username)
        monkeypatch.setattr(agent, "_apply_email_scan", spy_email)

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = _provider_response(
                200,
                {"emails": ["seen@example.com"], "phones": [], "platforms": ["X"]},
            )
            res = await agent.execute({"target_profile": {"username": "@cyber_agent"}})

        spy_username.assert_awaited_once()
        spy_email.assert_awaited_once()
        # Holehe gerçek girdiyle koşar: sağlayıcının gördüğü e-posta.
        assert spy_email.await_args.args[1] == "seen@example.com"
        assert res.connected_emails == ["seen@example.com"]
        assert res.email_scan["requested_email"] == "seen@example.com"

    @pytest.mark.asyncio
    async def test_provider_success_seals_sensor_provenance_even_when_gates_closed(self, monkeypatch):
        """Kapalı kapılar bile `not_run` provenance'ı yazar: sensör KOŞMADI, kayboldu değil."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        agent = OsintInvestigatorAgent()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = _provider_response(
                200, {"emails": ["seen@example.com"], "phones": [], "platforms": ["X"]}
            )
            res = await agent.execute({"target_profile": {"username": "@cyber_agent"}})

        assert res.username_scan is not None, "maigret provenance'sı yok — sensör sessizce atlandı"
        assert res.email_scan is not None, "holehe provenance'sı yok — sensör sessizce atlandı"
        # Kapılar kapalı → tarama çalışmadı; kanal durumu `not_run` + sebep.
        row = from_engine_result("sensor.identity.maigret", res.username_scan)
        assert row.status == CHANNEL_NOT_RUN
        assert row.reason

    @pytest.mark.asyncio
    async def test_provider_empty_observations_are_not_data_confidence(self, monkeypatch):
        """[PR #136] 200 + boş gözlem → veri güveni YOK; sebep makine-okunur."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        agent = OsintInvestigatorAgent()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = _provider_response(
                200, {"emails": [], "phones": [], "platforms": []}
            )
            res = await agent.execute({"target_profile": {"username": "@ghost_user"}})

        assert res.confidence == 0.0
        assert res.data_confidence is False
        assert res.fallback_reason == "provider_returned_no_observations"
        # Boş yanıt bile sensörleri durdurmaz.
        assert res.username_scan is not None

    @pytest.mark.asyncio
    async def test_provider_http_error_does_not_skip_sensors(self, monkeypatch):
        """[KALAN GÖREV] HTTP hata yolu erken return ile sensörleri atlamaz; hata AÇIK kalır."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        agent = OsintInvestigatorAgent()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = _provider_response(
                429, text="rate limited"
            )
            res = await agent.execute({
                "target_profile": {
                    "username": "@rate_limited",
                    "bio": "İletişim: bio.user@example.com",
                },
            })

        # Sağlayıcı hatası açık sonuç statüsüyle korunur.
        assert res.fallback_reason == "api_error"
        assert res.error_code == "RATE_LIMITED"
        # Bağımsız sensörler yine koştu ve provenance yazıldı.
        assert res.username_scan is not None
        assert res.email_scan is not None
        # Sağlayıcı veri dönmediğinde çıkarılan gerçek e-posta girdisi kaybolmaz.
        assert res.connected_emails == ["bio.user@example.com"]
        assert res.email_scan["requested_email"] == "bio.user@example.com"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("side_effect,error_code", [
        (asyncio.TimeoutError("slow"), "TIMEOUT"),
        (OSError("network down"), "NETWORK_ERROR"),
    ])
    async def test_provider_timeout_and_network_errors_also_continue(self, monkeypatch, side_effect, error_code):
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        agent = OsintInvestigatorAgent()

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.side_effect = side_effect
            res = await agent.execute({"target_profile": {"username": "@offline_target"}})

        assert res.fallback_reason == "api_error"
        assert res.error_code == error_code
        assert res.username_scan is not None
        assert res.email_scan is not None
        assert res.email_scan["reason"] == "no_target_email", "e-posta yokken Holehe koşmuş gibi gösterilemez"

    @pytest.mark.asyncio
    async def test_holehe_not_invoked_without_real_email(self, monkeypatch):
        """[KALAN GÖREV] E-posta yoksa Holehe ÇALIŞMAZ; `no_target_email` ile `not_run`."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        agent = OsintInvestigatorAgent()

        holehe_spy = AsyncMock(side_effect=AssertionError("Holehe e-postasız koştu"))
        monkeypatch.setattr(agent, "_apply_email_scan", holehe_spy)

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value = _provider_response(
                200, {"emails": [], "phones": ["+15550001"], "platforms": ["X"]}
            )
            res = await agent.execute({"target_profile": {"username": "@no_email_user"}})

        holehe_spy.assert_not_awaited()
        assert res.email_scan["available"] is False
        assert res.email_scan["reason"] == "no_target_email"
        # Kanal durumu çevirisi "bulunamadı" değil "koşmadı" der.
        row = from_engine_result("sensor.identity.holehe", res.email_scan)
        assert row.status == CHANNEL_NOT_RUN
        assert row.reason == "no_target_email"


# ================================================================ 5. KANAL DURUMU DÜRÜSTLÜĞÜ
class TestSensorChannelStatus:
    def test_sealed_scans_translate_to_real_channel_statuses(self):
        """`username_scan`/`email_scan` → `ok / not_run / failed` gerçek durumu yansıtır."""
        done = MaigretScanResult(
            requested_username="u", available=True,
            found_sites=[MaigretSiteHit(site="GitHub", url="https://github.com/u")],
            scanned_count=10, error_count=0,
        ).model_dump()
        assert from_engine_result("sensor.identity.maigret", done).status == CHANNEL_OK

        started_then_failed = HoleheScanResult(
            requested_email="a@b.co", available=False,
            reason="provider_errors", scanned_count=8, error_count=8,
        ).model_dump()
        row = from_engine_result("sensor.identity.holehe", started_then_failed)
        assert row.status == CHANNEL_FAILED
        assert row.reason == "provider_errors"

        never_ran = OsintInvestigatorAgent._no_target_email_seal()
        row = from_engine_result("sensor.identity.holehe", never_ran)
        assert row.status == CHANNEL_NOT_RUN
        assert row.reason == "no_target_email"


# ================================================================ 6. GÜVEN EZİLMEZ (MONOTON)
class TestConfidenceMonotoneMerge:
    def _maigret_hit(self, scanned: int, found: int):
        hits = [
            MaigretSiteHit(site=f"Site{i}", url=f"https://site{i}.example/u")
            for i in range(found)
        ]
        return MaigretScanResult(
            requested_username="u", available=True,
            found_sites=hits, scanned_count=scanned, error_count=0,
        )

    @pytest.mark.asyncio
    async def test_username_scan_coverage_does_not_drown_provider_confidence(self, monkeypatch):
        """Sağlayıcı 3/3 gözlem (1.0) + maigret 1/10 kapsama → güven 1.0 kalır (0.1'e çökmez)."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        monkeypatch.setenv("ENABLE_HOLEHE", "false")
        agent = OsintInvestigatorAgent()

        scan = self._maigret_hit(scanned=10, found=1)
        with patch("aiohttp.ClientSession.get") as mock_get, \
             patch("agent_core.services.maigret_scanner.scan_username", AsyncMock(return_value=scan)):
            mock_get.return_value.__aenter__.return_value = _provider_response(
                200,
                {"emails": ["a@b.co"], "phones": ["+15550001"], "platforms": ["X"]},
            )
            res = await agent.execute({
                "target_profile": {"username": "@full_profile"},
                "policy": {"vault_locked": False},
            })

        assert res.confidence == 1.0, "maigret kapsamı sağlayıcı gözlemini ezdi"
        assert res.data_confidence is True
        # Platformlar birleşir; kaynak silinmez.
        assert "X" in res.associated_platforms
        assert "Site0" in res.associated_platforms
        assert res.username_scan["found_sites"][0]["site"] == "Site0"

    @pytest.mark.asyncio
    async def test_clean_username_absence_does_not_erase_provider_observations(self, monkeypatch):
        """Maigret güvenilir yokluğu, başka kaynak gözlemini sıfırlamaz."""
        monkeypatch.setenv("OSINT_INDUSTRIES_KEY", "sk-osint-valid-test-key")
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        monkeypatch.setenv("ENABLE_HOLEHE", "false")
        agent = OsintInvestigatorAgent()

        scan = self._maigret_hit(scanned=8, found=0)
        with patch("aiohttp.ClientSession.get") as mock_get, \
             patch("agent_core.services.maigret_scanner.scan_username", AsyncMock(return_value=scan)):
            mock_get.return_value.__aenter__.return_value = _provider_response(
                200,
                {"emails": ["a@b.co"], "phones": ["+15550001"], "platforms": ["X"]},
            )
            res = await agent.execute({
                "target_profile": {"username": "@full_profile"},
                "policy": {"vault_locked": False},
            })

        assert res.confidence == 1.0, "sağlayıcı gözlemi maigret yokluğunda ezildi"
        assert res.data_confidence is True
        assert "X" in res.associated_platforms
        # Yokluk kanıtı provenance'da durur.
        assert res.username_scan["found_sites"] == []
