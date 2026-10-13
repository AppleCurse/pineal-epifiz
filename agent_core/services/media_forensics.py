"""FAZ D · D3 — MEDYA ADLİ HATTI: indir · kare kare ölç · yazıya dök · eşleştir.

Dört adım, dördü de ÖLÇÜM üretir (yorum değil):

    fetch_media       → paylaşılan video/foto indirilir (yt-dlp platformlar için,
                        doğrudan bağlantılar için httpx) ve sha256 ile mühürlenir.
    analyze_frames    → künye (fps/kare/süre/çözünürlük) + kare kare parlaklık,
                        baskın renk, sahne kesmeleri (histogram farkı) ve
                        fotoğrafta Laplacian keskinliği. OpenCV.
    transcribe        → ses yazıya dökülür: YALNIZ yerel motor (yerel uç ya da
                        yerel CLI). Uzak uç REDDEDİLİR — ses metni makineden
                        çıkmaz (çeviri/seslendirme ile aynı kural).
    visual_similarity → pHash (DCT) parmak izi + Hamming mesafesiyle yerel
                        benzerlik araması (indeks `memory/media/index.json`).

Dürüstlük sözleşmesi:
    * Araç yok → `available=False` + makine-okunur sebep (ffmpeg/yt-dlp/opencv).
    * Ölçülmeyen şey iddia edilmez: "kare kare analiz" kare sayısı raporlanır;
      içerik YORUMU (ne olduğu) bu katmanın işi DEĞİLDİR.
    * Motor boş çıktı verirse transkript İDDİA EDİLMEZ (`empty_transcript`).
    * İndirme özel/yerel adreslere yapılmaz (SSRF kapısı: net_hygiene).
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from httpx import Timeout

from agent_core.services import net_hygiene
from agent_core.utils.security import UnsafeURLError, build_secure_client, safe_get

__all__ = [
    "GATE",
    "PRIVATE_ALLOW_ENV",
    "PLATFORM_HOSTS",
    "MEDIA_EXTENSIONS",
    "MediaFetch",
    "FrameAnalysis",
    "Transcript",
    "SimilarityResult",
    "media_dir",
    "index_path",
    "platform_of",
    "fetch_media",
    "analyze_frames",
    "transcribe",
    "phash",
    "visual_similarity",
]

GATE = "ENABLE_MEDIA_FORENSICS"
PRIVATE_ALLOW_ENV = "PINEAL_MEDIA_ALLOW_PRIVATE"

#: yt-dlp olmadan indirilemeyen platformlar (doğrudan dosya URL'si DEĞİL).
PLATFORM_HOSTS = {
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "vimeo.com": "vimeo",
    "tiktok.com": "tiktok",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "twitter.com": "x",
    "x.com": "x",
}

MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic",
    ".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac",
}

MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
MAX_SCENES = 40
MAX_INDEX_FILES = 500


def media_dir() -> Path:
    """Medya dizini: ``PINEAL_MEDIA_DIR`` ya da ``memory/media``."""
    raw = os.getenv("PINEAL_MEDIA_DIR", "").strip()
    return Path(raw).expanduser() if raw else Path("memory") / "media"


def index_path() -> Path:
    return media_dir() / "index.json"


def _kind_of(path: Path, content_type: str = "") -> str:
    suffix = path.suffix.lower()
    if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
        return "video"
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".heic"}:
        return "image"
    if suffix in {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac"}:
        return "audio"
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    return "unknown"


def platform_of(url: str) -> str:
    """Bilinen platform adı (yoksa ``""``)."""
    host = ""
    if "://" in url:
        host = url.split("://", 1)[1].split("/", 1)[0].lower()
    for name, platform in PLATFORM_HOSTS.items():
        if host == name or host.endswith("." + name):
            return platform
    return ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------- indirme
@dataclass
class MediaFetch:
    available: bool
    reason: str = ""
    source: str = ""
    path: str = ""
    kind: str = "unknown"
    sha256: str = ""
    bytes: int = 0
    content_type: str = ""
    tool: str = ""


async def fetch_media(source: str, *, timeout: float = 120.0) -> MediaFetch:
    """Yerel yol ya da URL'den medya alır; sonucu sha256 ile mühürler."""
    value = (source or "").strip()
    if not value:
        return MediaFetch(available=False, reason="empty_source")

    local = Path(value).expanduser()
    if "://" not in value:
        if not local.exists() or not local.is_file():
            return MediaFetch(available=False, reason="not_found")
        return MediaFetch(
            available=True,
            source=value,
            path=str(local),
            kind=_kind_of(local),
            sha256=_sha256_file(local),
            bytes=local.stat().st_size,
            tool="local_path",
        )

    host = value.split("://", 1)[1].split("/", 1)[0].split(":")[0]
    if net_hygiene.is_private_host(host, env_name=PRIVATE_ALLOW_ENV):
        return MediaFetch(available=False, reason="private_address_rejected")

    target_dir = media_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return MediaFetch(available=False, reason="media_dir_unwritable", tool=type(exc).__name__)

    platform = platform_of(value)
    if platform:
        # Platform linkleri yt-dlp ister: yoksa UYDURMA indirme yapılmaz.
        exe = shutil.which("yt-dlp")
        if not exe:
            return MediaFetch(
                available=False, reason="dependency_missing:yt-dlp", source=value, tool=platform
            )
        try:
            proc = subprocess.run(
                [exe, "-o", str(target_dir / "%(id)s.%(ext)s"), "--no-playlist", value],
                capture_output=True,
                timeout=timeout,
            )
        except Exception as exc:
            return MediaFetch(available=False, reason=f"ytdlp_failed:{type(exc).__name__}", source=value)
        if proc.returncode != 0:
            return MediaFetch(available=False, reason="ytdlp_failed:rc", source=value, tool=platform)
        newest = max(target_dir.glob("*"), key=lambda p: p.stat().st_mtime, default=None)
        if newest is None:
            return MediaFetch(available=False, reason="download_missing", source=value, tool=platform)
        return MediaFetch(
            available=True,
            source=value,
            path=str(newest),
            kind=_kind_of(newest),
            sha256=_sha256_file(newest),
            bytes=newest.stat().st_size,
            tool=f"yt-dlp:{platform}",
        )

    suffix = Path(value.split("?", 1)[0]).suffix.lower()
    if suffix not in MEDIA_EXTENSIONS:
        return MediaFetch(available=False, reason="unsupported_extension", source=value)

    # [AUDIT 2026-10-08 · E-GÖZ1-3] İndirme merkezi istemci + SSRF kapısından
    # geçer. Eskiden `follow_redirects=True` ile ham `client.stream` kullanılıyordu:
    # ilk host kontrolünden SONRA bir yönlendirme ile özel ağa atlanabiliyordu
    # (net_hygiene ilk doma bakıyor, redirect atlamasını görmüyordu).
    # Şimdi: `safe_get` her atlamayı DNS-pinleme ile doğrular (stream modunda da).
    operator_allows_private = net_hygiene.allow_private(PRIVATE_ALLOW_ENV)
    try:
        async with build_secure_client(timeout=Timeout(timeout)) as client:
            if operator_allows_private:
                # Operatör özel adreslere AÇIKÇA izin vermiş: pinleme devre dışı;
                # yönlendirme yine kapalı, boyut sınırı yerinde.
                request = client.build_request("GET", value)
                response = await client.send(request, stream=True, follow_redirects=False)
            else:
                response = await safe_get(client, value, stream=True, max_redirects=3)
            try:
                if response.status_code != 200:
                    return MediaFetch(
                        available=False, reason=f"http_status:{response.status_code}", source=value
                    )
                content_type = response.headers.get("content-type", "")
                digest = hashlib.sha256()
                target = target_dir / f"fetch-{hashlib.sha256(value.encode()).hexdigest()[:16]}{suffix}"
                written = 0
                with open(target, "wb") as handle:
                    async for chunk in response.aiter_bytes(65536):
                        written += len(chunk)
                        if written > MAX_DOWNLOAD_BYTES:
                            handle.close()
                            target.unlink(missing_ok=True)
                            return MediaFetch(available=False, reason="too_large", source=value)
                        digest.update(chunk)
                        handle.write(chunk)
            finally:
                await response.aclose()
    except UnsafeURLError as exc:
        return MediaFetch(available=False, reason=f"ssrf_blocked:{exc.reason}", source=value)
    except Exception as exc:
        return MediaFetch(available=False, reason=f"download_failed:{type(exc).__name__}", source=value)

    return MediaFetch(
        available=True,
        source=value,
        path=str(target),
        kind=_kind_of(target, content_type),
        sha256=digest.hexdigest(),
        bytes=written,
        content_type=content_type,
        tool="httpx",
    )


