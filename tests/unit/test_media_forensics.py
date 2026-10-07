"""FAZ D · D3 — medya adli hattı servisi: ölçüm, yerellik, dürüst araç yokluğu.

Kilitlenen iddialar:
    * İndirme özel/yerel adreslere yapılmaz (SSRF kapısı).
    * Platform linki (youtube…) yt-dlp yoksa UYDURMA indirme yapmaz.
    * Kare analizi ÖLÇER (fps/kare/parlaklık/sahne kesmesi); yorum yapmaz.
    * Transkript YALNIZ yerel motorla üretilir; uzak uç reddedilir ve CLI'ye
      sessizce düşülmez; boş çıktı transkript sayılmaz.
    * pHash + Hamming benzerliği deterministiktir; indeks diske yazılır.
"""

from __future__ import annotations

import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest
from PIL import Image

from agent_core.services import media_forensics as mf

PNG_BYTES = b""


def _make_image(path, color=(200, 30, 30), size=(160, 120)):
    image = Image.new("RGB", size, color)
    image.save(path)
    return path


def _make_pattern(path, *, seed=1, shift=0, kind="stripes", size=(160, 120)):
    """Yapılı görsel: pHash için doku gerekir (düz renk DCT'de boş çıkar)."""
    import random

    rng = random.Random(seed)
    image = Image.new("RGB", size, (18, 22, 34))
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            if kind == "stripes":
                value = 220 if (x // 8) % 2 == 0 else 40
            else:
                value = 220 if ((x - 80) ** 2 + (y - 60) ** 2) < 1600 else 40
            jitter = rng.randint(-12, 12) + shift
            pixels[x, y] = (
                max(0, min(255, value + jitter)),
                max(0, min(255, value // 2 + jitter)),
                max(0, min(255, 255 - value + jitter)),
            )
    image.save(path)
    return path


def _make_video(path, *, pixel_format="mp4v", fps=10.0, frames=30, switch_at=15):
    import cv2

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*pixel_format), fps, (320, 240))
    assert writer.isOpened(), "VideoWriter açılamadı (codec yok)"
    for index in range(frames):
        value = 0 if index < switch_at else 220
        frame = np.full((240, 320, 3), value, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in (
        "PINEAL_MEDIA_DIR",
        "PINEAL_MEDIA_ALLOW_PRIVATE",
        "PINEAL_TRANSCRIBE_URL",
        "PINEAL_TRANSCRIBE_CMD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PINEAL_MEDIA_DIR", str(tmp_path / "media"))
    yield


class _FileServer:
    """Küçük dosya sunucusu (indirme testleri için)."""

    def __init__(self, payload: bytes, *, content_type="image/png"):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.endswith(".png"):
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/dosya.png"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TestFetch:
    @pytest.mark.asyncio
    async def test_local_path_is_sealed(self, tmp_path):
        image = _make_image(tmp_path / "foto.png")
        fetched = await mf.fetch_media(str(image))
        assert fetched.available is True
        assert fetched.kind == "image"
        assert len(fetched.sha256) == 64 and fetched.bytes > 0

    @pytest.mark.asyncio
    async def test_missing_inputs_are_honest(self, tmp_path):
        assert (await mf.fetch_media("")).reason == "empty_source"
        assert (await mf.fetch_media(str(tmp_path / "yok.png"))).reason == "not_found"

    @pytest.mark.asyncio
    async def test_private_host_is_rejected(self):
        fetched = await mf.fetch_media("http://127.0.0.1:9/gizli.png")
        assert fetched.available is False
        assert fetched.reason == "private_address_rejected"

    @pytest.mark.asyncio
    async def test_platform_url_needs_ytdlp(self, monkeypatch):
        monkeypatch.setattr(mf.shutil, "which", lambda name: None)
        fetched = await mf.fetch_media("https://www.youtube.com/watch?v=abc")
        assert fetched.available is False
        assert fetched.reason == "dependency_missing:yt-dlp"

    @pytest.mark.asyncio
    async def test_direct_download(self, monkeypatch):
        monkeypatch.setenv("PINEAL_MEDIA_ALLOW_PRIVATE", "1")
        image = _make_image("/tmp/pineal-media-test.png", color=(10, 200, 10))
        payload = open(image, "rb").read()
        server = _FileServer(payload)
        try:
            fetched = await mf.fetch_media(server.url)
        finally:
            server.close()
        assert fetched.available is True
        assert fetched.bytes == len(payload)
        assert fetched.kind == "image"
        assert os.path.exists(fetched.path)

    @pytest.mark.asyncio
    async def test_unsupported_extension(self, monkeypatch):
        monkeypatch.setenv("PINEAL_MEDIA_ALLOW_PRIVATE", "1")
        fetched = await mf.fetch_media("http://127.0.0.1:9/arsiv.zip")
        assert fetched.available is False
        # Uzantı kapısı ağ denemesinden ÖNCE: istek atılmaz.

    @pytest.mark.asyncio
    async def test_too_large_is_refused(self, monkeypatch):
        monkeypatch.setenv("PINEAL_MEDIA_ALLOW_PRIVATE", "1")
        monkeypatch.setattr(mf, "MAX_DOWNLOAD_BYTES", 10)
        server = _FileServer(b"x" * 1024)
        try:
            fetched = await mf.fetch_media(server.url)
        finally:
            server.close()
        assert fetched.available is False
        assert fetched.reason == "too_large"


class TestFrames:
    def test_video_measurements_and_scene_cut(self, tmp_path):
        video = _make_video(tmp_path / "kayit.mp4")
        analysis = mf.analyze_frames(str(video), sample_every=3)
        assert analysis.available is True
        assert analysis.fps == pytest.approx(10.0, abs=0.5)
        assert analysis.frames >= 29
        assert analysis.width == 320 and analysis.height == 240
        assert analysis.brightness_mean == pytest.approx(110, abs=15)
        assert analysis.scenes, "siyah→beyaz geçişi sahne kesmesi olmalı"
        assert 1.0 <= analysis.scenes[0] <= 2.0

    def test_image_measurements(self, tmp_path):
        image = _make_image(tmp_path / "foto.png", color=(200, 30, 30))
        analysis = mf.analyze_frames(str(image))
        assert analysis.available is True
        assert analysis.kind == "image"
        assert analysis.dominant_color == pytest.approx((200, 30, 30), abs=6)

    def test_unsupported_kind_is_honest(self, tmp_path):
        audio = tmp_path / "ses.mp3"
        audio.write_bytes(b"\x00\x01")
        analysis = mf.analyze_frames(str(audio))
        assert analysis.available is False
        assert analysis.reason == "unsupported_kind:audio"

    def test_missing_file(self, tmp_path):
        assert mf.analyze_frames(str(tmp_path / "yok.mp4")).reason == "not_found"


class TestTranscript:
    def test_no_engine_is_honest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mf.shutil, "which", lambda name: None)
        media = tmp_path / "ses.wav"
        media.write_bytes(b"RIFF")
        import asyncio

        transcript = asyncio.run(mf.transcribe(str(media)))
        assert transcript.available is False
        assert transcript.reason == "no_engine"

    def test_remote_endpoint_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PINEAL_TRANSCRIBE_URL", "https://api.example.com/transcribe")
        engine, reason = mf.resolve_engine()
        assert engine == "" and reason == "non_local_endpoint"

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    def test_local_cli_transcript(self, tmp_path, monkeypatch):
        media = tmp_path / "ses.wav"
        media.write_bytes(b"RIFF")
        script = tmp_path / "whisper"
        script.write_text(
            "#!/bin/sh\n"
            'last=""; for arg in "$@"; do last="$arg"; done\n'
            'dir=$(dirname "$last"); stem=$(basename "$last"); stem="${stem%.*}"\n'
            "printf 'Merhaba dunya, bu bir transkript kaydidir.' > \"$dir/$stem.txt\"\n"
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSCRIBE_CMD", str(script))
        import asyncio

        transcript = asyncio.run(mf.transcribe(str(media)))
        assert transcript.available is True
        assert "transkript" in transcript.text
        assert transcript.language in {"tr", "unknown"}
        assert len(transcript.media_sha256) == 64

    @pytest.mark.skipif(os.name != "posix", reason="sahte CLI POSIX betiği (WinError 193)")
    def test_empty_engine_output_is_not_a_transcript(self, tmp_path, monkeypatch):
        media = tmp_path / "ses.wav"
        media.write_bytes(b"RIFF")
        script = tmp_path / "whisper"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PINEAL_TRANSCRIBE_CMD", str(script))
        import asyncio

        transcript = asyncio.run(mf.transcribe(str(media)))
        assert transcript.available is False
        assert transcript.reason == "empty_transcript"

    def test_video_without_ffmpeg_is_honest(self, tmp_path, monkeypatch):
        video = _make_video(tmp_path / "kayit.mp4", frames=4)
        script = tmp_path / "whisper"
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setattr(mf.shutil, "which", lambda name: None)
        monkeypatch.setenv("PINEAL_TRANSCRIBE_CMD", str(script))
        import asyncio

        transcript = asyncio.run(mf.transcribe(str(video)))
        # CLI bulunamaz (which None) → motor yok; ffmpeg ayrımı ayrı ölçülür.
        assert transcript.available is False
        assert transcript.reason in {"no_engine", "dependency_missing:ffmpeg"}


class TestSimilarity:
    def test_phash_similarity_and_index(self):
        # İndeks MEDYA DİZİNİNİ tarar (yerel medya kütüphanesi); sorgu da oradan.
        library = mf.media_dir()
        library.mkdir(parents=True, exist_ok=True)
        base = _make_pattern(library / "a.png", seed=1, shift=0, kind="stripes")
        near = _make_pattern(library / "b.png", seed=1, shift=6, kind="stripes")
        far = _make_pattern(library / "c.png", seed=2, shift=0, kind="circle")
        query_hash = mf.phash(str(base))
        assert len(query_hash) == 16
        result = mf.visual_similarity(str(near), top_k=5)
        assert result.available is True
        assert result.index_size >= 3
        distances = {row["file"]: row["distance"] for row in result.matches}
        assert distances["a.png"] < distances.get("c.png", 64)
        assert mf.index_path().exists()

    def test_missing_file(self, tmp_path):
        result = mf.visual_similarity(str(tmp_path / "yok.png"))
        assert result.available is False
        assert result.reason == "not_found"
