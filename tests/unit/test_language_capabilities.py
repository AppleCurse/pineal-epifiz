"""FAZ D · D4 — dil yetenekleri omurgada: tespit + yerel çeviri + kanıt damgası.

Kilitlenen iddialar:
    * Her iki yetenek omurgaya KAYITLIDIR ve ``vault`` kapısını taşır
      (Tüzük Md.4: kasa kilitliyken hiçbir yetenek koşamaz — tespit bile).
    * Tespit omurgadan koşar; sinyal yoksa kanıt UYDURULMAZ (items boş,
      sebep notes'ta makine-okunur).
    * Web çıkarıcıları (trafilatura/crawl4ai/scrapling) çıkardıkları metnin
      dilini kanıt kapsamına İŞLER ve kokpit pilinin kaydını günceller.
    * Çeviri kapısı: ENABLE_LOCAL_TRANSLATE kapalıyken motor çağrılmaz.
"""

from __future__ import annotations

import pytest

from agent_core.capabilities.base import CapabilityContext
from agent_core.capabilities.policy import PolicyState
from agent_core.capabilities.registry import CapabilityRegistry, bootstrap
from agent_core.capabilities.runner import run_capability
from agent_core.services import language

TR_TEXT = (
    "Merhaba, bugün hava çok güzel ve ben dışarı çıkmak istiyorum. "
    "Ama önce işlerimi bitirmem gerekiyor çünkü yarın için hazırlık yapmalıyım."
)

DE_TEXT = (
    "Hallo, das Wetter ist heute sehr schön und ich möchte nach draußen gehen. "
    "Aber zuerst muss ich meine Arbeit beenden, weil ich mich auf morgen vorbereiten sollte."
)


@pytest.fixture(autouse=True)
def _clean_state():
    language.reset_last_finding()
    yield
    language.reset_last_finding()


class TestRegistration:
    def test_both_capabilities_registered(self):
        reg = CapabilityRegistry()
        bootstrap(reg)
        assert reg.has("extractor.text.language")
        assert reg.has("extractor.text.translate_local")

    def test_both_carry_vault_gate(self):
        """Tüzük Md.4 istisnasızdır: tespit de çeviri de kasa mandalına bağlı."""
        reg = CapabilityRegistry()
        bootstrap(reg)
        for cap_id in ("extractor.text.language", "extractor.text.translate_local"):
            cap = reg.get(cap_id)
            assert "vault" in cap.gates, f"{cap_id}: kasa kapısı yok"

    @pytest.mark.asyncio
    async def test_vault_lock_blocks_both(self):
        reg = CapabilityRegistry()
        bootstrap(reg)
        for cap_id in ("extractor.text.language", "extractor.text.translate_local"):
            result = await run_capability(
                cap_id,
                CapabilityContext(subject=TR_TEXT),
                registry=reg,
                state=PolicyState(vault_locked=True),
            )
            assert result.denied_by == "vault", f"{cap_id} kasa kilidini atladı"
            assert result.items == ()


class TestLanguageDetectCapability:
    @pytest.mark.asyncio
    async def test_detection_produces_evidence(self):
        from agent_core.capabilities.adapters_language import LanguageDetectCapability

        result = await LanguageDetectCapability().run(CapabilityContext(subject=TR_TEXT))
        assert result.available is True
        assert len(result.items) == 1
        item = result.items[0]
        assert item.source_engine == "language_detect"
        assert item.scope["kind"] == "language"
        assert item.scope["language"] == "tr"
        assert item.scope["confidence"] >= 0.5

    @pytest.mark.asyncio
    async def test_no_signal_produces_no_evidence_but_honest_notes(self):
        from agent_core.capabilities.adapters_language import LanguageDetectCapability

        result = await LanguageDetectCapability().run(CapabilityContext(subject="qw zx as df"))
        assert result.available is True  # yetenek çalıştı ama...
        assert result.items == ()  # ...etiket YOK: kanıt uydurulmaz
        assert result.notes["language"] == "unknown"
        assert result.notes["reason"] == "too_short"

    @pytest.mark.asyncio
    async def test_empty_text_rejected(self):
        from agent_core.capabilities.adapters_language import LanguageDetectCapability

        result = await LanguageDetectCapability().run(CapabilityContext(subject=""))
        assert result.available is False
        assert result.unavailable_reason == "empty_text"


class TestTranslateCapabilityGates:
    @pytest.mark.asyncio
    async def test_gate_disabled_blocks_before_engine(self, monkeypatch):
        from agent_core.capabilities.adapters_language import LocalTranslateCapability
        from agent_core.services import translation

        monkeypatch.delenv("ENABLE_LOCAL_TRANSLATE", raising=False)

        def _boom():
            raise AssertionError("kapı kapalıyken motor ÇÖZÜLMEMELİ")

        monkeypatch.setattr(translation, "resolve_engine", _boom)
        cap = LocalTranslateCapability()
        availability = cap.availability()
        assert availability.available is False
        assert availability.reason == "gate_disabled:ENABLE_LOCAL_TRANSLATE"

    @pytest.mark.asyncio
    async def test_no_engine_is_honest_unavailable(self, monkeypatch):
        from agent_core.capabilities.adapters_language import LocalTranslateCapability

        monkeypatch.setenv("ENABLE_LOCAL_TRANSLATE", "true")
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", "pineal-olmayan-komut")
        monkeypatch.delenv("PINEAL_TRANSLATE_URL", raising=False)
        result = await LocalTranslateCapability().run(
            CapabilityContext(subject=TR_TEXT, params={"target": "en"})
        )
        assert result.available is False
        assert result.unavailable_reason == "no_engine"
        assert result.items == ()


