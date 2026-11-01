"""Instagram medya zamanı — shortcode'dan bağımsız çapraz doğrulama.

Neden: bir dökümün tarihleri, onları üreten katmanın iddiasıdır. Oysa medya
kimliği (shortcode) platform tarafından üretilir ve monoton artan bir Snowflake
ID'nin base64'üdür: ``((id >> 23) + 1314220021721)`` ms. Bu, tarihin
MATEMATİKSEL çapraz kontrolüdür — tarih uydurulduysa shortcode yakalar.

Kullanım: yalnız DOĞRULAMA. Tarih bu fonksiyonla ÜRETİLMEZ; bir karenin
beyan ettiği ``observed_at`` ile shortcode zamanı uyuşmuyorsa kare reddedilir
ve sebep kayda geçer (bkz. ``observation_adapter``).

Tüketici: ``observation_adapter.VisualFrameExtractor``.
Test: ``tests/lifecycle/test_lifecycle_ig_time.py``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

__all__ = ["decode_ig_shortcode_utc", "shortcode_from_url", "shortcode_time_drift_hours"]

_IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
#: Instagram medya ID epoch'u (2011-08-24T21:07:01.721Z).
_IG_EPOCH_MS = 1314220021721
#: 11 karakterden uzun shortcode'lar mevcut değil; makul aralık 5..15.
_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,15}$")
_URL_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]{5,15})")


def shortcode_from_url(url: str) -> Optional[str]:
    """``instagram.com/p/<shortcode>/`` → ``<shortcode>`` (yoksa None)."""
    if not isinstance(url, str):
        return None
    match = _URL_RE.search(url)
    return match.group(1) if match else None


def decode_ig_shortcode_utc(shortcode: str) -> Optional[datetime]:
    """Shortcode → medyanın oluşturulma zamanı (UTC). Çözülemezse None."""
    if not isinstance(shortcode, str):
        return None
    candidate = shortcode.strip()
    if not _SHORTCODE_RE.match(candidate):
        return None

    media_id = 0
    for char in candidate[:11]:
        index = _IG_ALPHABET.find(char)
        if index < 0:
            return None
        media_id = (media_id << 6) | index

    timestamp_ms = (media_id >> 23) + _IG_EPOCH_MS
    if timestamp_ms <= _IG_EPOCH_MS:
        return None
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def shortcode_time_drift_hours(observed_at: datetime, shortcode: str) -> Optional[float]:
    """Beyan edilen zaman ile shortcode zamanı arasındaki fark (saat).

    Shortcode çözülemezse None döner — bu "uyuşmazlık YOK" demek değildir,
    "doğrulanamadı" demektir; çağıran taraf bunu ayrı raporlar.
    """
    decoded = decode_ig_shortcode_utc(shortcode)
    if decoded is None:
        return None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return abs((observed_at.astimezone(timezone.utc) - decoded).total_seconds()) / 3600.0
