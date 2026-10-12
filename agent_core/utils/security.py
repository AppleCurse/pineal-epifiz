"""Shared production security primitives."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import secrets
import socket
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)


_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.google.internal.",
})
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:or-v1-)?[A-Za-z0-9._-]{8,}\b"),
    re.compile(r"(?i)\b(?:authorization\s*:\s*bearer|bearer)\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)\b(?:sessionid|auth_token|access_token|api[_-]?key|cookie)\s*[=:]\s*[^\s;,]+"),
)

# [AUDIT P2-10] Güvenlik varsayılanı fail-CLOSED'dır: PINEAL_ENV yalnızca
# aşağıdaki açık geliştirme adlarından biriyse kimlik doğrulama kapatılabilir.
# Boş/tanınmayan/yazım-hatalı bir değer ÜRETİM sayılır (bkz. _is_production).
_DEVELOPMENT_ENVIRONMENTS = frozenset({
    "development", "dev", "local", "localhost", "test", "testing", "ci",
})


class UnsafeURLError(ValueError):
    error_code = "SSRF_BLOCKED"

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"{self.error_code}: {reason}")


class SecurityConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.error_code = code
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict:
        return {"status": "failed", "error_code": self.error_code}


@dataclass(frozen=True)
class ResolvedPublicURL:
    original_url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]
    pinned_url: str
    host_header: str


def _environment_name() -> str:
    """PINEAL_ENV'in normalize edilmiş değeri; set edilmemişse boş dize."""
    return os.getenv("PINEAL_ENV", "").strip().lower()


def _is_production() -> bool:
    """[AUDIT P2-10] fail-closed ortam tespiti.

    Eski davranış yalnızca {"production", "prod"} değerlerini üretim sayıyordu;
    PINEAL_ENV unutulduğunda (en olası dağıtım hatası) tüm /api/* ve /v1/*
    kimlik doğrulamasız açılıyordu. Artık yalnızca _DEVELOPMENT_ENVIRONMENTS
    içindeki AÇIK bir değer geliştirme sayılır; boş ya da tanınmayan her değer
    üretim kabul edilir ve PINEAL_TOKEN zorunlu hale gelir.
    """
    return _environment_name() not in _DEVELOPMENT_ENVIRONMENTS


def security_posture() -> dict:
    """Validate auth posture and describe development's explicit open mode."""
    configured_environment = os.getenv("PINEAL_ENV", "").strip()
    environment = "development" if not _is_production() else "production"
    if not configured_environment:
        logger.warning(
            "AUTH_FAIL_CLOSED: PINEAL_ENV set edilmemiş; ortam ÜRETİM varsayıldı. "
            "Yerel geliştirme için PINEAL_ENV=development (veya "
            "PINEAL_REQUIRE_AUTH=false) açıkça ayarlanmalı."
        )
    token = os.getenv("PINEAL_TOKEN", "")
    explicitly_required = os.getenv("PINEAL_REQUIRE_AUTH", "false").strip().lower() == "true"
    required = environment == "production" or explicitly_required
    if required and not token:
        raise SecurityConfigurationError(
            "PRODUCTION_AUTH_REQUIRED" if environment == "production" else "AUTH_TOKEN_REQUIRED",
            "PINEAL_TOKEN must be configured when authentication is required",
        )
    # [AUDIT S1] Production'da harcama tavani ZORUNLU (fail-closed).
    # Cap 0/tanimsiz = SINIRSIZ LLM harcamasi: runtime enforce llm_gateway'de
    # var (spend_cap_usd > 0 kontrolu) ama cap yoksa enforce da yok. Eskiden
    # bu durum /health "SPEND_CAP_UNLIMITED" degraded uyarisiyla KALACAKTI —
    # uyarı yuzeyi bu sinif icin yetersizdir (P2-10 sinifi: production env
    # eksigi -> tehlikeli varsayilan sessizce aktif; auth'ta ayni hata
    # PRODUCTION_AUTH_REQUIRED ile kapatilmisti). Artik: production +
    # cap<=0 -> acilis REDDedilir. Development etkilenmez (kendi hesabiniz).
    if environment == "production":
        try:
            spend_cap = float(os.getenv("OPENROUTER_MAX_SPEND_USD", "0").strip() or "0")
        except (TypeError, ValueError):
            spend_cap = 0.0
        if spend_cap <= 0:
            raise SecurityConfigurationError(
                "PRODUCTION_SPEND_CAP_REQUIRED",
                "OPENROUTER_MAX_SPEND_USD must be a positive value in production "
                "(0 or undefined means UNLIMITED LLM spend; e.g. 50 = $50/session)",
            )
    return {
        "environment": environment,
        "auth_required": required or bool(token),
        "auth_state": "ENFORCED" if required or token else "DISABLED_DEVELOPMENT_ONLY",
        "warning_code": None if required or token else "AUTH_DISABLED_DEVELOPMENT_ONLY",
    }


