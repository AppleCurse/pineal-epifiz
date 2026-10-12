"""socid-extractor entegrasyonu — profil URL'sinden yapılandırılmış kimlik kaydı.

Sözleşme (projenin dürüstlük ilkeleriyle hizalı):
- Kütüphane kurulu değilse / URL güvensizse / kayıt çıkmadıysa: mümkün olan en
  doğru sonucu döner (`available=False` + makine-okunur sebep). ASLA uydurma
  alan üretmez.
- Tüm ağ erişimi `agent_core.utils.security.is_safe_url` SSRF guard'ından geçer.
- Kayıtlar provenance taşır: provider="socid_extractor".
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class SocidRecord(BaseModel):
    """Tek bir profil URL'sinin çıkarım sonucu (dürüst boş dönebilir)."""
    source_url: str
    available: bool = False
    provider: str = "socid_extractor"
    reason: Optional[str] = None          # unavailable ise sebep
    fields: Dict[str, Any] = {}           # çıkarılan yapılandırılmış alanlar
    model_config = ConfigDict(extra="forbid")


def _call_extract(text: str) -> Dict[str, Any]:
    """socid_extractor.extract'i sürümler arası güvenli çağırır.

    Bazı sürümler dict, bazıları (dict, flags) tuple döner; burada normalize edilir.
    """
    from socid_extractor import extract  # lazy: paket yoksa çağıran dürüst hata alır

    result = extract(text)
    if isinstance(result, tuple):
        for item in result:
            if isinstance(item, dict) and item:
                return item
        return {}
    return result if isinstance(result, dict) else {}


def extract_from_html(html: str, source_url: str = "") -> SocidRecord:
    """Ham HTML metninden kayıt çıkarır (ağsız; test ve pipeline kullanımı için)."""
    try:
        fields = _call_extract(html)
    except ModuleNotFoundError as exc:
        reason = (
            "library_missing"
            if exc.name and exc.name.split(".")[0] == "socid_extractor"
            else "dependency_broken"
        )
        return SocidRecord(source_url=source_url, available=False, reason=reason)
    except ImportError:
        return SocidRecord(source_url=source_url, available=False,
                           reason="dependency_broken")
    except Exception as exc:  # parse hataları dürüstçe raporlanır
        return SocidRecord(source_url=source_url, available=False,
                           reason=f"extract_error:{type(exc).__name__}")
    if not fields:
        return SocidRecord(source_url=source_url, available=False,
                           reason="no_record")
    return SocidRecord(source_url=source_url, available=True, fields=fields)


async def extract_profile(url: str, client: Optional[httpx.AsyncClient] = None) -> SocidRecord:
    """Profil URL'sini indirip yapılandırılmış kimlik kaydına çevirir."""
    if not url or not url.startswith("http"):
        return SocidRecord(source_url=url or "", available=False, reason="invalid_url")

    from agent_core.utils.security import UnsafeURLError, safe_get

    try:
        if client is not None:
            resp = await safe_get(client, url, headers={"User-Agent": USER_AGENT})
        else:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as own:
                resp = await safe_get(own, url, headers={"User-Agent": USER_AGENT})
    except UnsafeURLError:
        return SocidRecord(source_url=url, available=False, reason="ssrf_blocked")
    except Exception:
        return SocidRecord(source_url=url, available=False, reason="network_error")

    if resp.status_code != 200:
        return SocidRecord(source_url=url, available=False, reason=f"http_{resp.status_code}")

    return extract_from_html(resp.text, source_url=url)


async def enrich_urls(urls, limit: int = 3):
    """Verilen URL listesinin ilk `limit` tanesini zenginleştirir (paralel).

    Dönen listede yalnız `available=True` kayıtlar bulunur; hatalar sessizce
    yutulmaz — çağıran isterse `extract_profile` ile tekil sebep alabilir.
    """
    import asyncio

    targets = [u for u in (urls or []) if isinstance(u, str)][:limit]
    if not targets:
        return []
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
        records = await asyncio.gather(*(extract_profile(u, client=client) for u in targets))
    return [r for r in records if r.available]
