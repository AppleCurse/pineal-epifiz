"""YAPRAK katman kasa kapısı — Tüzük Md.4'ün ikinci savunması.

API sınırı (``backend/api.py``: ``_check_vault_interlock`` +
``_require_vault_open``) birinci kapıdır. Bu modül, yaprak servislerin
(scraper / OSINT) KENDİ egress anında kasayı yeniden denetlemesini sağlar:
sınır atlanırsa (yeni bir iç çağrı yolu, MCP, worker) yaprakta ikinci savunma
hâlâ durur. [AUDIT 2026-10-08 · E-GÖZ2-3]

Durum kaynağı, öncelik sırasıyla:

  1. Açıkça verilen karar (``unlocked=``) — API sınırı kasa mandalını
     değerlendirdiği anda yaprak çağrısına BU parametreyle aktarır
     (oda-bazlı, istemci-bazlı karar — tek sahibi API sınırıdır).
  2. Süreç-içi override (``mark_vault_unlocked``) — API sınırı interlock
     değerlendirdiğinde yazar (executor ile aynı süreçte koşar). Not: bu
     katman kompensatiftir; istemci-odası kesinliği açık parametrededir.
  3. Diskteki ``.pineal_vault.json`` GERÇEK anahtar malzemesi taşır. Dosya
     VARLIĞI yetki değildir; içerik denetlenir (bkz. RÖNTGEN 2026-09-23).
  4. Aksi hâlde KİLİTLİ (fail-closed).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "VaultLockedError",
    "get_vault_status",
    "mark_vault_unlocked",
    "require_vault_open",
]

#: Kasa dosyası — API sınırı ile AYNI dosya (tek kasa, tek kaynak).
VAULT_FILE = os.getenv("PINEAL_VAULT_FILE", ".pineal_vault.json")

#: Yer tutucu sayılacak işaretler — "anahtar var" iddiası gerçek malzeme ister.
_PLACEHOLDER_MARKERS = (
    "placeholder", "changeme", "change-me", "todo", "dummy", "example", "xxxx",
)

#: Üst seviye alanlar — bu alanlardan biri gerçek değer taşırsa kasa açık.
_VAULT_KEY_FIELDS = (
    "api_key", "or_key", "ig_sessionid", "x_cookie",
    "tavily_key", "serpapi_key", "exa_key",
)


class VaultLockedError(RuntimeError):
    """[KASA MANDALI] Kasa kilitli: yaprak servis dışarı çıkamaz (Tüzük Md.4)."""


#: Süreç-içi override: None = bilinmiyor (dosyaya bak), True/False = karar.
_override: Optional[bool] = None


def mark_vault_unlocked(unlocked: Optional[bool]) -> None:
    """API sınırı kasa kararını süreç içinde yapraklara bildirir.

    ``None`` ile çağrılırsa override temizlenir (bir sonraki sorguda dosya
    kasasına düşülür). Kararın TEK sahibi API sınırındaki interlock'tur;
    bu fonksiyon sadece o kararın yapraklara taşınmasıdır.
    """
    global _override
    _override = None if unlocked is None else bool(unlocked)


def _is_real_secret(value: Any) -> bool:
    """Değer gerçek anahtar/oturum malzemesi mi (yer tutucu değil mi)?"""
    if value is True:
        # Oda kasasında "uygulandı" bayrağı (or_key=True vb.).
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) < 8:
        return False
    lowered = text.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _entry_bears_key_material(entry: Any) -> bool:
    if isinstance(entry, dict):
        return any(
            _is_real_secret(entry.get(key))
            for key in ("api_key", "primary_api_key", "backup_api_key")
        )
    return _is_real_secret(entry)


def file_vault_bears_key_material(vault: Any) -> bool:
    """Kasa dict'i GERÇEK anahtar/oturum malzemesi taşıyor mu?

    Kural, API sınırındaki ``_vault_bears_key_material`` ile aynıdır:
    providers/provider_keys içinde uygulanabilir anahtar VEYA üst seviye
    gerçek bir alan. Boş dosya / yer tutucular YETMEZ.
    """
    if not isinstance(vault, dict) or not vault:
        return False
    for section in ("providers", "provider_keys"):
        entries = vault.get(section)
        if isinstance(entries, dict) and any(
            _entry_bears_key_material(entry) for entry in entries.values()
        ):
            return True
    return any(_is_real_secret(vault.get(field)) for field in _VAULT_KEY_FIELDS)


def get_vault_status() -> dict:
    """Kasa durumu: ``{"locked": bool, "source": str}``.

    ``source``: bu fonksiyon override ve dosya kaynaklarını rapor eder:
    ``override`` | ``file_vault`` | ``default_locked``.
    """
    if _override is not None:
        return {"locked": not _override, "source": "override"}
    try:
        with open(VAULT_FILE, encoding="utf-8") as handle:
            vault = json.load(handle)
    except FileNotFoundError:
        return {"locked": True, "source": "default_locked"}
    except Exception as exc:
        # Okunamayan kasa dosyası = dar taraf (kilitli); arıza LOGLANIR —
        # sessizce açık varsaymak fail-open olurdu.
        logger.warning(
            "vault_gate: kasa dosyası okunamadı (%s), kilitli sayıldı: %s",
            VAULT_FILE, exc,
        )
        return {"locked": True, "source": "default_locked"}
    if file_vault_bears_key_material(vault):
        return {"locked": False, "source": "file_vault"}
    return {"locked": True, "source": "default_locked"}


def require_vault_open(source: str, *, unlocked: Optional[bool] = None) -> dict:
    """Dış egress'ten ÖNCE çağrılır; kilitliyse ``VaultLockedError`` fırlatır.

    ``unlocked`` açıkça verilmişse (API sınırının oda-bazlı kararı) o karar
    kullanılır; ``None`` ise override → dosya kasası sırasıyla bakılır.
    Dönüş: kasa durum dict'i (çağıran loglamak isterse).
    """
    if unlocked is None:
        status = get_vault_status()
    else:
        status = {"locked": not bool(unlocked), "source": "caller"}
    if status["locked"]:
        logger.warning(
            "KASA KİLİTLİ: '%s' dış egress reddedildi (Tüzük Md.4, kaynak=%s)",
            source, status["source"],
        )
        raise VaultLockedError(
            f"KASA KİLİTLİ: operatör anahtarı çevrilmeden '{source}' dışarı çıkamaz."
        )
    return status