def token_matches(candidate: Optional[str], expected: Optional[str] = None) -> bool:
    expected = os.getenv("PINEAL_TOKEN", "") if expected is None else expected
    if not candidate or not expected:
        return False
    return secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"INVALID_{field.upper()}")
    return value


def safe_child_path(base: str, filename: str) -> str:
    """Join one filename and prove the result remains below base."""
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("PATH_TRAVERSAL_BLOCKED")
    root = Path(base).resolve()
    candidate = (root / filename).resolve()
    if root not in candidate.parents:
        raise ValueError("PATH_TRAVERSAL_BLOCKED")
    return str(candidate)


def _resolved_addresses(
    hostname: str,
    port: int,
    resolver: Callable[..., Iterable] = socket.getaddrinfo,
) -> tuple[str, ...]:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            records = resolver(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except (socket.gaierror, OSError) as exc:
            raise UnsafeURLError("DNS_RESOLUTION_FAILED") from exc
        addresses = {record[4][0].split("%", 1)[0] for record in records if record[4]}
    else:
        addresses = {hostname.split("%", 1)[0]}

    if not addresses:
        raise UnsafeURLError("DNS_RESOLUTION_FAILED")
    normalized = []
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeURLError("INVALID_DNS_ADDRESS") from exc
        # is_global blocks private, loopback, link-local, multicast,
        # unspecified, reserved, documentation, and metadata ranges.
        if not ip.is_global:
            raise UnsafeURLError("NON_PUBLIC_ADDRESS")
        normalized.append(ip.compressed)
    return tuple(sorted(normalized))


def resolve_public_url(
    url: str,
    *,
    resolver: Callable[..., Iterable] = socket.getaddrinfo,
) -> ResolvedPublicURL:
    """Validate a URL and pin it to a resolved public address."""
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise UnsafeURLError("INVALID_URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("SCHEME_NOT_ALLOWED")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("URL_CREDENTIALS_NOT_ALLOWED")
    if not parsed.hostname:
        raise UnsafeURLError("HOST_REQUIRED")

    hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise UnsafeURLError("BLOCKED_HOSTNAME")
    port = port or (443 if parsed.scheme == "https" else 80)
    addresses = _resolved_addresses(hostname, port, resolver)
    pinned = addresses[0]
    pinned_host = f"[{pinned}]" if ":" in pinned else pinned
    explicit_port = parsed.port is not None
    netloc = f"{pinned_host}:{port}" if explicit_port else pinned_host
    host_header_name = f"[{hostname}]" if ":" in hostname else hostname
    host_header = f"{host_header_name}:{port}" if explicit_port else host_header_name
    pinned_url = urllib.parse.urlunsplit((
        parsed.scheme,
        netloc,
        parsed.path or "/",
        parsed.query,
        "",
    ))
    return ResolvedPublicURL(
        original_url=url,
        hostname=hostname,
        port=port,
        addresses=addresses,
        pinned_url=pinned_url,
        host_header=host_header,
    )


def is_safe_url(url: str) -> bool:
    """Compatibility predicate; DNS failures and non-public answers fail closed."""
    try:
        resolve_public_url(url)
    except (UnsafeURLError, UnicodeError):
        return False
    return True


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    max_redirects: int = 3,
    stream: bool = False,
) -> httpx.Response:
    """GET with DNS pinning and validation of every redirect target."""
    current_url = url
    for redirect_count in range(max_redirects + 1):
        resolved = await asyncio.to_thread(resolve_public_url, current_url)
        request_headers = dict(headers or {})
        request_headers["Host"] = resolved.host_header
        request = client.build_request("GET", resolved.pinned_url, headers=request_headers)
        if request.url.scheme == "https":
            request.extensions["sni_hostname"] = resolved.hostname
        response = await client.send(request, stream=stream)
        if response.status_code not in _REDIRECT_CODES:
            response.extensions["pineal_original_url"] = current_url
            response.extensions["pineal_resolved_addresses"] = resolved.addresses
            return response

        location = response.headers.get("location")
        await response.aclose()
        if not location:
            raise UnsafeURLError("REDIRECT_WITHOUT_LOCATION")
        if redirect_count >= max_redirects:
            raise UnsafeURLError("TOO_MANY_REDIRECTS")
        current_url = urllib.parse.urljoin(current_url, location)
    raise UnsafeURLError("TOO_MANY_REDIRECTS")


@lru_cache(maxsize=1)
def _environment_secret_values() -> tuple[str, ...]:
    markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "COOKIE")
    return tuple(
        value
        for name, value in os.environ.items()
        if value and len(value) >= 6 and any(marker in name.upper() for marker in markers)
    )


