"""Yaprak kasa kapısı (leaf vault gate) — E-GÖZ2-3.

Denetim (2026-10-06, E-GÖZ2-3): kasa kilidi yalnız API sınırında
(``backend/api.py::_require_vault_open``) duruyordu; scraper/OSINT yaprak
katmanı kilit durumunu HİÇ okumuyordu. Yani kapı atlanırsa (yeni bir iç
çağrı yolu, MCP, worker, CLI) ikinci bir savunma yoktu.

Bu modül o ikinci hattır:

* ``agent_core/scraper/run_scraper.py``  — CLI, tarayıcıyı kilitliyken AÇMAZ.
* ``agent_core/services/holehe_scanner.py`` — taramaya girmeden kilit okur.
* ``agent_core/capabilities/egress.py`` — OSINT amaçlı istemciyi kurmaz.

Karar kaynağı (öncelik sırası — tek yer, tek söz):

1. **Bağlam yetkisi**: API sınırı ``_require_vault_open`` kapısından geçtiyse
   aynı istek görevinde ``authorize_vault_egress()`` bağlamı işaretlenir.
   Oda kasası (bellek içi anahtar) bu sayede yaprak katmana akar.
2. **Dosya kasası**: ``.pineal_vault.json`` GERÇEK anahtar/oturum malzemesi
   taşıyorsa açık (dosya VARLIĞI yetki değildir — placeholder anahtar sayılmaz).
3. **Ortam**: ``PINEAL_ENV=production`` ise ve yukarılarındaki yetki yoksa
   **fail-closed: KİLİTLİ**. Geliştirme ortamında kapı (bilinçli) sınır
   katmanına devredilir; asıl zorlama üretimdedir ve testlerle kilitlenir.

Dürüstlük: kilitliyken iş "başarısız gibi görünmez" — ``VaultLockedError``
veya ``available:false + vault_locked`` olarak AÇIKÇA bildirilir.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "VaultLockedError",
    "authorize_vault_egress",
    "get_vault_status",
    "is_locked",
    "mark_vault_egress_authorized",
    "require_open",
    "vault_egress_authorized",
]

#: API sınırının işaretlediği istek-bağlamı yetkisi (None = sınır geçilmedi).
_auth_ctx: ContextVar[Optional[bool]] = ContextVar(
    "pineal_vault_egress_authorized", default=None
)

#: Dosya kasasının yerel adı (backend ile aynı kaynak; env ile yöneltilebilir).
DEFAULT_VAULT_FILE = ".pineal_vault.json"

#: Yer tutucu değerler anahtar DEĞİLDİR (backend/_vault_bears_key_material
#: ile aynı sözleşme): "sk-or-v1-YOUR..." satırı mandalı açamaz.
_PLACEHOLDER_MARKERS = ("your", "changeme", "placeholder", "xxx", "<", "ornek", "örnek")

#: Düz seviyede aranacak anahtar alanları (odada ``or_key`` gibi).
_KEY_FIELDS = ("or_key", "ig_sessionid", "x_cookie", "api_key", "openrouter_api_key")


class VaultLockedError(RuntimeError):
    """Kasa kilitliyken dışa çıkma denemesi — fail-closed, gizli değil."""

    code = "VAULT_LOCKED"


def _is_real_key(value: object) -> bool:
    """Uygulanabilir gerçek anahtar mı? (dosya VARLIĞI yetki değildir.)"""
    if value is True:  # oda kasasında "uygulandı" bayrağı
        return True
    if not isinstance(value, str):
        return False
    raw = value.strip()
    if len(raw) < 8:
        return False
    lowered = raw.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _walk_key_material(node: object) -> bool:
    """Sözlük/liste içinde gerçek anahtar/oturum malzemesi var mı?"""
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in _KEY_FIELDS and _is_real_key(value):
                return True
            if _walk_key_material(value):
                return True
    elif isinstance(node, list):
        return any(_walk_key_material(item) for item in node)
    elif _is_real_key(node):
        return True
    return False


def _file_vault_open(path: Optional[str] = None) -> bool:
    """Dosya kasası GERÇEK anahtar taşıyorsa açık; okunamazsa dar taraf (kilitli)."""
    vault_path = path or os.getenv("PINEAL_VAULT_FILE", DEFAULT_VAULT_FILE)
    try:
        with open(vault_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return False
    except (OSError, json.JSONDecodeError) as exc:
        # Arıza YUTULMAZ: "kilitli" ile "kasa okunamadı" ayırt edilsin diye ERROR.
        logger.error(
            "VAULT_GATE: kasa dosyası okunamadı — dar taraf KİLİTLİ (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return False
    if not isinstance(data, dict):
        logger.error(
            "VAULT_GATE: kasa dosyası JSON nesnesi değil (%s) — dar taraf KİLİTLİ",
            type(data).__name__,
        )
        return False
    return _walk_key_material(data)


def mark_vault_egress_authorized() -> None:
    """API sınırı kapıyı açtığında aynı istek görevini işaretler.

    ``_require_vault_open`` kapıyı ``None`` (açık) döndürürken çağrılır;
    FastAPI her isteği kendi asyncio görevinde çalıştırdığı için işaret
    istek sonunda kaybolur — kalıcı yetki birikmez.
    """
    _auth_ctx.set(True)


@contextmanager
def authorize_vault_egress() -> Iterator[None]:
    """Bloğu kasa- yetkili işaretle (çağıran katmanın görevi)."""
    token = _auth_ctx.set(True)
    try:
        yield
    finally:
        _auth_ctx.reset(token)


def get_vault_status(*, strict: bool = False) -> dict:
    """Kilit kararının TEK okuması (makine-okunur iz ile).

    Args:
        strict: ``True`` → geliştirme "bekleme" (``dev_boundary_deferred``)
            yok sayılır: yalnız sınır yetkisi veya dosya kasası açar
            (CLI/serbest çalışma için Tüzük Md.4'e tam uyum).

    Returns:
        ``{"open": bool, "locked": bool, "source": str, "production": bool}``
        ``source``: ``boundary_context`` · ``file_vault`` ·
        ``dev_boundary_deferred`` · ``production_fail_closed`` ·
        ``strict_no_authorization``
    """
    ctx = _auth_ctx.get()
    production = os.getenv("PINEAL_ENV", "").strip().lower() == "production"
    file_open = _file_vault_open()
    if ctx is not None:
        authorized, source = bool(ctx), "boundary_context"
    elif file_open:
        authorized, source = True, "file_vault"
    elif production:
        authorized, source = False, "production_fail_closed"
    elif strict:
        # CLI/serbest araç: mandal hiç çevrilmediyse dışa çıkış yok.
        authorized, source = False, "strict_no_authorization"
    else:
        # Geliştirme: asıl kapı API sınırındadır; yaprak ikinci hattı
        # üretimde devrededir (belgeli tasarım — testle kilitli).
        authorized, source = True, "dev_boundary_deferred"
    return {
        "open": authorized,
        "locked": not authorized,
        "source": source,
        "production": production,
    }


def vault_egress_authorized(purpose: str = "", *, strict: bool = False) -> bool:
    """Kasa açık mı? (egress/OSINT precheck girişi.)"""
    status = get_vault_status(strict=strict)
    logger.debug(
        "VAULT_GATE okundu purpose=%s open=%s source=%s",
        purpose or "-",
        status["open"],
        status["source"],
    )
    return bool(status["open"])


def is_locked(*, strict: bool = False) -> bool:
    """``vault_egress_authorized()``nin tersi (yaprak katman çağrısı kolaylığı)."""
    return not vault_egress_authorized(strict=strict)


def require_open(purpose: str = "", *, strict: bool = False) -> None:
    """Kilitliyse ``VaultLockedError`` fırlat — sessiz devam YOKTUR."""
    status = get_vault_status(strict=strict)
    if status["open"]:
        return
    logger.warning(
        "VAULT_GATE RET: purpose=%s source=%s — dışa çıkış engellendi",
        purpose or "unspecified",
        status["source"],
    )
    raise VaultLockedError(
        f"VAULT_LOCKED purpose={purpose or 'unspecified'} source={status['source']}"
    )
