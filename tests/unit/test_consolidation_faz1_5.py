"""FAZ 1-5 sağlamlaştırma sözleşmeleri.

Bu dosya tüm deneysel yüzeyi tek yerde kilitler:
- Default (kapıların hepsi kapalı) uç sözleşmeleri — pipeline değişmez garantisi.
- Sağlamlaştırma düzeltmelerinin regresyonları:
  * holehe tek-httpx-client (yarış kaynaklı client sızıntısı yok),
  * maigret DB yükleyicisi eşzamanlılıkta tam bir kez yüklenir (kilitli singleton).
- Beyan→kurulu zinciri: requirements'taki OSINT kütüphaneleri import edilebilir.
"""
import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from agent_core.services import maigret_scanner
from agent_core.services.holehe_scanner import scan_email
from agent_core.services.maigret_scanner import scan_username


class TestDefaultPostureSurface:
    """Kapılar default kapalı: tüm deneysel uçlar dürüst `disabled` der."""

    def test_all_experimental_endpoints_disabled_by_default(self, monkeypatch):
        for gate in ("ENABLE_MAIGRET", "ENABLE_HOLEHE", "ENABLE_CRAWL4AI"):
            monkeypatch.delenv(gate, raising=False)
        from backend.api import app

        with TestClient(app) as client:
            maigret = client.post("/api/experimental/maigret/scan",
                                  json={"username": "soxoj"}).json()
            holehe = client.post("/api/experimental/holehe/scan",
                                 json={"email": "a@b.com"}).json()
            crawl = client.post("/api/experimental/crawl/fetch",
                                json={"url": "https://example.com/a"}).json()
            stealth = client.get("/api/experimental/stealth").json()

        assert maigret["available"] is False and maigret["reason"] == "disabled"
        assert holehe["available"] is False and holehe["reason"] == "disabled"
        assert crawl["available"] is False and crawl["reason"] == "disabled"
        # stealth kapı DEĞİL seçicidir: default sağlayıcı bildirilir
        assert stealth["provider"] == "playwright_stealth"
        assert {"maigret", "holehe", "crawl4ai"} == {
            maigret["provider"], holehe["provider"], crawl["provider"]}


class TestHoleheSingleClient:
    @pytest.mark.asyncio
    async def test_concurrent_modules_share_one_client(self, monkeypatch):
        """[SAĞLAMLAŞTIRMA] Eşzamanlı modüller yarışla ikinci httpx client
        yaratamaz (eski kod concurrency>=2'de client sızdırıyordu)."""
        import httpx

        monkeypatch.setenv("ENABLE_HOLEHE", "true")
        created = {"n": 0}

        class CountingClient(httpx.AsyncClient):
            def __init__(self, *a, **kw):
                created["n"] += 1
                super().__init__(*a, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", CountingClient)

        mods = []
        for i in range(4):
            def _make(idx):
                async def _fn(email, client, out):
                    await asyncio.sleep(0.01)  # eşzamanlılığı zorla
                    out.append({"name": f"mod{idx}", "domain": f"{idx}.com",
                                "exists": False, "rateLimit": False,
                                "emailrecovery": None, "phoneNumber": None,
                                "others": None})
                _fn.__name__ = f"mod{idx}"
                return _fn
            mods.append(_make(i))
        import holehe.core as core

        async def _honest_launch(module, email, client, out):
            await module(email, client, out)

        monkeypatch.setattr(core, "launch_module", _honest_launch)
        res = await scan_email("a@b.com", modules=mods, site_timeout=5)
        assert created["n"] == 1  # TEK istemci — sızıntı yok
        assert res.scanned_count == 4
        assert res.available is True  # hepsi temiz yokluk döndü
        assert res.error_count == 0


class TestMaigretSingletonLock:
    @pytest.mark.asyncio
    async def test_site_dict_loaded_exactly_once_concurrent(self, monkeypatch):
        """[SAĞLAMLAŞTIRMA] Eşzamanlı taramalarda 3302 sitelik DB tam bir
        kez yüklenir (kilitli singleton; eski kodda yarış iki tam yük üretebilir)."""
        monkeypatch.setenv("ENABLE_MAIGRET", "true")
        # [RÖNTGEN 2026-09-23] SIRALAMA SIZINTISI KAPATILDI: `_db_singleton`
        # modül globali. Başka bir test (maigret kuruluysa test_maigret_scanner
        # gerçek 3302 sitelik DB'yi yüklüyor) singleton'u doldurmuşsa bu
        # testte yükleyici HİÇ çağrılmıyor ve kilit testi "assert 0 == 1" ile
        # kırmızıya düşüyordu — yani ölçülen şey KİLİT değil TEST SIRASIydı.
        # monkeypatch ile sıfırla: kilit gerçekten ölçülür ve global test
        # sonunda eski değerine döner (yeni sızıntı üretmez).
        monkeypatch.setattr(maigret_scanner, "_db_singleton", None)
        calls = {"n": 0}
        load_lock = threading.Lock()

        class _FakeDB:
            def ranked_sites_dict(self, top):
                return {f"S{i}": object() for i in range(min(top, 5))}

        def _slow_loader(top):
            with load_lock:
                calls["n"] += 1
            time.sleep(0.05)  # ikinci çağrıyı singleton'a beklet
            return _FakeDB()

        monkeypatch.setattr(maigret_scanner, "_load_site_dict", _slow_loader)

        from maigret.result import MaigretCheckStatus

        class _R:
            status = MaigretCheckStatus.AVAILABLE
            url_user = ""

        async def _fake_scan(username, site_dict, timeout):
            return {k: _R() for k in site_dict}

        monkeypatch.setattr(maigret_scanner, "_run_library_scan", _fake_scan)
        results = await asyncio.gather(*(scan_username("soxoj", limit=5) for _ in range(3)))
        assert calls["n"] == 1  # tek yükleme
        assert all(r.scanned_count == 5 for r in results)


class TestDeclaredLibrariesInstalled:
    """Beyan→kurulu zinciri: requirements'taki OSINT bağımlılıkları bu ortamda
    import edilebilir olmalı (config exists vs deployed ayrımı kapanır)."""

    @pytest.mark.parametrize("module", [
        "socid_extractor", "maigret", "holehe",
        "playwright_stealth", "invisible_playwright",
    ])
    def test_import(self, module):
        import importlib

        importlib.import_module(module)

    def test_crawl4ai_second_step_optional_in_ci(self):
        """crawl4ai requirements-osint.txt'tedir (psutil meta-çatışması nedeniyle
        iki-adımlı kurulum). CI backend job'ı yalnız birinci adımı kurar —
        yoksa dürüstçe SKIP; varsa (tam kurulumda) import kanıtlanır."""
        crawl4ai = pytest.importorskip(
            "crawl4ai",
            reason="crawl4ai ikinci-adım dosyasındadır (pip install -r requirements-osint.txt); CI yalnız birinci adımı kurar",
        )
        assert crawl4ai is not None
