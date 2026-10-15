"""Capability Spine · TEK HTTP ÇIKIŞ KAPISI (egress) — E-GÖZ1-3.

Neden var?
    Denetim (2026-10-06, E-GÖZ1-3): ``agent_core`` içinde 8 dosya yetenek
    omurgasını/registry'yi atlayıp doğrudan ``httpx`` ile dışarı çıkıyordu
    (paralel yol ihlali). Sorumluluk Zinciri ilkesi: *her dışa çıkış bir
    kapıdan geçer, kapı da izini bırakır.*

Sözleşme:
    1. ``agent_core`` içinde satır başı ``import httpx`` YALNIZCA bu dosyada
       yaşar (tip/istisna erişimi için yeniden ihracat edilir).
    2. ``httpx.AsyncClient(...)`` inşası YALNIZCA :func:`open_client`
       içindedir — başka hiçbir yerde istemci kurulamaz.
    3. Her ``open_client`` çağrısı, amaç (``purpose``) ve hedefiyle birlikte
       görevin Sorumluluk Zinciri'ne (``attempted_paths``) yazılır; denetim
       sırasında "ne dışarı çıktı" sorusunun cevabı hazırdır.
    4. OSINT amaçlı çıkışlar (``osint``/``search``/``sensor``/``scraper``)
       yaprak kasa kapısından geçer (bkz. ``agent_core/scraper/vault_gate.py``):
       kilitliyse istemci HİÇ OLUŞTURULMAZ, ``VaultLockedError`` fırlatılır.
       Kasa kararı tek yerden okunur; bu modül kendi kendine "kilitli mi?"
       YORUMU ÜRETMEZ.

Not (dürüstlük): bu modül bir "yetenek" değildir; omurganın kendi parçasıdır.
Politikasız bir kapı dekorasyondur — bu yüzden OSINT precheck'i zorunludur ve
``tests/unit/test_egress_single_spine.py`` ile kilitlenmiştir.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

# agent_core'daki TEK satır başı httpx importu (E-GÖZ1-3 beyanı).
import httpx  # noqa: F401  (yeniden ihracat: tip/istisna erişimi)

__all__ = [
    "httpx",
    "EgressAttempt",
    "VAULT_ENFORCED_PURPOSES",
    "drain_egress_attempts",
    "egress_attempts",
    "open_client",
]

logger = logging.getLogger(__name__)

#: Kasa kilidinin ikinci (yaprak) hattında denetlenen çıkış amaçları.
#: LLM/medya/probe amaçları bu sette DEĞİLDİR: Tüzük Md.4 OSINT, tarama ve
#: scraper çıkışlarını kapatır; sohbet/analiz içi model çağrıları kapatmaz.
VAULT_ENFORCED_PURPOSES = frozenset({"osint", "search", "sensor", "scraper"})


@dataclass(frozen=True)
class EgressAttempt:
    """Sorumluluk Zinciri'ne yazılan tek bir dışa çıkış denemesi."""

    purpose: str
    target: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


#: Görev-bağlamı (context-local) deneme izi. ``asyncio`` görevleri arasında
#: yalıtıktır: bir ajanın denemeleri başka bir ajanın kaydına karışmaz.
_attempts: ContextVar[tuple[EgressAttempt, ...]] = ContextVar(
    "pineal_egress_attempts", default=()
)


def _safe_target(target: Any) -> str:
    """Return a useful destination label without retaining URL secrets.

    Egress records are copied into task evidence and application logs. Raw URLs
    can contain credentials, signed paths, API keys in query parameters, or
    fragments. Preserve the scheme/host/port and only indicate whether a path
    exists; this is enough to identify the destination without persisting its
    request-specific secret material.
    """
    raw = str(target or "").strip()
    if not raw:
        return ""
    has_scheme = "://" in raw
    candidate = raw if has_scheme else f"//{raw}"
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        # Malformed URL: don't echo a possible credential-bearing raw value.
        return "<invalid-url>" if has_scheme else "<redacted>"
    if not hostname:
        return raw[:200] if not has_scheme and "@" not in raw else "<redacted>"
    host = hostname.rstrip(".").lower()
    if ":" in host:
        host = f"[{host}]"
    scheme = f"{parsed.scheme.lower()}://" if parsed.scheme else ""
    authority = f"{host}:{port}" if port is not None else host
    suffix = "/…" if parsed.path not in {"", "/"} else ""
    return f"{scheme}{authority}{suffix}"[:200]


def egress_attempts() -> tuple[EgressAttempt, ...]:
    """Bu bağlamda biriken dışa çıkış denemeleri (salt okunur)."""
    return _attempts.get()


def drain_egress_attempts() -> list[dict]:
    """Denemeleri okur ve bağlamı temizler (ajan sınırında çağrılır).

    Dürüstlük: boş dizi "hiç dışarı çıkmadı" demektir; uydurma kayıt yok.
    """
    attempts = _attempts.get()
    _attempts.set(())
    return [a.to_dict() for a in attempts]


def open_client(
    *args: Any,
    purpose: str = "general",
    target: str = "",
    **kwargs: Any,
) -> httpx.AsyncClient:
    """``httpx.AsyncClient`` kurmanın TEK yolu.

    Args:
        *args/**kwargs: ``httpx.AsyncClient``'a aynen aktarılır (testlerin
            globally kurduğu ``AsyncClient`` yamaları aynen çalışır).
        purpose: Çıkışın amacı (``osint``/``search``/``sensor``/``scraper``/
            ``llm``/``media``/``probe``/``general``). Denetim izinde bu alan
            "neden dışarı çıktık" sorusunun cevabıdır.
        target: Hedef kök/URL (izinle kırpılır; sır taşımaz — query/credentials
            atılmaz, yalnız kök ad ya da verilen ham değer).

    Raises:
        VaultLockedError: OSINT amaçlı çıkış ve kasa kapalıysa — istemci
            hiç kurulmaz (fail-closed, iz bırakır).
    """
    if purpose in VAULT_ENFORCED_PURPOSES:
        # Geç import bilinçli: vault_gate dosya/env okur; her genel amaçlı
        # LLM çağrısında bu ağırlık yüklenmesin. Döngü riski yok.
        from agent_core.scraper.vault_gate import VaultLockedError, vault_egress_authorized

        if not vault_egress_authorized(purpose=purpose):
            logger.warning(
                "EGRESS RET (kasa): purpose=%s target=%s — istemci kurulmadı",
                purpose,
                _safe_target(target),
            )
            raise VaultLockedError(f"VAULT_LOCKED purpose={purpose}")

    attempt = EgressAttempt(
        purpose=purpose,
        target=_safe_target(target),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    _attempts.set(_attempts.get() + (attempt,))
    logger.debug("EGRESS open purpose=%s target=%s", purpose, attempt.target[:120])
    return httpx.AsyncClient(*args, **kwargs)


def _reset_for_tests() -> None:  # pragma: no cover — test yardımcısi
    _attempts.set(())