# ------------------------------------------------------------- kare analizi
@dataclass
class FrameAnalysis:
    available: bool
    reason: str = ""
    path: str = ""
    kind: str = "unknown"
    width: int = 0
    height: int = 0
    fps: float = 0.0
    frames: int = 0
    duration_s: float = 0.0
    sampled: int = 0
    brightness_mean: float = 0.0
    brightness_std: float = 0.0
    dominant_color: tuple[int, int, int] = (0, 0, 0)
    sharpness: float = 0.0
    scenes: tuple[float, ...] = ()
    notes: dict[str, Any] = field(default_factory=dict)


def _cv2():
    try:
        import cv2  # noqa: PLC0415 (ağır import: yalnız gerektiğinde)

        return cv2
    except Exception:
        return None


def analyze_frames(path: str, *, sample_every: int = 5) -> FrameAnalysis:
    """Kare kare ÖLÇÜM: künye, parlaklık, baskın renk, sahne kesmeleri."""
    cv2 = _cv2()
    if cv2 is None:
        return FrameAnalysis(available=False, reason="dependency_missing:opencv")
    target = Path(path).expanduser()
    if not target.exists():
        return FrameAnalysis(available=False, reason="not_found", path=str(target))
    kind = _kind_of(target)
    if kind not in {"video", "image"}:
        return FrameAnalysis(available=False, reason=f"unsupported_kind:{kind}", path=str(target))

    import numpy as np

    if kind == "image":
        image = cv2.imread(str(target))
        if image is None:
            return FrameAnalysis(available=False, reason="decode_failed", path=str(target), kind=kind)
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean = image.reshape(-1, 3).mean(axis=0)
        return FrameAnalysis(
            available=True,
            path=str(target),
            kind=kind,
            width=int(width),
            height=int(height),
            frames=1,
            sampled=1,
            brightness_mean=round(float(gray.mean()), 4),
            brightness_std=round(float(gray.std()), 4),
            dominant_color=tuple(int(c) for c in mean[::-1]),  # BGR → RGB
            sharpness=round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 4),
        )

    capture = cv2.VideoCapture(str(target))
    if not capture.isOpened():
        return FrameAnalysis(available=False, reason="decode_failed", path=str(target), kind=kind)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    declared_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    step = max(1, int(sample_every or 1))
    readings: list[dict[str, Any]] = []
    previous_hist = None
    scenes: list[float] = []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
            cv2.normalize(hist, hist)
            scenes_hit = False
            if previous_hist is not None:
                # Korelasyon düşükse sahne değişti (ölçüm; yorum değil).
                correlation = float(cv2.compareHist(previous_hist, hist, cv2.HISTCMP_CORREL))
                if correlation < 0.6:
                    scenes_hit = True
            previous_hist = hist
            timestamp = index / fps if fps > 0 else 0.0
            readings.append(
                {
                    "frame": index,
                    "at_s": round(timestamp, 3),
                    "brightness": round(float(gray.mean()), 4),
                    "scene_cut": scenes_hit,
                }
            )
            if scenes_hit and len(scenes) < MAX_SCENES:
                scenes.append(round(timestamp, 3))
        index += 1
    capture.release()

    if not readings:
        return FrameAnalysis(available=False, reason="no_frames", path=str(target), kind=kind)

    brightness = [row["brightness"] for row in readings]
    return FrameAnalysis(
        available=True,
        path=str(target),
        kind=kind,
        width=width,
        height=height,
        fps=round(fps, 3),
        frames=index,
        duration_s=round(index / fps, 3) if fps > 0 else 0.0,
        sampled=len(readings),
        brightness_mean=round(sum(brightness) / len(brightness), 4),
        brightness_std=round(float(np.std(brightness)), 4),
        scenes=tuple(scenes),
        notes={
            "sample_every": step,
            "scene_threshold": 0.6,
            # Kapsayıcının BEYAN ettiği kare sayısı (ölçülenle uyuşmayabilir;
            # ikisi de dürüstçe raporlanır).
            "declared_frames": declared_frames,
        },
    )


