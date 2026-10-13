"""FAZ D · D6 — KURUM HEDEFİ: şirket/kurum/alan adı hedefleme.

Üç ayak, üçü de KANIT üretir:

    theHarvester    → e-posta · alt alan adı · IP · URL (arama motorlarından;
                      araç yoksa `dependency_missing:theHarvester`).
    açık SEO        → robots.txt · sitemap.xml · meta başlık/açıklama · dil ·
                      canonical · security.txt · güvenlik başlıkları. Kurumun
                      KENDİ yayınladığı dosyalar ölçülür; harici SEO servisi
                      yoktur ve **SEO "puanı" hesaplanmaz** (uydurma metrik
                      üretilmez — ölçülen yazılır).
    çalışan listesi → yalnız KURUMUN KENDİ sayfalarındaki YAPILANDIRILMIŞ kişi
                      verisi (schema.org/Person: ad + rol) ve herkese açık
                      iletişim adresleri (mailto). Bu bir kişi avı değildir:
                      ad/rol dışında hiçbir kişisel alan toplanmaz, profilleme
                      yapılmaz; kaynak URL her satırda görünür.

Dürüstlük sözleşmesi (ev kuralları, değişmedi):
    * Araç/servis yok → `available=False` + makine-okunur sebep.
    * "Yok" iddiası YALNIZ sunucu kesin 404 dediğinde (`absence`); ağ hatası
      yokluğa çevrilmez.
    * Özel/yerel adresler (SSRF hijyeni) varsayılan olarak REDDEDİLİR;
      yalnız operatör açıkça `PINEAL_COMPANY_ALLOW_PRIVATE=1` derse geçer.
    * Tüm fonksiyonlar yapılandırmayı YALNIZ `os.environ`'dan okur (tek
      kaynak kuralı — [2026-10-07] iki-env-kaynağı dersinin dördüncü tekrarı
      olmasın).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import asyncio
import json
import os
import re
import shlex
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from agent_core.services import net_hygiene

__all__ = [
    "GATE",
    "HarvesterScan",
    "SeoCheck",
    "SeoSnapshot",
    "PersonRow",
    "PeopleScan",
    "normalize_domain",
    "harvester_command",
    "harvester_availability",
    "scan_company",
    "seo_snapshot",
    "people_scan",
]

#: Kapı adı (state.py MANAGED_GATE_FLAGS ile aynı olmak zorunda).
GATE = "ENABLE_COMPANY_TARGETING"

HARVESTER_TIMEOUT = 240.0
HTTP_TIMEOUT = 20.0
MAX_TEXT = 400

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")

#: theHarvester çıktı kovaları: kanonik ad → olası anahtar adları.
_BUCKETS: dict[str, tuple[str, ...]] = {
    "emails": ("emails", "email"),
    "hosts": ("hosts", "host"),
    "ips": ("ips", "ip"),
    "urls": ("urls", "interesting_urls", "trello_urls"),
    "people": ("linkedin_people", "twitter_people", "people"),
}

#: "Çalışan sayfası" adayı URL deseni (kurumun kendi sitesi).
_TEAM_PAGE_RE = re.compile(
    r"(team|about|people|staff|company|contact|ekip|kadro|hakkimizda|hakkinda|iletisim|kurumsal)",
    re.IGNORECASE,
)


# ------------------------------------------------------------------ alan adı
def normalize_domain(value: str) -> str:
    """Girdiyi çıplak alan adına indirger; geçersizse ``""`` (asla tahmin yok).

    ``https://www.Örnek.com/yol?x=1`` → ``örnek.com`` (IDN küçük harfe iner;
    punycode'a çevirme çağıranın işi değil — biz yalnız ASCII güvenli alanı
    kabul ederiz, punycode zaten ASCII'dir).
    """
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in text:  # eposta verildiyse alan adı kısmı
        text = text.rsplit("@", 1)[1]
    if text.endswith("."):
        text = text[:-1]
    if text.startswith("www."):
        text = text[4:]
    if ":" in text:  # port (IPv6 bu yetenekte desteklenmez — kurum hedefi)
        text = text.split(":", 1)[0]
    return text if _DOMAIN_RE.match(text) else ""


#: SSRF kapısının bu aileye özel istisna anahtarı (tek kaynak: net_hygiene).
PRIVATE_ALLOW_ENV = "PINEAL_COMPANY_ALLOW_PRIVATE"


def _is_private_target(domain: str) -> bool:
    """Hedef özel/yerel ağa mı çözülüyor? (SSRF hijyeni — fail-closed)."""
    return net_hygiene.is_private_host(domain, env_name=PRIVATE_ALLOW_ENV)


# ---------------------------------------------------------------- theHarvester
def harvester_command() -> list[str]:
    """theHarvester komutu: önce ``PINEAL_HARVESTER_CMD``, sonra PATH.

    Dönen komut GERÇEKTEN çalıştırılabilir olmalı: env'de yazılı ama PATH'te
    (ya da mutlak yolda) bulunmayan bir komut "var" sayılmaz — aksi hâlde
    koşu başlar ve ham ``FileNotFoundError`` ile düşerdi (dürüst ret yerine).
    """
    raw = os.getenv("PINEAL_HARVESTER_CMD", "").strip()
    if raw:
        try:
            parts = shlex.split(raw)
        except ValueError:
            return []  # bozuk tırnak: sessizce PATH'e düşmeyiz, araç yok sayılır
        if not parts:
            return []
        head = parts[0]
        if os.path.isabs(head) or "/" in head or "\\" in head:
            return parts if os.path.exists(head) else []
        return parts if shutil.which(head) else []
    for name in ("theHarvester", "theharvester"):
        found = shutil.which(name)
        if found:
            return [found]
    return []


def harvester_availability() -> tuple[bool, str]:
    if harvester_command():
        return True, ""
    if os.getenv("PINEAL_HARVESTER_CMD", "").strip():
        # Operatörün verdiği komut bulunamadı: "araç kurulu değil" demek
        # yanıltıcı olurdu — asıl sorun yapılandırmada.
        return False, "configured_command_not_found:PINEAL_HARVESTER_CMD"
    return False, "dependency_missing:theHarvester"


@dataclass
class HarvesterScan:
    available: bool
    reason: str = ""
    domain: str = ""
    emails: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    ips: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    people: tuple[str, ...] = ()
    sources: str = ""
    duration_ms: int = 0
    stderr_tail: str = ""
    keys_seen: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.emails) + len(self.hosts) + len(self.ips) + len(self.urls) + len(self.people)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_as_str_list(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(_as_str_list(item))
        return out
    return [str(value)]


def _buckets_from_mapping(mapping: dict[str, Any]) -> dict[str, list[str]]:
    flat: dict[str, list[str]] = {name: [] for name in _BUCKETS}
    for key, value in mapping.items():
        low = str(key).strip().lower()
        for bucket, aliases in _BUCKETS.items():
            if low in aliases:
                flat[bucket].extend(_as_str_list(value))
    return {name: sorted({v.strip() for v in vals if str(v).strip()}) for name, vals in flat.items()}


def _read_harvester_output(prefix: str) -> tuple[dict[str, Any] | None, str]:
    """theHarvester çıktısını okur: önce JSON, sonra XML. Ham sözlük döner."""
    json_path = prefix + ".json"
    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8", errors="replace") as handle:
                data = json.load(handle)
        except Exception:
            return None, "parse_error"
        if isinstance(data, dict):
            return data, ""
        return None, "parse_error"

    xml_path = prefix + ".xml"
    if os.path.exists(xml_path):
        try:
            root = ET.parse(xml_path).getroot()
        except Exception:
            return None, "parse_error"
        merged: dict[str, list[str]] = {}
        for element in root.iter():
            tag = str(element.tag).strip().lower()
            text = (element.text or "").strip()
            if text:
                merged.setdefault(tag, []).append(text)
            for child in list(element):
                child_text = (child.text or "").strip()
                if child_text:
                    merged.setdefault(tag, []).append(child_text)
        return merged, ""

    return None, "output_missing"


async def scan_company(
    domain: str,
    *,
    sources: str = "",
    limit: int = 200,
    timeout: float = HARVESTER_TIMEOUT,
) -> HarvesterScan:
    """theHarvester'ı koşar ve çıktısını dürüstçe ayrıştırır."""
    clean = normalize_domain(domain)
    if not clean:
        return HarvesterScan(available=False, reason="invalid_domain")
    if _is_private_target(clean):
        return HarvesterScan(available=False, reason="private_address_rejected")
    command = harvester_command()
    if not command:
        # Sebep TEK yerden gelir: yapılandırma hatası ile eksik araç ayrılır.
        _ok, reason = harvester_availability()
        return HarvesterScan(available=False, reason=reason or "dependency_missing:theHarvester")

    src = (sources or os.getenv("PINEAL_HARVESTER_SOURCES", "duckduckgo,crtsh,bing")).strip()
    try:
        limit_n = max(1, min(int(limit or 0), 1000))
    except (TypeError, ValueError):
        limit_n = 200

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="pineal-harvester-") as tmp:
        prefix = os.path.join(tmp, "out")
        argv = [*command, "-d", clean, "-b", src, "-l", str(limit_n), "-f", prefix]
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            _ok, reason = harvester_availability()
            return HarvesterScan(available=False, reason=reason or "dependency_missing:theHarvester")
        except Exception as exc:
            return HarvesterScan(
                available=False, reason=f"harvester_failed:{type(exc).__name__}"
            )

        stderr_bytes = b""
        try:
            _stdout, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception as exc:
                logger.warning(
                    "[scan_company] beklenmeyen hata (Exception) yutulmadı — iz bırakıldı: %s", exc, exc_info=True
                )
            return HarvesterScan(
                available=False, reason="timeout", domain=clean, sources=src,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        stderr_tail = (stderr_bytes or b"").decode("utf-8", errors="replace")[-MAX_TEXT:].strip()
        data, parse_reason = _read_harvester_output(prefix)

    if data is None:
        return HarvesterScan(
            available=False,
            reason=parse_reason or "output_missing",
            domain=clean,
            sources=src,
            duration_ms=duration_ms,
            stderr_tail=stderr_tail,
        )

    buckets = _buckets_from_mapping(data)
    return HarvesterScan(
        available=True,
        reason="",
        domain=clean,
        emails=tuple(buckets["emails"]),
        hosts=tuple(buckets["hosts"]),
        ips=tuple(buckets["ips"]),
        urls=tuple(buckets["urls"]),
        people=tuple(buckets["people"]),
        sources=src,
        duration_ms=duration_ms,
        stderr_tail=stderr_tail,
        keys_seen=tuple(sorted(str(k) for k in data.keys())),
    )


# ------------------------------------------------------------------ açık SEO
@dataclass
class SeoCheck:
    """Tek ölçüm: URL + HTTP durumu + ölçülen alanlar (uydurma yok)."""

    name: str
    url: str
    status: int = 0
    present: bool = False
    detail: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def absent(self) -> bool:
        """Kesin yokluk: sunucu 404 dedi (ağ hatası yokluğa çevrilmez)."""
        return self.status == 404


@dataclass
class SeoSnapshot:
    available: bool
    reason: str = ""
    domain: str = ""
    base_url: str = ""
    checks: tuple[SeoCheck, ...] = ()
    scheme: str = ""


async def _fetch(client: Any, url: str) -> tuple[int, str, dict[str, str], str]:
    """(status, text, headers, error) — ağ hatası durumda status=0."""
    try:
        response = await client.get(url)
        return response.status_code, response.text or "", dict(response.headers), ""
    except Exception as exc:
        return 0, "", {}, type(exc).__name__


def _parse_robots(text: str) -> dict[str, Any]:
    sitemaps: list[str] = []
    disallow_all = False
    crawl_delay = ""
    current_agent = ""
    for raw_line in text.splitlines()[:500]:
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current_agent = value.lower()
        elif key == "sitemap" and value:
            sitemaps.append(value)
        elif key == "crawl-delay" and value and not crawl_delay:
            crawl_delay = value
        elif key == "disallow" and value == "/" and current_agent in {"*", ""}:
            disallow_all = True
    return {
        "sitemaps": sorted(set(sitemaps))[:10],
        "disallow_all": disallow_all,
        "crawl_delay": crawl_delay,
        "lines": len(text.splitlines()),
    }


def _parse_sitemap(text: str) -> dict[str, Any]:
    locations = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text, flags=re.IGNORECASE)
    lastmods = re.findall(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", text, flags=re.IGNORECASE)
    is_index = "<sitemapindex" in text
    return {
        "kind": "index" if is_index else "urlset",
        "entries": len(locations),
        "first_lastmod": lastmods[0] if lastmods else "",
        "locations": locations[:50],
    }


def _parse_homepage(text: str) -> dict[str, Any]:
    def _meta(pattern: str) -> str:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        return (match.group(1).strip() if match else "")[:MAX_TEXT]

    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    return {
        "title": (title_match.group(1).strip() if title_match else "")[:MAX_TEXT],
        "description": _meta(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)'),
        "og_title": _meta(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)'),
        "canonical": _meta(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)'),
        "lang": _meta(r'<html[^>]+lang=["\']([^"\']*)'),
        "bytes": len(text),
    }


async def seo_snapshot(
    domain: str,
    *,
    base_url: str = "",
    timeout: float = HTTP_TIMEOUT,
) -> SeoSnapshot:
    """Kurumun KENDİ yayınladığı SEO/izlenebilirlik verisini ölçer."""
    clean = normalize_domain(domain)
    if not clean:
        return SeoSnapshot(available=False, reason="invalid_domain")
    if not base_url and _is_private_target(clean):
        return SeoSnapshot(available=False, reason="private_address_rejected")

    try:
        import httpx
    except ImportError:
        return SeoSnapshot(available=False, reason="dependency_missing:httpx")

    checks: list[SeoCheck] = []
    scheme = ""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        base = (base_url or "").rstrip("/")
        if base:
            candidates = [base]
        else:
            candidates = [f"https://{clean}", f"http://{clean}"]

        for candidate in candidates:
            status, text, headers, error = await _fetch(client, candidate + "/")
            if status and 200 <= status < 400:
                scheme = candidate.split("://", 1)[0]
                detail = _parse_homepage(text)
                detail["server"] = headers.get("server", "")[:120]
                detail["hsts"] = headers.get("strict-transport-security", "")[:120]
                detail["csp"] = bool(headers.get("content-security-policy", ""))
                checks.append(SeoCheck("homepage", candidate + "/", status, True, detail))
                base = candidate
                break
            checks.append(
                SeoCheck("homepage", candidate + "/", status, False, {}, error or f"status:{status}")
            )

        if not scheme:
            return SeoSnapshot(
                available=False, reason="unreachable", domain=clean, checks=tuple(checks)
            )

        # robots.txt
        robots_url = base + "/robots.txt"
        status, text, _headers, error = await _fetch(client, robots_url)
        robots_detail: dict[str, Any] = {}
        if status == 200:
            robots_detail = _parse_robots(text)
            robots_detail["chars"] = len(text)
            checks.append(SeoCheck("robots", robots_url, status, True, robots_detail))
        else:
            checks.append(SeoCheck("robots", robots_url, status, False, {}, error or f"status:{status}"))

        # sitemap.xml (robots'ta işaret edilen ilk sitemap, yoksa kök)
        sitemap_url = ""
        if robots_detail.get("sitemaps"):
            sitemap_url = str(robots_detail["sitemaps"][0])
        sitemap_url = sitemap_url or (base + "/sitemap.xml")
        status, text, _headers, error = await _fetch(client, sitemap_url)
        if status == 200:
            checks.append(SeoCheck("sitemap", sitemap_url, status, True, _parse_sitemap(text)))
        else:
            checks.append(SeoCheck("sitemap", sitemap_url, status, False, {}, error or f"status:{status}"))

        # security.txt
        sec_url = base + "/.well-known/security.txt"
        status, text, _headers, error = await _fetch(client, sec_url)
        if status == 200:
            contacts = re.findall(r"(?im)^contact:\s*(.+)$", text)
            checks.append(
                SeoCheck(
                    "security_txt",
                    sec_url,
                    status,
                    True,
                    {"contacts": [c.strip()[:200] for c in contacts[:5]], "chars": len(text)},
                )
            )
        else:
            checks.append(SeoCheck("security_txt", sec_url, status, False, {}, error or f"status:{status}"))

    return SeoSnapshot(
        available=True,
        reason="",
        domain=clean,
        base_url=base,
        scheme=scheme,
        checks=tuple(checks),
    )


# ------------------------------------------------------- çalışan/kişi sinyali
@dataclass
class PersonRow:
    name: str
    role: str
    page: str


@dataclass
class PeopleScan:
    available: bool
    reason: str = ""
    domain: str = ""
    pages_checked: tuple[str, ...] = ()
    people: tuple[PersonRow, ...] = ()
    contacts: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class _SignalsParser(HTMLParser):
    """Yalnız iki sinyal toplar: JSON-LD blokları ve mailto bağlantıları."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_ld = False
        self._ld_parts: list[str] = []
        self.json_ld: list[str] = []
        self.mails: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script" and "ld+json" in attr.get("type", "").lower():
            self._in_ld = True
            self._ld_parts = []
        if tag == "a":
            href = attr.get("href", "")
            if href.lower().startswith("mailto:"):
                addr = href[7:].split("?", 1)[0].strip()
                if addr:
                    self.mails.append(addr)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self._in_ld = False
            block = "".join(self._ld_parts).strip()
            if block:
                self.json_ld.append(block)

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_parts.append(data)


def _people_from_json_ld(blocks: list[str], page: str) -> list[PersonRow]:
    rows: list[PersonRow] = []

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        node_type = node.get("@type", "")
        types = [node_type] if isinstance(node_type, str) else list(node_type or [])
        if any(str(t).lower() == "person" for t in types):
            name = str(node.get("name", "")).strip()[:200]
            role = str(node.get("jobTitle", "") or node.get("description", "")).strip()[:200]
            if name:
                rows.append(PersonRow(name=name, role=role, page=page))
        for value in node.values():
            if isinstance(value, (dict, list)):
                _walk(value)

    for block in blocks:
        try:
            payload = json.loads(block)
        except Exception:
            continue  # bozuk JSON-LD: sessizce atlanır, kişi UYDURULMAZ
        _walk(payload)
    return rows


async def people_scan(
    domain: str,
    *,
    base_url: str = "",
    max_pages: int = 5,
    timeout: float = HTTP_TIMEOUT,
) -> PeopleScan:
    """Kurumun kendi sayfalarındaki YAPILANDIRILMIŞ kişi verisini toplar."""
    clean = normalize_domain(domain)
    if not clean:
        return PeopleScan(available=False, reason="invalid_domain")
    if not base_url and _is_private_target(clean):
        return PeopleScan(available=False, reason="private_address_rejected")

    try:
        import httpx
    except ImportError:
        return PeopleScan(available=False, reason="dependency_missing:httpx")

    snapshot = await seo_snapshot(clean, base_url=base_url, timeout=timeout)
    if not snapshot.available and snapshot.reason:
        return PeopleScan(available=False, reason=snapshot.reason, domain=clean)
    base = snapshot.base_url or (base_url or f"https://{clean}").rstrip("/")

    candidates: list[str] = [base + "/"]
    for check in snapshot.checks:
        if check.name == "sitemap" and check.present:
            for location in check.detail.get("locations", []):
                if _TEAM_PAGE_RE.search(str(location)) and location not in candidates:
                    candidates.append(str(location))
    if len(candidates) == 1:
        for suffix in ("/team", "/about", "/contact", "/ekip", "/hakkimizda"):
            candidates.append(base + suffix)
    pages = candidates[: max(1, min(int(max_pages or 5), 10))]

    people: list[PersonRow] = []
    contacts: list[str] = []
    errors: list[str] = []
    checked: list[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for page in pages:
            status, text, _headers, error = await _fetch(client, page)
            if status and 200 <= status < 400:
                checked.append(page)
                parser = _SignalsParser()
                try:
                    parser.feed(text)
                except Exception:
                    errors.append(f"parse_error:{page}")
                    continue
                people.extend(_people_from_json_ld(parser.json_ld, page))
                contacts.extend(parser.mails)
            else:
                errors.append(f"{error or f'status:{status}'}:{page}")

    # Aynı kişi birden çok sayfada görünürse tek satır kalır (ilk kaynak tutulur).
    seen: set[str] = set()
    unique_people: list[PersonRow] = []
    for row in people:
        key = row.name.lower()
        if key not in seen:
            seen.add(key)
            unique_people.append(row)

    if not checked:
        return PeopleScan(
            available=False,
            reason="unreachable",
            domain=clean,
            errors=tuple(errors[:10]),
        )

    return PeopleScan(
        available=True,
        reason="",
        domain=clean,
        pages_checked=tuple(checked),
        people=tuple(unique_people[:50]),
        contacts=tuple(sorted({c for c in contacts if c})[:20]),
        errors=tuple(errors[:10]),
    )
