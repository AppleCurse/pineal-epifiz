"""P0 · KANAL DURUMU — "koşmadı" ile "bulamadı" AYRIMI.

Neden (denetim 2026-10-16 · Bulgu B-1 / B-2):
    Bir yetenek bayrak, kasa, bağımlılık veya hesap havuzu yüzünden koşmadığında
    sistem "boş liste" dönüyordu; kullanıcı bunu "hedefte hiçbir iz yok" ile
    karıştırabiliyordu. X sensörü daha kötüsünü yapıyordu: boş twscrape hesap
    havuzunda sebebi ``user_not_found`` (yani "kullanıcı yok") diye yazıyordu.

Sözleşme:
    Her kanal (sensör/araştırma) üç durumdan birini üretir:

        ``ok``       → çalıştı ve kanıt üretti
        ``not_run``  → ÇALIŞMADI (bayrak kapalı / kasa kilitli / bağımlılık yok /
                       hesap havuzu boş) — sebep MAKİNE-OKUNUR
        ``failed``   → çalışmayı denedi, hata/timeout oldu — sebep yazılır

    "Boş sonuç" (kanıt üretildi ama eşleşme yok) ``ok`` + ``detail`` olarak
    ayrılır; ``not_run`` asla "bulunamadı" anlamına gelmez.

Bu, görev zincirinin telemetrisine, WebSocket yayınına ve UI'a taşınır.
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

__all__ = [
    "CHANNEL_OK",
    "CHANNEL_NOT_RUN",
    "CHANNEL_FAILED",
    "ChannelRun",
    "ok",
    "not_run",
    "failed",
    "from_engine_result",
    "serialize",
    "summarize",
]

CHANNEL_OK = "ok"
CHANNEL_NOT_RUN = "not_run"
CHANNEL_FAILED = "failed"


class ChannelRun(BaseModel):
    """Tek kanalın çalışma durumu."""

    channel: str
    status: str = CHANNEL_OK
    reason: str | None = None
    detail: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "status": self.status,
            "reason": self.reason,
            "detail": self.detail,
        }


def ok(channel: str, detail: str | None = None) -> ChannelRun:
    """Kanal çalıştı (kanıt üretti)."""
    return ChannelRun(channel=channel, status=CHANNEL_OK, detail=detail)


def not_run(channel: str, reason: str, detail: str | None = None) -> ChannelRun:
    """Kanal ÇALIŞMADI — sebep zorunlu (boş liste dönmek yasak)."""
    return ChannelRun(
        channel=channel,
        status=CHANNEL_NOT_RUN,
        reason=str(reason or "unknown"),
        detail=detail,
    )


def failed(channel: str, reason: str, detail: str | None = None) -> ChannelRun:
    """Kanal denendi ama hata/timeout verdi."""
    return ChannelRun(
        channel=channel,
        status=CHANNEL_FAILED,
        reason=str(reason or "unknown"),
        detail=detail,
    )


def _read(result: Any, key: str) -> Any:
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def from_engine_result(channel: str, result: Any) -> ChannelRun:
    """Bir tarayıcı/kapasite sonucunu kanal durumuna çevirir.

    Ayrım kuralı:
        * ``available=True``                → ``ok`` (kanıt üretildi)
        * ``available=False`` ve tarama HİÇ başlamadı (``scanned_count == 0``)
          → ``not_run`` (kapı kapalı / bağımlılık yok / kasa kilitli)
        * ``available=False`` ama tarama başladı (``scanned_count > 0``)
          → ``failed`` (koştu, hata verdi)

    Böylece "hiç çalışmadı" ile "çalıştı ama eşleşme bulamadı" ayrımı
    kaybolmaz.
    """
    if result is None:
        return not_run(channel, reason="no_result")
    available = bool(_read(result, "available"))
    reason = _read(result, "reason")
    scanned = _read(result, "scanned_count")
    try:
        scanned_count = int(scanned or 0)
    except (TypeError, ValueError):
        scanned_count = 0
    if available:
        found = _read(result, "found_sites")
        try:
            count = len(found or [])
        except TypeError:
            count = 0
        return ok(
            channel,
            detail=(
                f"{count} eşleşme / {scanned_count} tarama"
                if scanned_count
                else f"{count} eşleşme"
            ),
        )
    if scanned_count > 0:
        return failed(
            channel,
            reason=str(reason or "provider_errors"),
            detail=f"{scanned_count} tarama denendi",
        )
    return not_run(channel, reason=str(reason or "unavailable"))


def serialize(runs: Iterable[Any]) -> list[dict[str, Any]]:
    """ChannelRun listesini WS/UI için düz sözlüğe çevirir."""
    out: list[dict[str, Any]] = []
    for run in runs or ():
        if isinstance(run, ChannelRun):
            out.append(run.to_dict())
        elif isinstance(run, dict):
            out.append(
                {
                    "channel": str(run.get("channel") or ""),
                    "status": str(run.get("status") or CHANNEL_OK),
                    "reason": run.get("reason"),
                    "detail": run.get("detail"),
                }
            )
    return out


def summarize(runs: Iterable[Any]) -> dict[str, Any]:
    """Kısa özet: kaç kanal ok / not_run / failed + koşmayanların sebepleri."""
    rows = serialize(runs)
    counts = {CHANNEL_OK: 0, CHANNEL_NOT_RUN: 0, CHANNEL_FAILED: 0}
    reasons: list[dict[str, str]] = []
    for row in rows:
        status = row.get("status") or CHANNEL_OK
        counts[status] = counts.get(status, 0) + 1
        if status in (CHANNEL_NOT_RUN, CHANNEL_FAILED):
            reasons.append(
                {
                    "channel": row.get("channel") or "",
                    "status": status,
                    "reason": row.get("reason") or "unknown",
                }
            )
    return {
        "channels_total": len(rows),
        "ok": counts[CHANNEL_OK],
        "not_run": counts[CHANNEL_NOT_RUN],
        "failed": counts[CHANNEL_FAILED],
        "not_run_reasons": reasons,
    }