# ---------------------------------------------------------------- transkript
@dataclass
class Transcript:
    available: bool
    reason: str = ""
    engine: str = ""
    text: str = ""
    chars: int = 0
    language: str = ""
    language_confidence: float = 0.0
    media_sha256: str = ""


def _local_transcribe_endpoint() -> tuple[str, str]:
    """Yerel STT ucu; uzak adres SERT reddedilir (ses metni dışarı çıkmaz)."""
    raw = os.getenv("PINEAL_TRANSCRIBE_URL", "").strip()
    if not raw:
        return "", ""
    if "://" not in raw:
        return "", "bad_endpoint_scheme"
    scheme, rest = raw.split("://", 1)
    if scheme not in {"http", "https"}:
        return "", "bad_endpoint_scheme"
    host = rest.split("/", 1)[0].split(":")[0].strip("[]").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return "", "non_local_endpoint"
    return raw, ""


def resolve_engine() -> tuple[str, str]:
    """Motor: yerel uç → yerel CLI. Uzak uç yapılandırılmışsa CLI'ye DÜŞÜLMEZ."""
    url_configured = bool(os.getenv("PINEAL_TRANSCRIBE_URL", "").strip())
    url, reason = _local_transcribe_endpoint()
    if url:
        return "local_endpoint", ""
    if url_configured:
        return "", reason
    command = os.getenv("PINEAL_TRANSCRIBE_CMD", "whisper").strip() or "whisper"
    try:
        parts = shlex.split(command)
    except ValueError:
        return "", "no_engine"
    head = parts[0]
    if os.path.isabs(head) or "/" in head or "\\" in head:
        return ("cli", "") if os.path.exists(head) else ("", "no_engine")
    return ("cli", "") if shutil.which(head) else ("", "no_engine")


