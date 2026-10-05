"""FAZ D · D4 — çeviri: ses/dinlemeyle AYNI yerellik kuralı.

Kilitlenen iddialar:
    * UZAK uç reddedilir (`non_local_endpoint`); metin makineden çıkmaz.
    * Motor yoksa çeviri ÜRETİLMEZ (`no_engine`); kaynak metin çeviri diye dönmez.
    * Yerel uç (yalnız 127.0.0.1) ve yerel CLI çalışır; kaynak dil tespiti
      çeviriye eşlik eder (hangi dilden çevrildiği gizlenmez).
    * Motor girdiyi aynen geri verirse bu çeviri İDDİA EDİLMEZ.
"""

from __future__ import annotations

import json
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_core.services import translation

TR_TEXT = (
    "Merhaba, bugün hava çok güzel ve ben dışarı çıkmak istiyorum. "
    "Ama önce işlerimi bitirmem gerekiyor çünkü yarın için hazırlık yapmalıyım."
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.delenv("PINEAL_TRANSLATE_URL", raising=False)
    monkeypatch.delenv("PINEAL_TRANSLATE_CMD", raising=False)
    # PATH'te `trans` varsa testin dışına çıkmasın: bulunmayan komuta sabitle.
    monkeypatch.setenv("PINEAL_TRANSLATE_CMD", "pineal-olmayan-ceviri-komutu")


class TestEngineResolution:
    def test_no_engine_is_honest(self, monkeypatch):
        monkeypatch.delenv("PINEAL_TRANSLATE_URL", raising=False)
        engine, reason = translation.resolve_engine()
        assert engine == ""
        assert reason == "no_engine"

    def test_remote_endpoint_rejected(self, monkeypatch):
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "https://cevirici.example.com/translate")
        engine, reason = translation.resolve_engine()
        assert engine == ""
        assert reason == "non_local_endpoint"

    def test_remote_rejection_does_not_fall_back_to_cli(self, monkeypatch, tmp_path):
        """Uç TANIMLI ama uzaksa CLI'ye sessizce düşülmez: ret kararı açık kalır."""
        fake = tmp_path / "trans"
        fake.write_text("#!/bin/sh\ncat\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "https://uzak.example.com/t")
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", str(fake))
        engine, reason = translation.resolve_engine()
        assert engine == ""
        assert reason == "non_local_endpoint"

    def test_bad_scheme_rejected(self, monkeypatch):
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "ftp://127.0.0.1/x")
        _engine, reason = translation.resolve_engine()
        assert reason == "bad_endpoint_scheme"

    def test_local_endpoint_accepted(self, monkeypatch):
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:9/translate")
        engine, reason = translation.resolve_engine()
        assert engine == "local_endpoint"
        assert reason == ""

    def test_cli_accepted_when_on_path(self, monkeypatch, tmp_path):
        fake = tmp_path / "ceviri"
        fake.write_text("#!/bin/sh\ncat\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", str(fake))
        engine, reason = translation.resolve_engine()
        assert engine == "cli"
        assert reason == ""


class TestNoEngineHonesty:
    @pytest.mark.asyncio
    async def test_no_engine_no_translation(self):
        result = await translation.translate_text(TR_TEXT, "en")
        assert result.available is False
        assert result.reason == "no_engine"
        assert result.text == ""
        # Tespit yine de dürüstçe eşlik eder:
        assert result.source_language == "tr"
        assert result.source_confidence >= 0.5

    @pytest.mark.asyncio
    async def test_empty_text_and_target(self):
        assert (await translation.translate_text("", "en")).reason == "empty_text"
        assert (await translation.translate_text(TR_TEXT, "")).reason == "empty_target"


class TestLocalEndpoint:
    @pytest.fixture()
    def local_server(self, monkeypatch):
        """Gerçek YEREL çeviri ucu: JSON döner, kaynağı görür."""
        seen: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server sözleşmesi
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                seen.update(body)
                out = json.dumps({"text": "Hello, the weather is nice today."}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setenv(
            "PINEAL_TRANSLATE_URL", f"http://127.0.0.1:{server.server_port}/translate"
        )
        yield seen
        server.shutdown()

    @pytest.mark.asyncio
    async def test_local_endpoint_translates_and_reports_source(self, local_server):
        result = await translation.translate_text(TR_TEXT, "en")
        assert result.available is True
        assert result.text == "Hello, the weather is nice today."
        assert result.engine == "local_endpoint"
        assert result.source_language == "tr"  # hangi dilden geldi gizlenmez
        assert result.target_language == "en"
        assert local_server.get("source") == "tr"  # motora da iletildi

    @pytest.mark.asyncio
    async def test_unknown_source_not_sent_to_engine(self, monkeypatch):
        """Tespit 'unknown' ise motora kaynak etiketi GÖNDERİLMEZ (uydurma yok)."""
        seen: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                seen.update(json.loads(self.rfile.read(length).decode("utf-8")))
                out = b'{"text": "cevirlendi"}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", f"http://127.0.0.1:{server.server_port}/")
        try:
            text = "Zzxx qplm vbntr kjsdhf aldfkj qwepoi zxcvmn rutyqp lskdjf"
            result = await translation.translate_text(text, "en")
            assert result.source_language == "unknown"
            assert "source" not in seen
            assert result.available is True
        finally:
            server.shutdown()


class TestLocalCli:
    @pytest.fixture()
    def cli_engine(self, monkeypatch, tmp_path):
        """Sahte yerel CLI: 'TR→EN:' öneki ekler (stdin→stdout sözleşmesi)."""
        fake = tmp_path / "sahte-ceviri"
        fake.write_text("#!/bin/sh\nread -r line\necho \"EN: $line\"\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", str(fake))
        return fake

    @pytest.mark.asyncio
    async def test_cli_translates(self, cli_engine):
        result = await translation.translate_text(TR_TEXT, "en")
        assert result.available is True
        assert result.engine == "cli"
        assert result.text.startswith("EN: ")

    @pytest.mark.asyncio
    async def test_cli_echo_is_not_claimed_as_translation(self, monkeypatch, tmp_path):
        """Motor metni değiştirmediyse çeviri İDDİA EDİLMEZ (engine_echoed_input)."""
        fake = tmp_path / "yanki"
        fake.write_text("#!/bin/sh\ncat\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", str(fake))
        result = await translation.translate_text(TR_TEXT, "en")
        assert result.available is False
        assert result.reason == "engine_echoed_input"

    @pytest.mark.asyncio
    async def test_cli_failure_is_classified(self, monkeypatch, tmp_path):
        fake = tmp_path / "basaarisiz"
        fake.write_text("#!/bin/sh\necho 'motor bozuk' 1>&2\nexit 3\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSLATE_CMD", str(fake))
        result = await translation.translate_text(TR_TEXT, "en")
        assert result.available is False
        assert result.reason.startswith("translation_failed:")


class TestStatus:
    def test_status_reports_gate_and_engine(self, monkeypatch):
        monkeypatch.setenv("PINEAL_TRANSLATE_URL", "http://127.0.0.1:1/t")
        status = translation.status()
        assert status["available"] is True
        assert status["engine"] == "local_endpoint"
        assert status["gate"] == "ENABLE_LOCAL_TRANSLATE"
