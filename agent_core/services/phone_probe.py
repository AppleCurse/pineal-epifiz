"""Telefon Numarası OSINT ve Varlık Yoklama Servisi (Phone Probe).

Neden var?
    2026-10-25: Kullanıcının kokpit üzerinden herhangi bir telefon numarasını
    (örn: (552) 956-87-63, 0552..., +90...) girerek:
    1. Ülke, şebeke/operatör, hat türü doğrulaması yapabilmesi,
    2. WhatsApp, Telegram ve benzeri açık mesajlaşma profil linklerini/durumunu görebilmesi,
    3. Numaranın açık web'de bıraktığı dijital ayak izini (ilan, forum, rehber) tarayabilmesi,
    4. Bulunan isim ve kullanıcı adlarını otomatik olarak çapraz sosyal medya
       taramasına (Instagram, TikTok, X vb.) aktarabilmesi ("İşte Bu Da Onun" köprüsü).

Dürüstlük sözleşmesi:
    * Yasa dışı MERNİS/sızıntı veritabanı kullanılmaz; yalnızca meşru OSINT
      ve açık ağ protokolleri konuşur.
    * Şebeke veya platform kesin doğrulanmadıysa 'unknown' veya 'candidate'
      olarak dürüstçe raporlanır.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

__all__ = [
    "PhoneMetadata",
    "MessagingProbe",
    "PhoneProbeResult",
    "probe_phone",
]


class PhoneMetadata(BaseModel):
    raw_input: str
    e164: str = ""
    national_format: str = ""
    international_format: str = ""
    country_code: int = 0
    country_name: str = "Bilinmiyor"
    carrier_name: str = "Bilinmiyor"
    line_type: str = "UNKNOWN"  # MOBILE, FIXED_LINE, VOIP, UNKNOWN
    is_valid: bool = False
    is_possible: bool = False

    model_config = ConfigDict(extra="allow")


class MessagingProbe(BaseModel):
    platform: str
    url: str
    status: str = "candidate"  # candidate, active, absent, unknown
    note: str = ""

    model_config = ConfigDict(extra="allow")


class PhoneProbeResult(BaseModel):
    phone_input: str
    metadata: PhoneMetadata
    messaging_probes: List[MessagingProbe] = Field(default_factory=list)
    web_footprint_hits: List[Dict[str, Any]] = Field(default_factory=list)
    associated_handles: List[str] = Field(default_factory=list)
    social_probes: List[Dict[str, Any]] = Field(default_factory=list)
    summary_report: str = ""
    elapsed_ms: int = 0

    model_config = ConfigDict(extra="allow")


def _clean_digits(s: str) -> str:
    return re.sub(r"[^\d+]", "", s)


def parse_phone_metadata(raw_phone: str, default_region: str = "TR") -> PhoneMetadata:
    """Numarayı E.164 ve uluslararası standartlara göre çözümler."""
    cleaned = _clean_digits(raw_phone)
    if not cleaned:
        return PhoneMetadata(raw_input=raw_phone)

    # Başında + yoksa ve 0 ile başlıyorsa Türkiye için varsayılan düzeltme
    if not cleaned.startswith("+"):
        if cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = "+9" + cleaned
        elif len(cleaned) == 10 and cleaned.startswith("5"):
            cleaned = "+90" + cleaned
        else:
            cleaned = "+" + cleaned

    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder, number_type, PhoneNumberType

        parsed = phonenumbers.parse(cleaned, default_region)
        valid = phonenumbers.is_valid_number(parsed)
        possible = phonenumbers.is_possible_number(parsed)
        e164_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        nat_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
        intl_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

        country = geocoder.description_for_number(parsed, "tr") or geocoder.description_for_number(parsed, "en") or "Bilinmiyor"
        c_name = carrier.name_for_number(parsed, "tr") or carrier.name_for_number(parsed, "en") or "Bilinmiyor"

        nt = number_type(parsed)
        type_map = {
            PhoneNumberType.MOBILE: "MOBILE",
            PhoneNumberType.FIXED_LINE: "FIXED_LINE",
            PhoneNumberType.FIXED_LINE_OR_MOBILE: "MOBILE/FIXED",
            PhoneNumberType.TOLL_FREE: "TOLL_FREE",
            PhoneNumberType.VOIP: "VOIP",
            PhoneNumberType.PERSONAL_NUMBER: "PERSONAL",
            PhoneNumberType.PAGER: "PAGER",
            PhoneNumberType.UAN: "UAN",
            PhoneNumberType.UNKNOWN: "UNKNOWN",
        }
        l_type = type_map.get(nt, "UNKNOWN")

        return PhoneMetadata(
            raw_input=raw_phone,
            e164=e164_str,
            national_format=nat_str,
            international_format=intl_str,
            country_code=parsed.country_code,
            country_name=country,
            carrier_name=c_name,
            line_type=l_type,
            is_valid=valid,
            is_possible=possible,
        )
    except Exception as e:
        logger.warning(f"phonenumbers parse failed for '{raw_phone}': {e}")
        return PhoneMetadata(
            raw_input=raw_phone,
            e164=cleaned,
            national_format=raw_phone,
            international_format=cleaned,
            is_valid=False,
            is_possible=False,
        )


async def _search_web_footprint(query_variants: List[str]) -> List[Dict[str, Any]]:
    """Açık arama motorları üzerinden numaranın web izlerini (dorking) güvenle tarar."""
    hits: List[Dict[str, Any]] = []
    # DuckDuckGo HTML Lite sorgusu
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    primary_query = f'"{query_variants[0]}"' if query_variants else ""
    if not primary_query:
        return hits

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.post(url, data={"q": primary_query}, headers=headers)
            if resp.status_code == 200:
                html = resp.text
                # Basit başlık ve snippet ayıklayıcı
                from re import findall
                raw_results = findall(r'<a class="result__url" href="([^"]+)".*?<a class="result__snippet[^>]*>(.*?)</a>', html)
                for r_url, r_snip in raw_results[:5]:
                    clean_snip = re.sub(r"<[^>]+>", "", r_snip).strip()
                    hits.append({
                        "url": r_url.strip(),
                        "snippet": clean_snip,
                        "engine": "duckduckgo_lite",
                    })
    except Exception as e:
        logger.debug(f"Web footprint search timeout/err: {e}")

    return hits


async def probe_phone(raw_phone: str, auto_bridge_social: bool = True) -> PhoneProbeResult:
    """Telefon numarası üzerinde tam spektrum OSINT ve varlık yoklaması yürütür."""
    t0 = time.time()
    meta = parse_phone_metadata(raw_phone)

    clean_digits = re.sub(r"[^\d]", "", meta.e164) if meta.e164 else re.sub(r"[^\d]", "", raw_phone)
    nat_digits = re.sub(r"[^\d]", "", meta.national_format) if meta.national_format else clean_digits

    # 1. Mesajlaşma Platformları
    messaging_probes: List[MessagingProbe] = []
    if clean_digits:
        # WhatsApp probe link
        messaging_probes.append(MessagingProbe(
            platform="WhatsApp",
            url=f"https://wa.me/{clean_digits}",
            status="candidate",
            note="wa.me doğrudan mesaj ve açık avatar/durum protokolü",
        ))
        # Telegram probe link
        messaging_probes.append(MessagingProbe(
            platform="Telegram",
            url=f"https://t.me/+{clean_digits}",
            status="candidate",
            note="Telegram doğrudan arama ve MTProto kişi profili",
        ))
        # Viber
        messaging_probes.append(MessagingProbe(
            platform="Viber",
            url=f"viber://chat?number=+{clean_digits}",
            status="candidate",
            note="Viber arama şeması",
        ))

    # 2. Açık Web Ayak İzi
    query_variants = []
    if meta.national_format:
        query_variants.append(meta.national_format)
    if meta.e164:
        query_variants.append(meta.e164)
    if nat_digits and nat_digits not in query_variants:
        query_variants.append(nat_digits)

    footprint_hits = await _search_web_footprint(query_variants)

    # 3. İsim ve Kullanıcı Adı Ayıklama
    associated_handles: List[str] = []
    for hit in footprint_hits:
        snip = hit.get("snippet", "") + " " + hit.get("url", "")
        # @handle benzeri kalıplar
        found_handles = re.findall(r"@([a-zA-Z0-9_\.]{3,30})", snip)
        for h in found_handles:
            h_clean = h.strip(".").lower()
            if h_clean not in associated_handles and h_clean not in {"gmail", "yahoo", "hotmail", "outlook", "duckduckgo"}:
                associated_handles.append(h_clean)

    # 4. Otomatik Sosyal Medya Köprüsü (Handle Probe)
    social_probes: List[Dict[str, Any]] = []
    if auto_bridge_social and associated_handles:
        from agent_core.services.handle_probe import probe_handle
        for handle in associated_handles[:2]:
            try:
                h_res = await probe_handle(handle)
                for probe in h_res.probes:
                    if probe.status == "claimed":
                        social_probes.append({
                            "handle": handle,
                            "platform": probe.platform,
                            "url": probe.url,
                            "http_status": probe.http_status,
                        })
            except Exception as e:
                logger.debug(f"Handle probe bridge failed for {handle}: {e}")

    # Özet Rapor Metni
    summary_lines = [
        f"📱 TELEFON OSINT RAPORU: {raw_phone}",
        f"• E.164 Standart Format: {meta.e164 or 'Bilinmiyor'}",
        f"• Ülke & Bölge: {meta.country_name} (+{meta.country_code})",
        f"• Şebeke / Operatör: {meta.carrier_name}",
        f"• Hat Türü: {meta.line_type}",
        f"• Doğruluk Durumu: {'Geçerli GSM Numarası' if meta.is_valid else 'Doğrulanamadı'}",
        f"• Mesajlaşma Kanalları: WhatsApp ({'Hazır' if clean_digits else 'Yok'}), Telegram ({'Hazır' if clean_digits else 'Yok'})",
    ]
    if footprint_hits:
        summary_lines.append(f"• Açık Web İzi: {len(footprint_hits)} adet web kaydı/ilan/forum eşleşmesi bulundu.")
    else:
        summary_lines.append("• Açık Web İzi: Açık arama motorlarında halka açık ilan veya dizin kaydı tespit edilmedi.")

    if associated_handles:
        summary_lines.append(f"• Tespit Edilen Kullanıcı Adları: {', '.join(associated_handles)}")
    if social_probes:
        summary_lines.append(f"• Aktif Sosyal Medya Hesapları: {', '.join([p['platform'] for p in social_probes])}")

    elapsed = int((time.time() - t0) * 1000)

    return PhoneProbeResult(
        phone_input=raw_phone,
        metadata=meta,
        messaging_probes=messaging_probes,
        web_footprint_hits=footprint_hits,
        associated_handles=associated_handles,
        social_probes=social_probes,
        summary_report="\n".join(summary_lines),
        elapsed_ms=elapsed,
    )
