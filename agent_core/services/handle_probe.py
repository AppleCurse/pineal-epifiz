"""Çapraz platform kullanıcı-adı yoklaması (native, dış bağımlılık YOK).

Neden var?
    2026-10-23 ölçümü: "X'te bulunan hedef Instagram'da / Facebook'ta /
    Threads'te aransın" beklentisi yalnız `ENABLE_MAIGRET` kapısının arkasında
    duruyordu. Maigret kapalıyken (varsayılan) hedefin adı hiçbir başka
    platformda ARANMIYORDU; çapraz tarama yalnız arama motorunun kendiliğinden
    döndürdüğü URL'lere bağlıydı. Bu modül o boşluğu kapatır: verilen kullanıcı
    adını bilinen platformların kanonik profil adreslerinde YOKLAR.

Dürüstlük sözleşmesi (değişmez):
    * **Uydurma yok.** Yalnız HTTP durum kodu + yönlendirme hedefi konuşur.
      Sayfa gövdesi yorumlanmaz (profil sayfalarının nav'ında da "Log in"
      yazar; gövde okumak yanlış "yok" üretirdi).
    * **Yokluk ancak kanıtlanabilirse iddia edilir** (`absence_claimable`):
      sıfır hata VE sıfır "bilinmiyor" gereklidir. 403/429/login duvarı
      görüldüyse "hesap yok" DENMEZ; `unknown` olarak raporlanır.
    * Her istek egress omurgasından çıkar (`purpose="sensor"`) → kasa kapısı
      ve Sorumluluk Zinciri izi zorunludur.
    * Tüm çıkışlar bütçeyle sınırlıdır (`PINEAL_HANDLE_PROBE_BUDGET_SEC`)
      ve sıralıdır: hedefe/plATFORMA yük bindiren paralel sel yok.

Kapı: yetenek katmanında `ENABLE_CROSS_PLATFORM` (+ kasa). Bu modül kendi
kapısını OKUMAZ; karar tek yerden (`CapabilityRegistry` / PolicyKernel) gelir.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

__all__ = [
    "PROBE_PLATFORMS",
    "HandleProbe",
    "HandleProbeResult",
    "probe_handle",
    "probe_platforms",
]


#: (platform, kanonik profil URL şablonu). Sıra = yoklama sırası.
#: Yalnız PROFİL yolu; arama/keşif sayfası yoklanmaz (yanlış "var" üretmesin).
PROBE_PLATFORMS: tuple[tuple[str, str], ...] = (
    ("instagram", "https://www.instagram.com/{handle}/"),
    ("facebook", "https://www.facebook.com/{handle}"),
    ("threads", "https://www.threads.net/@{handle}"),
    ("x", "https://x.com/{handle}"),
    ("tiktok", "https://www.tiktok.com/@{handle}"),
    ("github", "https://github.com/{handle}"),
    ("reddit", "https://www.reddit.com/user/{handle}"),
    ("pinterest", "https://www.pinterest.com/{handle}/"),
    ("youtube", "https://www.youtube.com/@{handle}"),
    ("telegram", "https://t.me/{handle}"),
)

#: Durum sözlüğü (makine-okunur; raporda gizlenmez).
STATUS_CLAIMED = "claimed"      # 200: profil sayfası açıldı
STATUS_ABSENT = "absent"        # 404/410: profil yok
STATUS_UNKNOWN = "unknown"      # login duvarı / 403 / 429 / yönlendirme
STATUS_ERROR = "error"          # ağ hatası / 5xx

#: Yönlendirme hedefinde görülürse "bilinmiyor" sayılır (duvar işareti).
_WALL_MARKERS = ("login", "accounts/login", "checkpoint", "challenge", "consent")


class HandleProbe(BaseModel):
    """Tek platformun yoklama kaydı."""

    platform: str
    url: str
    status: str
    http_status: Optional[int] = None
    reason: str = ""
    model_config = ConfigDict(extra="forbid")


class HandleProbeResult(BaseModel):
    """Bir kullanıcı adının çapraz platform yoklama sonucu."""

    requested_username: str
    available: bool = False
    reason: Optional[str] = None
    provider: str = "handle_probe"
    probes: List[HandleProbe] = Field(default_factory=list)
    scanned_count: int = 0
    error_count: int = 0
    unknown_count: int = 0
    #: "Hiçbir platformda yok" iddiası YALNIZ bu bayrak True ise kurulabilir.
    absence_claimable: bool = False
    elapsed_ms: int = 0
    model_config = ConfigDict(extra="forbid")

    @property
    def claimed(self) -> List[HandleProbe]:
        return [p for p in self.probes if p.status == STATUS_CLAIMED]

    @property
    def found_sites(self) -> List[HandleProbe]:
        return self.claimed

    def to_username_scan(self) -> dict[str, Any]:
        """`username_scan` sözlüğüyle aynı şekle çevir (maigret uyumlu).

        `provider` alanı KİMLİĞİ gizlemez: bu tarama maigret değil,
        native yoklamadır; kaynağı raporda görünür.
        """
        return {
            "requested_username": self.requested_username,
            "available": self.available,
            "provider": self.provider,
            "reason": self.reason,
            "scanned_count": self.scanned_count,
            "error_count": self.error_count,
            "unknown_count": self.unknown_count,
            "absence_claimable": self.absence_claimable,
            "found_sites": [
                {"site": p.platform, "url": p.url, "status": p.status}
                for p in self.claimed
            ],
        }


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def probe_platforms(limit: Optional[int] = None) -> Sequence[tuple[str, str]]:
    """Yoklanacak platform listesi (operatör daraltabilir).

    ``PINEAL_HANDLE_PROBE_PLATFORMS`` virgüllü liste verirse (ör.
    ``"instagram,facebook,threads"``) yalnız onlar yoklanır; bilinmeyen ad
    sessizce yutulmaz — çağıran sonucu `scanned_count` üzerinden görür.
    """
    cap = limit if limit is not None else _env_int("PINEAL_HANDLE_PROBE_PLATFORMS_LIMIT", 10, 1, 10)
    raw = os.getenv("PINEAL_HANDLE_PROBE_PLATFORMS", "").strip()
    if raw:
        wanted = {p.strip().lower() for p in raw.split(",") if p.strip()}
        selected = tuple((p, t) for p, t in PROBE_PLATFORMS if p in wanted)
        if selected:
            return selected[:cap]
        logger.warning("handle_probe: PINEAL_HANDLE_PROBE_PLATFORMS tanınmadı (%s)", raw[:80])
    return PROBE_PLATFORMS[:cap]


def _sanitize(username: str) -> Optional[str]:
    """Kullanıcı adı doğrulaması — maigret ile AYNI kural (tek kaynak)."""
    from agent_core.services.maigret_scanner import sanitize_username

    return sanitize_username((username or "").strip())


def _classify(status_code: int, location: str) -> tuple[str, str]:
    """HTTP durumu → (durum, makine-okunur sebep). Gövde YORUMLANMAZ."""
    if status_code == 200:
        return STATUS_CLAIMED, ""
    if status_code in (404, 410):
        return STATUS_ABSENT, ""
    if status_code in (301, 302, 303, 307, 308):
        lowered = (location or "").lower()
        if any(marker in lowered for marker in _WALL_MARKERS):
            return STATUS_UNKNOWN, "login_wall"
        return STATUS_UNKNOWN, "redirect"
    if status_code == 429:
        return STATUS_UNKNOWN, "rate_limited"
    if status_code in (401, 403):
        return STATUS_UNKNOWN, "blocked"
    if 500 <= status_code < 600:
        return STATUS_ERROR, f"http_{status_code}"
    return STATUS_UNKNOWN, f"http_{status_code}"


async def probe_handle(
    username: str,
    *,
    platforms: Optional[Iterable[tuple[str, str]]] = None,
    client: Any = None,
) -> HandleProbeResult:
    """Kullanıcı adını bilinen platformlarda yoklar.

    Args:
        username: ``@`` öneki kabul edilir; doğrulama maigret kuralıyla.
        platforms: (platform, şablon) çiftleri; verilmezse operatör/env listesi.
        client: Test dikişi — verilirse ``egress.open_client`` çağrılmaz,
            bu nesnenin async ``get`` metodu kullanılır.

    Not: Yetenek kapısı (ENABLE_CROSS_PLATFORM / kasa) BURADA uygulanmaz;
    bu fonksiyon çağrıldığında kapı çoktan geçilmiştir.
    """
    started = time.monotonic()
    clean = _sanitize(username)
    if not clean:
        return HandleProbeResult(
            requested_username=(username or "")[:64],
            available=False,
            reason="invalid_username",
        )

    selected = tuple(platforms) if platforms is not None else tuple(probe_platforms())
    if not selected:
        return HandleProbeResult(
            requested_username=clean, available=False, reason="no_platforms"
        )

    timeout = _env_float("PINEAL_HANDLE_PROBE_TIMEOUT", 8.0, 1.0, 30.0)
    budget = _env_float("PINEAL_HANDLE_PROBE_BUDGET_SEC", 30.0, 1.0, 180.0)
    pause = _env_float("PINEAL_HANDLE_PROBE_PAUSE", 0.25, 0.0, 5.0)
    deadline = started + budget

    probes: List[HandleProbe] = []
    errors = 0
    unknown = 0
    owns_client = client is None

    from agent_core.capabilities.egress import open_client  # geç import: testte yamanabilir

    def _make(url: str):
        return open_client(
            purpose="sensor",
            target=url,
            timeout=timeout,
            follow_redirects=False,
        )

    shared = client
    for index, (platform, template) in enumerate(selected):
        url = template.format(handle=clean)
        if time.monotonic() >= deadline:
            probes.append(HandleProbe(platform=platform, url=url, status=STATUS_UNKNOWN, reason="budget_exhausted"))
            unknown += 1
            continue
        if index and pause:
            import asyncio

            await asyncio.sleep(pause)
        try:
            if shared is None:
                async with _make(url) as own:
                    response = await own.get(url)
            else:
                response = await shared.get(url)
            status, reason = _classify(int(response.status_code), str(response.headers.get("location") or ""))
            probes.append(HandleProbe(
                platform=platform, url=url, status=status,
                http_status=int(response.status_code), reason=reason,
            ))
            if status == STATUS_ERROR:
                errors += 1
            elif status == STATUS_UNKNOWN:
                unknown += 1
        except Exception as exc:  # ağ/transport hatası — hesap YOK denmez
            logger.warning("handle_probe %s hatası: %s", platform, type(exc).__name__)
            probes.append(HandleProbe(
                platform=platform, url=url, status=STATUS_ERROR,
                reason=f"transport:{type(exc).__name__}",
            ))
            errors += 1
    if owns_client and shared is not None:
        try:
            await shared.aclose()
        except Exception:
            pass

    return HandleProbeResult(
        requested_username=clean,
        available=True,
        probes=probes,
        scanned_count=len(probes),
        error_count=errors,
        unknown_count=unknown,
        absence_claimable=(len(probes) > 0 and errors == 0 and unknown == 0),
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
