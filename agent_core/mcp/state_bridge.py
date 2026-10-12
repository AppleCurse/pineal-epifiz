"""FAZ D · D1 — MCP için durum köprüsü: kasa gerçeği + giriş kontrolü.

İki kural, ikisi de tavizsiz:

1. **Kasa tek kaynaktan okunur.** Kasa mandalının sahibi Pineal API'sidir
   (``_check_vault_interlock`` → ``/api/vault/status``). MCP sunucusu bu kararı
   KENDİ kopyasında yeniden üretmez (kural [009]: ikinci kaynak yok); yalnız
   çalışan API'ye sorar ve cevabı AYNEN kullanır.
2. **Okunamıyorsa kilitlidir (fail-closed).** API kapalıysa, adres yerel
   değilse ya da cevap anlaşılmıyorsa ``vault_locked=True`` kabul edilir:
   "bilmiyorum" asla "açık" sayılmaz. Sebep makine-okunurdur ve çağırana
   aynen gösterilir.

Yerellik: API adresi yalnız ``127.0.0.1`` / ``localhost`` / ``[::1]`` olabilir
(ses, dinleme ve çevirideki kuralın aynısı). Uzak adres REDDEDİLİR — hedef
verisi ve kasa durumu makineden çıkmaz. Yönlendirmeler de kapatılmıştır:
yerel bir uç, okuma isteğini uzak bir adrese YÖNLENDİREMEZ.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Mapping

from agent_core.capabilities.policy import PolicyState
from agent_core.capabilities.state import enabled_flags

__all__ = [
    "LOCAL_API_HOSTS",
    "DEFAULT_API_URL",
    "api_base_url",
    "vault_state",
    "clear_vault_cache",
    "SlidingWindowLimiter",
    "limiter_from_env",
    "minor_case_for",
    "policy_state_for_call",
    "status_snapshot",
]

LOCAL_API_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"})

DEFAULT_API_URL = "http://127.0.0.1:8000"

#: Kasa cevabı önbelleği: her araç çağrısında API'ye gidilmez, ama bayat
#: cevapla da uzun süre koşulmaz (varsayılan 5 sn).
_VAULT_CACHE_SECONDS = 5.0
_vault_cache: dict[str, tuple[float, bool, str]] = {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Yönlendirmeyi reddeder: yerel uç uzak adrese yönlendirip veri çıkaramaz."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise urllib.error.HTTPError(req.full_url, code, "yönlendirme reddedildi", headers, fp)


_opener = urllib.request.build_opener(_NoRedirect)


def api_base_url(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """(taban adres, '') ya da ('', sebep): yalnız YEREL API adresi kabul edilir."""
    source = os.environ if env is None else env
    raw = (source.get("PINEAL_API_URL") or DEFAULT_API_URL).strip().rstrip("/")
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in LOCAL_API_HOSTS:
        return "", "non_local_api_url"
    if parsed.scheme not in {"http", "https"}:
        return "", "bad_api_scheme"
    return raw, ""


def vault_state(
    client_id: str = "default",
    *,
    timeout: float = 2.0,
    env: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    """(locked, sebep). Kasa durumu API'den okunur; okunamazsa KİLİTLİ sayılır."""
    base, reason = api_base_url(env)
    if not base:
        return True, reason

    source = os.environ if env is None else env
    room = (source.get("PINEAL_MCP_CLIENT_ID") or client_id or "default").strip() or "default"
    key = f"{base}|{room}"
    now = time.monotonic()
    cached = _vault_cache.get(key)
    if cached and now - cached[0] < _VAULT_CACHE_SECONDS:
        return cached[1], cached[2]

    query = urllib.parse.urlencode({"client_id": room})
    url = f"{base}/api/vault/status?{query}"
    try:
        with _opener.open(url, timeout=timeout) as response:
            body = response.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return True, f"vault_api_status:{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return True, f"vault_api_unreachable:{type(exc).__name__}"
    try:
        payload = json.loads(body)
    except ValueError:
        return True, "vault_api_bad_json"
    if not isinstance(payload, dict) or not isinstance(payload.get("locked"), bool):
        # Cevap şekli sözleşmeye uymuyorsa "açık" SAYILMAZ (sessiz varsayım yok).
        return True, "vault_api_bad_shape"

    locked = bool(payload["locked"])
    _vault_cache[key] = (now, locked, "")
    if len(_vault_cache) > 64:  # sınırsız büyüme yok
        for stale in sorted(_vault_cache, key=lambda k: _vault_cache[k][0])[: len(_vault_cache) - 64]:
            _vault_cache.pop(stale, None)
    return locked, ""