# [AUDIT P0-1] Redaksiyon eskiden her metin alanı için (a) tüm os.environ'ı
# yeniden tarıyor ve (b) her sır için ayrı bir str.replace geçişi yapıyordu:
# N metin x M sır. Ölçülen maliyet 900 string'lik tek telemetri gövdesinde
# 67.8 ms, 200 mesajda 13.60 s saf CPU (event loop üzerinde).
# Yeni tasarım:
#   * sır listesi redaksiyon BAŞINA bir kez toplanır, yaprak başına değil
#     (redact_structure özyinelemeye hazır deseni aşağıya taşır),
#   * tüm sırlar + genel kalıplar TEK derlenmiş alternation regex'inde
#     birleşir -> metin başına N+3 geçiş yerine 1 geçiş,
#   * derlenmiş desen sır kümesiyle önbelleğe alınır (sınırlı).
_REDACTOR_CACHE: dict[tuple[str, ...], re.Pattern] = {}
_REDACTOR_CACHE_LIMIT = 8
_GLOBAL_FLAG_PREFIX = re.compile(r"^\(\?([aiLmsx]+)\)")
_FLAG_LETTERS = (
    (re.IGNORECASE, "i"),
    (re.MULTILINE, "m"),
    (re.DOTALL, "s"),
    (re.VERBOSE, "x"),
    (re.ASCII, "a"),
    (re.LOCALE, "L"),
)


def _scoped_pattern_source(pattern: re.Pattern) -> str:
    """Bir deseni, alternation içine GÜVENLE gömülebilir hale getirir.

    Genel (global) satır-içi bayraklar — ör. ``(?i)`` — bir alternation'ın
    ortasında Python 3.11'de ``re.error: global flags not at the start``
    üretir. Bu yüzden bayraklar kapsamlı (scoped) ``(?i:...)`` grubuna
    taşınır; ``flags=`` ile verilmiş bayraklar da aynı biçimde korunur.
    """
    source = pattern.pattern
    letters = ""
    inline = _GLOBAL_FLAG_PREFIX.match(source)
    if inline:
        letters = inline.group(1)
        source = source[inline.end():]
    for flag, letter in _FLAG_LETTERS:
        if pattern.flags & flag and letter not in letters:
            letters += letter
    return f"(?{letters}:{source})" if letters else f"(?:{source})"


def _compile_combined(literals: list[str]):
    parts = literals + [_scoped_pattern_source(p) for p in _SECRET_PATTERNS]
    return re.compile("|".join(parts))


def _redaction_pattern(secrets: tuple[str, ...]) -> re.Pattern:
    cached = _REDACTOR_CACHE.get(secrets)
    if cached is not None:
        return cached
    # En uzun sır önce: str.replace'in "ilk eşleşen kazanır" davranışı korunur.
    literals = [re.escape(item) for item in sorted(
        {item for item in secrets if item}, key=len, reverse=True
    )]
    try:
        compiled = _compile_combined(literals)
    except re.error:  # pragma: no cover - güvenlik ağı
        logger.warning(
            "Birleşik redaksiyon deseni derlenemedi; birebir eşdeğer ayrı geçişlere düşülüyor"
        )
        compiled = _FallbackRedactor(literals)
    if len(_REDACTOR_CACHE) >= _REDACTOR_CACHE_LIMIT:
        _REDACTOR_CACHE.clear()
    _REDACTOR_CACHE[secrets] = compiled
    return compiled


class _FallbackRedactor:
    """Birleşik desen derlenemezse birebir eşdeğer çok-geçişli redaksiyon."""

    __slots__ = ("_literals",)

    def __init__(self, literals: list[str]):
        self._literals = literals

    def sub(self, replacement: str, text: str) -> str:
        for literal in self._literals:
            text = re.sub(literal, replacement, text)
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


def _apply_redaction(text: str, secrets: tuple[str, ...]) -> str:
    return _redaction_pattern(secrets).sub("[REDACTED]", text)


def redact_text(value: object, *, extra_secrets: Iterable[str] = ()) -> str:
    secrets = _environment_secret_values()
    extra = tuple(extra_secrets)
    if extra:
        secrets = secrets + extra
    return _apply_redaction(str(value), secrets)


def _redact_with(value: object, secrets: tuple[str, ...]) -> object:
    """Özyinelemeli yardımcı: sır listesi bir kez toplanır, aşağıya taşınır."""
    if isinstance(value, dict):
        return {key: _redact_with(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_with(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_with(item, secrets) for item in value)
    if isinstance(value, str):
        return _apply_redaction(value, secrets)
    return value


def redact_structure(value: object, *, extra_secrets: Iterable[str] = ()) -> object:
    secrets = _environment_secret_values()
    extra = tuple(extra_secrets)
    if extra:
        secrets = secrets + extra
    return _redact_with(value, secrets)
