"""FAZ D · D6 — kurum hedefi servisi: dürüst ölçüm, uydurma metrik yok.

Kilitlenen iddialar:
    * Alan adı normalizasyonu tahmin etmez; geçersizse ``""``.
    * Özel/yerel adresler varsayılan REDDEDİLİR (SSRF hijyeni); operatör
      ``PINEAL_COMPANY_ALLOW_PRIVATE=1`` derse geçer.
    * theHarvester yoksa ``dependency_missing``; çıktı yoksa/bozuksa yokluk
      İDDİA EDİLMEZ (``output_missing`` / ``parse_error``).
    * robots/sitemap/meta/security.txt ÖLÇÜLÜR; "yok" yalnız kesin 404'te.
    * Ağ hatası yokluğa çevrilmez (``unreachable``).
    * Kişi verisi yalnız yapılandırılmış kaynaktan (schema.org/Person) gelir.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_core.services import company_recon

HOME = """<html lang="tr"><head>
<title>Örnek AŞ</title>
<meta name="description" content="Kurumsal çözümler">
<meta property="og:title" content="Örnek AŞ">
<link rel="canonical" href="https://ornek.com/">
<script type="application/ld+json">
{"@type":"Organization","name":"Örnek AŞ","employee":[
  {"@type":"Person","name":"Ayşe Yılmaz","jobTitle":"Genel Müdür"},
  {"@type":"Person","name":"Mehmet Demir","jobTitle":"CTO"}]}
</script></head><body>
<a href="mailto:info@ornek.com">İletişim</a></body></html>"""

ROBOTS = "User-agent: *\nDisallow: /admin\nCrawl-delay: 5\nSitemap: {base}/sitemap.xml\n"
SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>{base}/</loc><lastmod>2026-09-01</lastmod></url>
<url><loc>{base}/team</loc></url>
<url><loc>{base}/blog</loc></url>
</urlset>"""
SECURITY = "Contact: mailto:security@ornek.com\nExpires: 2027-01-01\n"


class _StubSite:
    """Kurum sitesi taklidi: ana sayfa · robots · sitemap · security.txt.

    ``missing`` kümesindeki yollar bilinçli 404 döner (yokluk iddiası için).
    """

    def __init__(self, *, missing: set[str] | None = None):
        self.missing = missing or set()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                base = f"http://127.0.0.1:{outer.server.server_port}"
                path = self.path.split("?", 1)[0]
                if path in outer.missing:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = {
                    "/": HOME,
                    "/robots.txt": ROBOTS.format(base=base),
                    "/sitemap.xml": SITEMAP.format(base=base),
                    "/.well-known/security.txt": SECURITY,
                    "/team": HOME,
                }.get(path)
                if body is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Server", "stub/1.0")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "PINEAL_HARVESTER_CMD",
        "PINEAL_HARVESTER_SOURCES",
        "PINEAL_COMPANY_ALLOW_PRIVATE",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture()
def site():
    stub = _StubSite()
    yield stub
    stub.close()


@pytest.fixture()
def open_site(monkeypatch):
    """Özel adres kilidi açık kurulum (test uçları 127.0.0.1'de)."""
    monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
    stub = _StubSite()
    yield stub
    stub.close()


class TestDomainNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("https://www.Ornek.com/yol?x=1", "ornek.com"),
            ("ornek.com:8443", "ornek.com"),
            ("  ORNEK.COM.  ", "ornek.com"),
            ("info@ornek.com", "ornek.com"),
            ("", ""),
            ("iki kelime", ""),
            ("localhost", ""),  # tek etiket: kurum alan adı değil
        ],
    )
    def test_normalize(self, raw, expected):
        assert company_recon.normalize_domain(raw) == expected


class TestPrivateTargetHygiene:
    @pytest.mark.asyncio
    async def test_loopback_rejected_by_default(self):
        scan = await company_recon.scan_company("127.0.0.1")
        assert scan.available is False
        assert scan.reason == "private_address_rejected"

    def test_seo_rejects_loopback_by_default(self):
        snapshot = asyncio_run(company_recon.seo_snapshot("127.0.0.1"))
        assert snapshot.available is False
        assert snapshot.reason == "private_address_rejected"


