"""X (Twitter) sensör akışı — ``api.run_mission`` içinden çıkarıldı.

[API-BÖLME 7 · 2026-11-11] ``backend/api.py`` ratchet tavanının üstündeydi;
repo kuralı "satır eklemek yerine MODÜL ÇIKAR". Davranış BİREBİR korunur:

    - Sensör koşarsa ``channel_rows`` "koştu + N zaman damgalı gönderi" der.
    - Kanıt üretilemezse SAHTE PROFİL ÜRETİLMEZ; "bulunamadı" ile "hiç
      çalışmadı" ayrı görünsün diye makine-okunur sebep (``channel_reason``)
      kanal defterine yazılır ve açık kaynak dosyası yoluna düşülür.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent_core.scraper.instagram_ghost import (
    InsufficientEvidenceError as ScraperInsufficientEvidenceError,
)
from agent_core.task_executor import InsufficientEvidenceError
from backend.services.web_dossier import x_sensor_channel_rows

__all__ = ["XDispatchResult", "run_x_dispatch"]


@dataclass
class XDispatchResult:
    """X sensörünün sonucu: profil + kanal defteri + kanıt üretilemediyse sebep."""

    profile: dict = field(default_factory=dict)
    channel_rows: list[Any] = field(default_factory=list)
    reason: str = ""


async def run_x_dispatch(
    *,
    url: str,
    vault_locked: bool,
    scrape_x: Callable[..., Awaitable[dict]],
    log: Callable[[str, str], None],
) -> XDispatchResult:
    """X URL'sini kazı; sonuç HER durumda kanal defterine yazılır."""
    x_profile: dict = {}
    x_sensor_reason = ""
    channel_rows: list[Any] = []
    log("INFO", f"UPLINK: Hedefe sızılıyor -> {url} [X · twscrape]")
    try:
        x_profile = await scrape_x(
            url,
            log=log,
            vault_locked=vault_locked,
            rate_ok=True,
        )
        channel_rows.extend(
            x_sensor_channel_rows(
                ok_detail=(
                    f"{len(x_profile.get('post_times') or [])} zaman damgalı gönderi"
                )
            )
        )
        log("INFO",
            f"TELEMETRİ: X akışı ele geçirildi — {len(x_profile['post_times'])} gerçek zaman damgalı gönderi.",
        )
    except (InsufficientEvidenceError, ScraperInsufficientEvidenceError) as exc:
        x_sensor_reason = str(exc)[:200]
        # [P0] Sensör koşmadı → sebep kanıt defterine yazılır. "Bulunamadı"
        # ile "hiç çalışmadı" ARTIK AYRI görünür. Makine-okunur sebep
        # (örn. `no_session_pool`) istisna üzerinde taşınıyorsa o kullanılır.
        channel_rows.extend(
            x_sensor_channel_rows(
                reason=x_sensor_reason,
                machine_reason=str(getattr(exc, "channel_reason", None) or ""),
            )
        )
        log("WARNING",
            f"X SENSÖRÜ KANIT ÜRETEMEDİ ({x_sensor_reason}); "
            "profil uydurulmadı, açık kaynak dosyası ile devam ediliyor.",
        )

    return XDispatchResult(profile=x_profile, channel_rows=channel_rows, reason=x_sensor_reason)