class TestWebExtractorStamping:
    """Kanıt kapsamındaki dil alanı UYDURMA değil, ölçümün kendisidir."""

    @pytest.mark.asyncio
    async def test_trafilatura_stamps_language_into_evidence(self, monkeypatch):
        import sys
        import types

        from agent_core.capabilities import adapters_web
        from agent_core.capabilities.adapters_web import TrafilaturaCapability

        extracted = f"{TR_TEXT}\n\n{TR_TEXT}"
        fake_trafilatura = types.SimpleNamespace(
            fetch_url=lambda url: "<html>...</html>",
            extract=lambda *a, **k: extracted,
            extract_metadata=lambda downloaded: None,
        )
        monkeypatch.setitem(sys.modules, "trafilatura", fake_trafilatura)
        monkeypatch.setattr(adapters_web, "_module_available", lambda _n: True)
        monkeypatch.setattr(adapters_web, "is_safe_url", lambda _u: True)  # hedef: damga, guard değil

        result = await TrafilaturaCapability().run(
            CapabilityContext(subject="https://ornek.example/makale")
        )
        assert result.ok
        scope = result.items[0].scope
        assert scope["language"] == "tr"
        assert scope["language_confidence"] >= 0.5
        assert scope["kind"] == "web_text"
        assert result.notes["language"] == "tr"
        # Kokpit pilinin kaydı da güncellenir:
        last = language.last_finding()
        assert last is not None
        assert last["language"] == "tr"
        assert last["source_engine"] == "trafilatura"
        assert last["url"] == "https://ornek.example/makale"

    @pytest.mark.asyncio
    async def test_crawl4ai_stamps_language_into_evidence(self, monkeypatch):
        from agent_core.capabilities import adapters_web
        from agent_core.capabilities.adapters_web import Crawl4AICapability
        from agent_core.services import crawl_enricher

        class _Result:
            available = True
            reason = None
            markdown = DE_TEXT + "\n" + DE_TEXT
            url = "https://beispiel.example/artikel"
            title = "Beispiel"
            status_code = 200

        async def _fake_fetch(url):
            return _Result()

        monkeypatch.setattr(crawl_enricher, "fetch_readable", _fake_fetch)
        monkeypatch.setattr(crawl_enricher, "is_enabled", lambda: True)
        monkeypatch.setattr(adapters_web, "_module_available", lambda _n: True)
        monkeypatch.setattr(adapters_web, "is_safe_url", lambda _u: True)

        result = await Crawl4AICapability().run(
            CapabilityContext(subject="https://beispiel.example/artikel")
        )
        assert result.ok
        assert result.items[0].scope["language"] == "de"
        assert result.notes["language"] == "de"

    @pytest.mark.asyncio
    async def test_scrapling_stamps_language_into_evidence(self, monkeypatch):
        import sys
        import types

        from agent_core.capabilities import adapters_web
        from agent_core.capabilities.adapters_web import ScraplingCapability

        monkeypatch.setenv("ENABLE_SCRAPLING", "true")

        class _Page:
            text = DE_TEXT

        class _Fetcher:
            @staticmethod
            def get(url):
                return _Page()

        fake_fetchers = types.SimpleNamespace(Fetcher=_Fetcher)
        monkeypatch.setitem(
            sys.modules, "scrapling", types.SimpleNamespace(fetchers=fake_fetchers)
        )
        monkeypatch.setitem(sys.modules, "scrapling.fetchers", fake_fetchers)
        monkeypatch.setattr(adapters_web, "_module_available", lambda _n: True)
        monkeypatch.setattr(adapters_web, "is_safe_url", lambda _u: True)

        result = await ScraplingCapability().run(
            CapabilityContext(subject="https://beispiel.example/artikel")
        )
        assert result.ok
        assert result.items[0].scope["language"] == "de"

    def test_language_scope_never_breaks_extraction(self, monkeypatch):
        """Tespit patlasa bile kapsam dürüst kalır (unknown + sebep)."""
        from agent_core.capabilities import adapters_web

        def _boom(*args, **kwargs):
            raise RuntimeError("detect patladi")

        import agent_core.services.language as lang_mod

        monkeypatch.setattr(lang_mod, "detect_language", _boom)
        scope = adapters_web._language_scope("herhangi bir metin", "trafilatura", "https://x")
        assert scope["language"] == "unknown"
        assert scope["language_reason"] == "detect_error"
