"""Holehe entegrasyonu — e-posta kayıt taraması (FAZ 3, deneysel).

Sözleşme (maigret_scanner ile aynı dürüstlük ilkeleri):
- Kapalı / kütüphane yok / timeout / tüm sağlayıcı hatalı: `available=False`
  + makine-okunur sebep. ASLA uydurma site üretmez.
- "Bu e-posta hiçbir sitede kayıtlı değil" yalnızca tarama TAMAMLANIP sıfır
  hata ile sıfır eşleşme çıkarsa iddia edilir (güvenilir yokluk); karışık
  koşulda asla.

ADLİ BULGU (holehe 1.61 kaynak okuması; core.py::launch_module):
`launch_module` modül içi HER istisnayı yakalayıp `rateLimit=True,
exists=False` kaydı yazar. Kapalı ağda bu, tüm modüllerin "kayıtlı değil"
gibi görünmesine yol açar (maigret'teki status=None tuzağının eşdeğeri).
Bu yüzden sınıflandırma kuralı:
  - rateLimit=True            -> HATA (asla temiz yokluk değil)
  - sonucu hiç gelmeyen modül -> HATA
  - tanınmayan kayıt şekli    -> HATA (dürüstlük varsayılanı)
  - exists=True               -> eşleşme
  - exists=False, rateLimit yok -> temiz (yokluk kanıtı sayılabilir)

Lisans notu: holehe GPL-3.0'dır — kodu repo'ya GÖMÜLMEZ; pip bağımlılığı
olarak, varsayılan kapalı deneysel uçla kullanılır.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

DEFAULT_MODULES_LIMIT = 100
DEFAULT_SITE_TIMEOUT = 10
DEFAULT_TOTAL_TIMEOUT = 120
DEFAULT_CONCURRENCY = 20
MAX_MODULES_LIMIT = 300
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_EMAIL_LEN = 254


class HoleheSiteHit(BaseModel):
    site: str
    domain: str
    model_config = ConfigDict(extra="forbid")


class HoleheScanResult(BaseModel):
    requested_email: str
    available: bool = False
    provider: str = "holehe"
    reason: Optional[str] = None
    found_sites: List[HoleheSiteHit] = []
    scanned_count: int = 0
    error_count: int = 0
    model_config = ConfigDict(extra="forbid")


def _env_int(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def is_enabled() -> bool:
    return os.getenv("ENABLE_HOLEHE", "false").lower() == "true"


def sanitize_email(email: str) -> Optional[str]:
    """Boşlukları kırpar; geçerli e-posta değilse None döner."""
    cleaned = (email or "").strip()
    if not cleaned or len(cleaned) > MAX_EMAIL_LEN or not EMAIL_RE.match(cleaned):
        return None
    return cleaned


def _load_modules(limit: int) -> List[Any]:
    """holehe modül ağacından deterministik (isim-sıralı) ilk N kontrol fonksiyonu."""
    import holehe.core as core
    import holehe.modules

    functions = core.get_functions(core.import_submodules(holehe.modules))
    ranked = sorted(functions, key=lambda f: getattr(f, "__name__", ""))
    if not ranked:
        raise RuntimeError("holehe module list empty")
    return ranked[:limit]


async def _run_library_scan(
    email: str,
    functions: Sequence[Any],
    timeout: int,
    concurrency: int,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """holehe'nin kendi launch_module'unu çalıştırır; askıda kalan modülü
    per-modül timeout ile keser ve bunları ayrı hata listesine yazar."""
    from holehe.core import launch_module

    import httpx

    out: List[Dict[str, Any]] = []
    stalled: List[str] = []
    semaphore = asyncio.Semaphore(max(1, concurrency))
    # [SAĞLAMLAŞTIRMA] Tek istemci gather'dan ÖNCE yaratılır: eşzamanlı
    # _runner'ların "client is None" yarışıyla ikinci bir istemci yaratıp
    # sızdırması engellendi (FAZ 3 kusuru; regresyon testi var).
    client = httpx.AsyncClient(timeout=timeout)

    async def _runner(fn: Any) -> None:
        name = getattr(fn, "__name__", "?")
        async with semaphore:
            try:
                await asyncio.wait_for(
                    launch_module(fn, email, client, out), timeout=timeout + 5.0
                )
            except Exception:
                # launch_module istisnaları zaten rateLimit kaydına çevirir;
                # buraya düşen kayıt askıda kalan/iptal edilen modüldür.
                stalled.append(name)

    try:
        await asyncio.gather(*(_runner(fn) for fn in functions))
    finally:
        await client.aclose()
    return out, stalled


def _classify(
    functions: Sequence[Any],
    out: Sequence[Dict[str, Any]],
    stalled: Sequence[str],
) -> Tuple[List[HoleheSiteHit], int, int]:
    """Dürüst sınıflandırma: rateLimit/eksik/bilinmeyen => hata (asla temiz değil)."""
    stalled_set = set(stalled)
    by_name: Dict[str, Dict[str, Any]] = {}
    for rec in out:
        if isinstance(rec, dict) and isinstance(rec.get("name"), str):
            by_name.setdefault(rec["name"], rec)

    found: List[HoleheSiteHit] = []
    scanned = 0
    errors = 0
    for fn in functions:
        name = getattr(fn, "__name__", "?")
        scanned += 1
        rec = by_name.get(name)
        if name in stalled_set or rec is None:
            errors += 1  # hüküm yok — temiz yokluk SAYILMAZ
        elif rec.get("exists") is True:
            found.append(
                HoleheSiteHit(site=name, domain=str(rec.get("domain") or ""))
            )
        elif rec.get("rateLimit"):
            errors += 1  # holehe istisnaları böyle maskelemesi -> HATA
        elif rec.get("exists") is False:
            pass  # temiz: net yokluk yanıtı
        else:
            errors += 1  # tanınmayan şekil -> dürüstlük varsayılanı

    found.sort(key=lambda h: h.site.lower())
    return found, scanned, errors


async def scan_email(
    email: str,
    limit: Optional[int] = None,
    site_timeout: Optional[int] = None,
    modules: Optional[Sequence[Any]] = None,
) -> HoleheScanResult:
    """E-postayı holehe modüllerinde (limit) tarar.

    Dürüst sonuç: kapalıysa 'disabled', kütüphane yoksa 'library_missing',
    zaman aşımında 'timeout', tüm modüller hatalıysa 'provider_errors'.
    `modules` yalnız test/çağıran Overrides içindir (None => gerçek keşif).
    """
    if not is_enabled():
        return HoleheScanResult(requested_email=email, available=False,
                                reason="disabled")

    clean = sanitize_email(email)
    if clean is None:
        return HoleheScanResult(requested_email=email, available=False,
                                reason="invalid_email")

    module_limit = _env_int("HOLEHE_MODULES_LIMIT", DEFAULT_MODULES_LIMIT,
                            MAX_MODULES_LIMIT)
    if limit is not None:
        module_limit = max(1, min(int(limit), MAX_MODULES_LIMIT))
    timeout = site_timeout or _env_int("HOLEHE_TIMEOUT", DEFAULT_SITE_TIMEOUT, 60)
    total_timeout = _env_int("HOLEHE_TOTAL_TIMEOUT", DEFAULT_TOTAL_TIMEOUT, 600)
    concurrency = _env_int("HOLEHE_CONCURRENCY", DEFAULT_CONCURRENCY, 50)

    try:
        if modules is not None:
            functions = list(modules)
        else:
            functions = _load_modules(module_limit)
    except ModuleNotFoundError as exc:
        reason = "library_missing" if exc.name and exc.name.split(".")[0] == "holehe" else "dependency_broken"
        return HoleheScanResult(requested_email=clean, available=False, reason=reason)
    except ImportError as exc:
        logger.error("holehe dependency import failed: %s", type(exc).__name__)
        return HoleheScanResult(requested_email=clean, available=False,
                                reason="dependency_broken")
    except Exception as exc:
        logger.warning("holehe modülleri yüklenemedi: %s: %s",
                       type(exc).__name__, str(exc)[:80])
        return HoleheScanResult(requested_email=clean, available=False,
                                reason="scan_error")

    try:
        out, stalled = await asyncio.wait_for(
            _run_library_scan(clean, functions, timeout, concurrency),
            timeout=total_timeout,
        )
    except asyncio.TimeoutError:
        return HoleheScanResult(requested_email=clean, available=False,
                                reason="timeout", scanned_count=len(functions))
    except ModuleNotFoundError as exc:
        reason = "library_missing" if exc.name and exc.name.split(".")[0] == "holehe" else "dependency_broken"
        return HoleheScanResult(requested_email=clean, available=False,
                                reason=reason, scanned_count=len(functions))
    except ImportError as exc:
        logger.error("holehe dependency import failed: %s", type(exc).__name__)
        return HoleheScanResult(requested_email=clean, available=False,
                                reason="dependency_broken", scanned_count=len(functions))
    except Exception as exc:
        logger.warning("holehe tarama hatası: %s: %s",
                       type(exc).__name__, str(exc)[:80])
        return HoleheScanResult(requested_email=clean, available=False,
                                reason="scan_error", scanned_count=len(functions))

    found, scanned, errors = _classify(functions, out, stalled)

    if found:
        available = True
        reason = "provider_errors_partial" if errors else None
    elif scanned > 0 and errors == 0:
        # Güvenilir yokluk: tüm modüller net yanıt verdi, hiç kayıt yok.
        available = True
        reason = None
    else:
        available = False
        reason = "provider_errors"

    return HoleheScanResult(
        requested_email=clean,
        available=available,
        reason=reason,
        found_sites=found,
        scanned_count=scanned,
        error_count=errors,
    )