def _extract_audio(path: Path) -> tuple[Path | None, str]:
    """Video → wav (ffmpeg). Ses dosyası zaten uygunsa dokunulmaz."""
    if _kind_of(path) == "audio":
        return path, ""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None, "dependency_missing:ffmpeg"
    target = path.with_name(path.stem + ".pineal-audio.wav")
    try:
        proc = subprocess.run(
            [exe, "-y", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(target)],
            capture_output=True,
            timeout=300,
        )
    except Exception as exc:
        return None, f"ffmpeg_failed:{type(exc).__name__}"
    if proc.returncode != 0 or not target.exists():
        return None, "ffmpeg_failed:rc"
    return target, ""


async def transcribe(path: str, *, timeout: float = 600.0) -> Transcript:
    """Medyayı yazıya döker: yalnız YEREL motor; boş çıktı iddia edilmez."""
    target = Path(path).expanduser()
    if not target.exists():
        return Transcript(available=False, reason="not_found")
    media_sha = _sha256_file(target)

    engine, reason = resolve_engine()
    if not engine:
        return Transcript(
            available=False,
            reason=reason or "no_engine",
            media_sha256=media_sha,
        )

    audio, audio_reason = _extract_audio(target)
    if audio is None:
        return Transcript(available=False, reason=audio_reason, engine=engine, media_sha256=media_sha)

    text = ""
    if engine == "local_endpoint":
        url, _ = _local_transcribe_endpoint()
        try:
            # Yerel uç (127.0.0.1) — safe_post KULLANILMAZ (yerel adresler
            # SSRF kapısı tarafından reddedilir); merkezi istemci yeterli.
            async with build_secure_client(timeout=Timeout(timeout)) as client:
                response = await client.post(url, json={"media_path": str(audio)})
            if response.status_code != 200:
                return Transcript(
                    available=False, reason=f"endpoint_status:{response.status_code}",
                    engine=engine, media_sha256=media_sha,
                )
            payload = response.json()
            text = str(payload.get("text", "")).strip()
        except Exception as exc:
            return Transcript(
                available=False, reason=f"endpoint_failed:{type(exc).__name__}",
                engine=engine, media_sha256=media_sha,
            )
    else:
        command = shlex.split(os.getenv("PINEAL_TRANSCRIBE_CMD", "whisper").strip() or "whisper")
        try:
            proc = subprocess.run(
                [*command, "--output_format", "txt", "--output_dir", str(audio.parent), str(audio)],
                capture_output=True,
                timeout=timeout,
            )
        except Exception as exc:
            return Transcript(
                available=False, reason=f"engine_failed:{type(exc).__name__}",
                engine=engine, media_sha256=media_sha,
            )
        if proc.returncode != 0:
            return Transcript(
                available=False,
                reason=f"engine_failed:rc{proc.returncode}",
                engine=engine,
                media_sha256=media_sha,
            )
        candidates = sorted(audio.parent.glob(audio.stem + "*.txt"))
        if candidates:
            text = candidates[0].read_text(encoding="utf-8", errors="replace").strip()
        elif proc.stdout:
            text = proc.stdout.decode("utf-8", errors="replace").strip()
        # rc=0 ve çıktı yok → aşağıda empty_transcript olarak raporlanır.

    if not text:
        return Transcript(
            available=False, reason="empty_transcript", engine=engine, media_sha256=media_sha
        )

    language, confidence = "", 0.0
    try:
        from agent_core.services.language import detect_language

        finding = detect_language(text)
        language, confidence = finding.language, float(finding.confidence or 0.0)
    except Exception:
        language, confidence = "unknown", 0.0

    return Transcript(
        available=True,
        engine=engine,
        text=text,
        chars=len(text),
        language=language,
        language_confidence=round(confidence, 4),
        media_sha256=media_sha,
    )