class TestHarvester:
    def _fake_cli(self, tmp_path, payload):
        script = tmp_path / "harvester"
        if payload is None:
            script.write_text("#!/bin/sh\nexit 0\n")
        else:
            quoted = json.dumps(payload)
            script.write_text(
                "#!/bin/sh\n"
                "# $1=-d $2=domain $3=-b $4=sources $5=-l $6=limit $7=-f $8=prefix\n"
                f"printf '%s' '{quoted}' > \"$8.json\"\n"
            )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    @pytest.mark.asyncio
    async def test_json_output_parsed(self, monkeypatch, tmp_path):
        payload = {
            "emails": ["info@ornek.com"],
            "hosts": ["vpn.ornek.com"],
            "ips": ["203.0.113.9"],
            "urls": ["https://ornek.com/kariyer"],
            "linkedin_people": ["Ayşe Yılmaz - CEO"],
            "unrecognized_key": ["görmezden gelinir"],
        }
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", str(self._fake_cli(tmp_path, payload)))
        scan = await company_recon.scan_company("ornek.com")
        assert scan.available is True
        assert scan.emails == ("info@ornek.com",)
        assert scan.hosts == ("vpn.ornek.com",)
        assert scan.people == ("Ayşe Yılmaz - CEO",)
        assert "unrecognized_key" in scan.keys_seen

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    @pytest.mark.asyncio
    async def test_missing_output_is_not_absence(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", str(self._fake_cli(tmp_path, None)))
        scan = await company_recon.scan_company("ornek.com")
        assert scan.available is False
        assert scan.reason == "output_missing"

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    @pytest.mark.asyncio
    async def test_broken_output_is_parse_error(self, monkeypatch, tmp_path):
        script = tmp_path / "harvester"
        script.write_text("#!/bin/sh\nprintf '%s' 'bu json degil' > \"$8.json\"\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", str(script))
        scan = await company_recon.scan_company("ornek.com")
        assert scan.available is False
        assert scan.reason == "parse_error"

    @pytest.mark.asyncio
    async def test_bogus_configured_command_is_honest(self, monkeypatch):
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        monkeypatch.setenv("PINEAL_HARVESTER_CMD", "pineal-olmayan-harvester")
        scan = await company_recon.scan_company("ornek.com")
        assert scan.available is False
        assert scan.reason == "configured_command_not_found:PINEAL_HARVESTER_CMD"

    @pytest.mark.asyncio
    async def test_missing_tool_is_honest(self, monkeypatch):
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        monkeypatch.delenv("PINEAL_HARVESTER_CMD", raising=False)
        monkeypatch.setattr(company_recon.shutil, "which", lambda name: None)
        ok, reason = company_recon.harvester_availability()
        assert ok is False
        assert reason == "dependency_missing:theHarvester"


class TestSeoSnapshot:
    @pytest.mark.asyncio
    async def test_measures_published_files(self, open_site):
        snapshot = await company_recon.seo_snapshot("ornek.com", base_url=open_site.url)
        assert snapshot.available is True
        checks = {check.name: check for check in snapshot.checks}
        assert checks["homepage"].present is True
        assert checks["homepage"].detail["title"] == "Örnek AŞ"
        assert checks["homepage"].detail["lang"] == "tr"
        assert checks["robots"].detail["disallow_all"] is False
        assert checks["robots"].detail["sitemaps"] == [f"{open_site.url}/sitemap.xml"]
        assert checks["sitemap"].detail["entries"] == 3
        assert checks["sitemap"].detail["first_lastmod"] == "2026-09-01"
        assert checks["security_txt"].detail["contacts"] == ["mailto:security@ornek.com"]

    @pytest.mark.asyncio
    async def test_404_is_absence_but_error_is_not(self, monkeypatch):
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        stub = _StubSite(missing={"/robots.txt"})
        try:
            snapshot = await company_recon.seo_snapshot("ornek.com", base_url=stub.url)
            robots = next(c for c in snapshot.checks if c.name == "robots")
            assert robots.status == 404 and robots.absent is True
        finally:
            stub.close()

    @pytest.mark.asyncio
    async def test_unreachable_is_not_absence(self, monkeypatch):
        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        snapshot = await company_recon.seo_snapshot("ornek.com", base_url="http://127.0.0.1:1")
        assert snapshot.available is False
        assert snapshot.reason == "unreachable"
        assert all(check.absent is False for check in snapshot.checks)


class TestPeopleScan:
    @pytest.mark.asyncio
    async def test_structured_people_only(self, open_site):
        scan = await company_recon.people_scan("ornek.com", base_url=open_site.url)
        assert scan.available is True
        names = {row.name for row in scan.people}
        assert {"Ayşe Yılmaz", "Mehmet Demir"} <= names
        assert any("info@ornek.com" in c for c in scan.contacts)
        assert all(row.page.startswith(open_site.url) for row in scan.people)

    @pytest.mark.asyncio
    async def test_no_signals_is_not_a_claim(self, monkeypatch):
        class _Bare(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = b"<html><body>Merhaba</body></html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        monkeypatch.setenv("PINEAL_COMPANY_ALLOW_PRIVATE", "1")
        server = HTTPServer(("127.0.0.1", 0), _Bare)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            scan = await company_recon.people_scan(
                "ornek.com", base_url=f"http://127.0.0.1:{server.server_port}", max_pages=1
            )
        finally:
            server.shutdown()
            server.server_close()
        assert scan.available is True
        assert scan.people == ()
        assert scan.contacts == ()


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
