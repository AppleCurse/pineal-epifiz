"""Kazıma deneme döngüsü — altyapı farkındalığıyla.

Neden ayrı modül: ``backend/api.py`` tek-modül tavanına (5760 satır) dayandı;
repo kuralı "yeni kod eklemek yerine MODÜL ÇIKAR" (``tests/unit/
test_api_monolith_ratchet.py``). Bu döngü, ``api.py``'nin içine gömülü kalmak
yerine buraya taşındı: hem dosya küçüldü hem de davranış tek başına test
edilebilir hâle geldi.

Neden var (ölçülen kusur, 2026-11-11):
    Playwright Python paketi kurulu ama **tarayıcı ikilisi yokken** Instagram
    kazıması üç kez deneniyor, her seferinde
    ``BrowserType.launch: Executable doesn't exist`` alınıyor ve görev
    "kazıma altyapısı denemeleri tüketti" ile ölüyordu. Ölçüm: 3 deneme ≈ 7 sn
    boşa bekleme; operatöre NE yapacağı söylenmiyordu.

    Bu modül iki şeyi değiştirir:
      1. Denemeden ÖNCE ucuz gerçek kontrol (`browser_binary_status`): ikili
         yoksa tek denemede, kurulum adımını içeren ret.
      2. Deneme SIRASINDA kalıcı altyapı arızası görülürse
         (`is_fatal_infrastructure_failure`) yeniden deneme kesilir.

Sözleşme:
    - Kanıtsız profille analiz ÇALIŞTIRILMAZ (mevcut dürüstlük kuralı korunur).
    - Kişiye özel kanıt yetersizliği (gizli hesap vb.) altyapı arızası
      SAYILMAZ; mevcut davranış aynen sürer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from agent_core.scraper.instagram_ghost import (
    InsufficientEvidenceError as ScraperInsufficientEvidenceError,
)
from agent_core.services.browser_session import BrowserUnavailableError
from agent_core.task_executor import InsufficientEvidenceError as ExecutorInsufficientEvidenceError
from backend.services.browser_capability import (
    browser_binary_status,
    is_fatal_infrastructure_failure,
    remediation_hint,
)

__all__ = ["ScrapeAttemptResult", "INSTAGRAM_REJECT_PREFIX", "run_scrape_attempts"]

#: Altyapı arızasında ret mesajının öneki (UI/telemetri bunu arar).
INSTAGRAM_REJECT_PREFIX = "KAZIMA ALTYAPISI KULLANILAMIYOR"

#: Dürüst, kişiye özel kanıt yetersizliği mesajı (davranış değişmedi).
EVIDENCE_REJECT_MESSAGE = (
    "HEDEF VERİSİ ALINAMADI: kazıma altyapısı denemeleri tüketti; analiz başlatılmadı."
)


@dataclass
class ScrapeAttemptResult:
    """Döngünün sonucu: profil doldu mu, deneme sayısı, terminal hata."""

    profile: dict = field(default_factory=dict)
    attempts: int = 0
    last_error: Optional[BaseException] = None
    infrastructure_failure: bool = False
    #: Kanıt yetersizliği (kişiye özel) — çağıran `enable_cross` ise OSINT'e düşer.
    insufficient_evidence: Optional[BaseException] = None

    def reject_message(self) -> str:
        """Terminal ret için operatöre gösterilecek mesaj."""
        if self.infrastructure_failure:
            return f"{INSTAGRAM_REJECT_PREFIX}: {str(self.last_error)[:300]}"
        return EVIDENCE_REJECT_MESSAGE


async def run_scrape_attempts(
    *,
    url: str,
    cookie: str,
    max_attempts: int,
    scrape: Callable[..., Awaitable[dict]],
    log: Callable[[str, str], None],
    preflight: bool = True,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> ScrapeAttemptResult:
    """Kazımayı en fazla ``max_attempts`` kez dene; altyapı arızasında KES.

    ``scrape`` imzası: ``await scrape(url, cookie, log=...) -> dict``.
    ``preflight=True`` iken her denemeden önce tarayıcı ikilisi kontrol edilir
    (dosya sistemi kontrolü; ucuz).
    """
    result = ScrapeAttemptResult()
    attempts = max(1, int(max_attempts))

    for attempt in range(1, attempts + 1):
        result.attempts = attempt
        try:
            if preflight:
                # [ALTYAPI ÖN KONTROLÜ] Üç kez denemek yerine tek gerçek ölçüm.
                state = browser_binary_status()
                if not state.available:
                    raise BrowserUnavailableError(remediation_hint(state))
            result.profile = await scrape(url, cookie, log=log) or {}
            result.last_error = None
            result.infrastructure_failure = False
            return result
        except Exception as exc:  # noqa: BLE001 - sınıflandırma aşağıda
            # Kanıt yetersizliği çağırana AYNEN taşınır (davranış korunur).
            if isinstance(exc, _EVIDENCE_ERRORS):
                result.insufficient_evidence = exc
                return result

            result.last_error = exc
            log(
                "ERROR",
                f"UPLINK KOPTU (Deneme {attempt}/{attempts}): "
                f"{type(exc).__name__}: {str(exc)[:100]}",
            )
            if is_fatal_infrastructure_failure(exc):
                result.infrastructure_failure = True
                log(
                    "ERROR",
                    "KAZIMA ALTYAPISI KALICI OLARAK KULLANILAMIYOR — "
                    "yeniden deneme atlandı (aynı hata tekrarlanır).",
                )
                return result
            if attempt < attempts:
                await sleep(min(2 * attempt, 5))

    return result


#: Kanıt yetersizliği istisnaları — İKİ AYRI SINIF vardır ve ikisi de
#: "kişiye özel kanıt yok" anlamına gelir (altyapı arızası DEĞİL):
#:   - agent_core.task_executor.InsufficientEvidenceError
#:   - agent_core.scraper.instagram_ghost.InsufficientEvidenceError
#: Bunlar çağırana AYNEN taşınır; `enable_cross` ise OSINT yoluna düşülür.
_EVIDENCE_ERRORS: tuple[type[BaseException], ...] = (
    ExecutorInsufficientEvidenceError,
    ScraperInsufficientEvidenceError,
)