# ------------------------------------------------------------ görsel benzerlik
def phash(path: str, *, size: int = 32, low: int = 8) -> str:
    """DCT tabanlı algısal parmak izi (64 bit, hex). Boş dize = hesaplanamadı."""
    cv2 = _cv2()
    if cv2 is None:
        return ""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return ""
    import numpy as np

    resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(resized)
    # DC terimi (parlaklık) DIŞARIDA: kalan 63 katsayı yapıyı taşır.
    # DC dahil edilirse düz renkli iki fotoğraf "aynı" çıkardı — yanlış olurdu.
    block = dct[:low, :low].flatten()[1:]
    median = float(np.median(block))
    bits = "".join("1" if value > median else "0" for value in block)
    return f"{int(bits, 2):016x}"


def _hamming(a: str, b: str) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


@dataclass
class SimilarityResult:
    available: bool
    reason: str = ""
    query_path: str = ""
    query_hash: str = ""
    index_size: int = 0
    matches: tuple[dict[str, Any], ...] = ()


def _rebuild_index(limit: int = MAX_INDEX_FILES) -> dict[str, dict[str, Any]]:
    """Medya dizinindeki görsellerin pHash indeksini tazeler (dürüst: atlananı sayar)."""
    base = media_dir()
    index: dict[str, dict[str, Any]] = {}
    skipped = 0
    if not base.exists():
        return {"files": {}, "skipped": 0}  # type: ignore[return-value]
    for path in sorted(base.iterdir())[:limit]:
        if not path.is_file() or _kind_of(path) != "image":
            continue
        digest = phash(str(path))
        if not digest:
            skipped += 1
            continue
        index[path.name] = {"sha256": _sha256_file(path), "phash": digest}
    return {"files": index, "skipped": skipped}  # type: ignore[return-value]


def visual_similarity(path: str, *, top_k: int = 3) -> SimilarityResult:
    """Yerel pHash indeksinde en yakın görselleri bulur (Hamming mesafesi)."""
    target = Path(path).expanduser()
    if not target.exists():
        return SimilarityResult(available=False, reason="not_found", query_path=str(target))
    query_hash = phash(str(target))
    if not query_hash:
        return SimilarityResult(
            available=False, reason="dependency_missing:opencv", query_path=str(target)
        )
    if not media_dir().exists():
        media_dir().mkdir(parents=True, exist_ok=True)

    index = _rebuild_index()
    files = dict(index.get("files", {}))
    files[target.name] = {"sha256": _sha256_file(target), "phash": query_hash}
    index_path().write_text(
        json.dumps({"version": 1, "files": files, "skipped": index.get("skipped", 0)},
                   ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    scored = [
        (name, row["phash"], _hamming(query_hash, row["phash"]))
        for name, row in files.items()
        if name != target.name
    ]
    scored.sort(key=lambda row: (row[2], row[0]))
    matches = tuple(
        {"file": name, "phash": digest, "distance": distance, "similar": distance <= 10}
        for name, digest, distance in scored[: max(1, int(top_k or 3))]
    )
    return SimilarityResult(
        available=True,
        query_path=str(target),
        query_hash=query_hash,
        index_size=len(files),
        matches=matches,
    )