def clear_vault_cache() -> None:
    """Testler için: önbelleği boşaltır (üretimde çağrılmaz)."""
    _vault_cache.clear()


class SlidingWindowLimiter:
    """Araç başına kayan pencere hız sınırı (API'deki kova ile aynı şekil).

    Neden MCP sunucusunda kendi sınırı var: sunucu, API'nin HTTP katmanının
    dışında AYRI bir giriş kapısıdır; API'nin hız kovası bu isteği görmez.
    Sınır ``PolicyKernel``'in ``rate`` kapısına verilir — kararı yine çekirdek
    verir, bu sınıf yalnız durumu üretir.
    """

    def __init__(self, limit: int = 20, window_seconds: float = 60.0) -> None:
        self.limit = max(1, int(limit))
        self.window = max(0.1, float(window_seconds))
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str, *, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        events = self._events.setdefault(key, deque())
        while events and moment - events[0] > self.window:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(moment)
        return True


def limiter_from_env(env: Mapping[str, str] | None = None) -> SlidingWindowLimiter:
    """Env'den sınır kurar; bozuk/eksik değerde GÜVENLİ varsayılana düşer."""
    source = os.environ if env is None else env
    try:
        limit = int((source.get("PINEAL_MCP_RATE_LIMIT") or "20").strip())
    except ValueError:
        limit = 20
    try:
        window = float((source.get("PINEAL_MCP_RATE_WINDOW") or "60").strip())
    except ValueError:
        window = 60.0
    return SlidingWindowLimiter(limit=limit, window_seconds=window)


def policy_state_for_call(
    *,
    vault_locked: bool,
    rate_ok: bool,
    minor_case: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> PolicyState:
    """Tek çağrı için politika durumu (kapı bayrakları tek kaynaktan: ``state.py``)."""
    return PolicyState(
        vault_locked=bool(vault_locked),
        rate_ok=bool(rate_ok),
        enabled_flags=enabled_flags(env),
        minor_case=minor_case,
    )


def minor_case_for(subject: str, env: Mapping[str, str] | None = None):
    """Operatör beyanı: ``PINEAL_MCP_MINOR_SUBJECTS`` içindeki hedef 18 altıdır.

    Neden env: yaş sinyali araç çağrısının içinde YOKTUR ve MCP katmanı yaş
    UYDURMAZ. Operatör bir hedefin çocuk olduğunu beyan ederse o hedef MCP
    yolunda kilitlenir: vaka bağlamı (aile bilgisi, doğrulama, konsorsiyum
    onayı) taşınmadığı için ``MinorGate`` REDDEDER — yani beyan, "izin" değil
    "dur" demektir. Tam vaka yalnız normal operatör akışından açılabilir.
    """
    source = os.environ if env is None else env
    raw = (source.get("PINEAL_MCP_MINOR_SUBJECTS") or "").strip()
    if not raw or not subject:
        return None
    needles = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if subject.strip().lower() not in needles:
        return None
    from agent_core.safety.minor_gate import MinorCaseContext

    return MinorCaseContext(subject_is_minor=True)


def status_snapshot(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Dürüst durum özeti (kokpit + ``pineal_status`` aracı aynı gerçeği okur)."""
    source = os.environ if env is None else env
    base, reason = api_base_url(source)
    locked, vault_reason = vault_state(env=source)
    return {
        "api_url": base or None,
        "api_reason": reason or None,
        "vault_locked": locked,
        "vault_reason": vault_reason or None,
        "client_id": (source.get("PINEAL_MCP_CLIENT_ID") or "default"),
    }
