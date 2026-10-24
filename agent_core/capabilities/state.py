"""Politika durumunun TEK üretim yeri (Faz A · üretim bağlantısı).

Spine bugüne dek yalnızca testlerden çağrılıyordu: `PolicyState` elle
kuruluyordu. Üretim yolu (backend/api.py → platform_registry) artık durumu
buradan alır. Kural [009]: ikinci bir "env okuyup durum üreten" katman
YARATILMAZ — kapılar `PolicyKernel`'de, durum burada.

[DENETİM 2026-10-14] Kapı ADLARI da tek kaynaktır: `policy.MANAGED_GATE_FLAGS`.
Bu modül onu yalnız yeniden ihraç eder (iki kopya = "adaptörde kapı var,
durumda yok" kusuru; bkz. B1).

Kasıtlı olarak sade tutuldu:
- Hiçbir gizli değer okunmaz, hiçbir anahtar saklanmaz.
- Bilinmeyen/belirsiz değer → dar taraf (vault_locked=True, rate_ok=None).
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any, Mapping

from agent_core.capabilities.policy import MANAGED_GATE_FLAGS, PolicyState

__all__ = [
    "CONSENT_GATED_FLAGS",
    "MANAGED_GATE_FLAGS",
    "enabled_flags",
    "flag_enabled",
    "parse_bool",
    "policy_state",
    "with_operator_consent",
]


#: Spine'in bildiği env kapıları — TEK KAYNAK: ``policy.MANAGED_GATE_FLAGS``.
#: (Denetim 2026-10-14 · B1) Liste burada TUTULMAZ, yalnız yeniden ihraç edilir:
#: iki kopya, ses kapılarının "adaptörde var, durumda yok" hâline yol açmıştı.
#: Burada OLMAYAN bir ``ENABLE_*`` anahtarı geliştirici hatasıdır: ``PolicyKernel``
#: onu ``unknown_gate`` ile reddeder ve denetim izinde görünür (sessizce yok sayılmaz).
#:
#: [DENETİM 2026-10-14 · B2] Bu cümlenin ÖNCEDEN yanlış olduğu ölçüldü: çekirdek
#: ``ENABLE_`` dalını bilinmeyen-kapı denetiminden önce işlediği için uydurma bir
#: bayrak bile ``gate_disabled`` dönüyordu. Sıra artık ``policy.py``'de doğru;
#: ``tests/unit/test_capability_spine_faz0.py`` ikisini de kilitler.
_TRUTHY = frozenset({"1", "true", "yes", "on", "enabled"})


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Env değerini bayrağa çevirir; belirsizlikte `default` (dar taraf)."""
    if value is None:
        return default
    return str(value).strip().lower() in _TRUTHY


#: Operatörün AÇIK onayıyla açılabilen kapılar.
#:
#: [2026-10-23 · ÖLÜ KAPI] Bu iki sensörün bayrağı `.env.example`'da `false`
#: geliyordu; `POST /api/scraper/authorize-alternative` ile "çapraz arama"
#: onayı verilse bile kapı KAPALI kalıyordu — yani onay kablosu yalnız
#: `sensor.identity.handle_probe` için işliyordu, Instagram/X derin taraması
#: varsayılan kurulumda hiç koşmuyordu (ölçüm: `policy:gate_disabled`).
#: Bu liste onayın hangi kapıları açtığının TEK kaynağıdır.
CONSENT_GATED_FLAGS: tuple[str, ...] = (
    "ENABLE_CROSS_PLATFORM",
    "ENABLE_X_SENSOR",
    "ENABLE_IG_SECONDARY",
)


def flag_enabled(flag: str, env: Mapping[str, str] | None = None) -> bool:
    """Tek bir bayrağın AÇIK olup olmadığı — ``parse_bool`` kurallarıyla.

    [GÖLGE DENETİMİ 2026-10-24] Bu yardımcı, "kapıyı okuyan her yer kendi
    kuralını yazsın" kusurunu kapatır. Önceden dört ayrı dosya
    ``os.getenv("ENABLE_INTERPRETER", "false").lower() == "true"`` diyordu;
    bu kural ``1``/``yes``/``on`` değerlerini YOK sayıyordu. Sonuç: operatör
    ``ENABLE_INTERPRETER=1`` yazdığında ``policy_state()`` kapıyı AÇIK
    görürken ajan kapalı davranıyordu (iki farklı gerçek). Artık tek kural var.
    """
    source = os.environ if env is None else env
    return parse_bool(source.get(flag))


def enabled_flags(env: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Yönetilen tüm kapıların anlık durumu (varsayılan: KAPALI).

    Varsayılan kapalı: yeni bir yetenek, operatör açmadan asla koşmaz.
    """
    source = os.environ if env is None else env
    return {flag: parse_bool(source.get(flag)) for flag in MANAGED_GATE_FLAGS}


def with_operator_consent(
    state: PolicyState,
    authorized: bool,
    env: Mapping[str, str] | None = None,
) -> PolicyState:
    """Operatör onayı verildiyse onaya bağlı kapıları açar.

    Sözleşme (dar taraf korunur):
      * ``authorized=False`` → durum DEĞİŞMEZ (onay yoksa hiçbir kapı açılmaz).
      * Kapı env'de AÇIKÇA ``false`` yazılmışsa → yine DEĞİŞMEZ; operatörün
        elle kapattığı bir kapıyı oda onayı ezemez.
      * Env'de hiç yazılmamış (ya da ``true``) → o görev için açılır.
    """
    if not authorized:
        return state
    source = os.environ if env is None else env
    flags = dict(state.enabled_flags)
    for flag in CONSENT_GATED_FLAGS:
        raw = str(source.get(flag, "") or "").strip()
        if raw and not parse_bool(raw):
            continue  # açıkça kapatılmış — onay ezmez
        flags[flag] = True
    return dataclasses.replace(state, enabled_flags=flags)


def policy_state(
    *,
    vault_locked: bool = False,
    rate_ok: bool | None = None,
    budget_usd: float | None = None,
    spent_usd: float = 0.0,
    minor_case: Any | None = None,
    env: Mapping[str, str] | None = None,
) -> PolicyState:
    """Üretim çağrıları için standart `PolicyState`.

    `vault_locked` çağıran taraf verir (kasa interlock'unun tek sahibi
    `backend/api.py::_check_vault_interlock`). `rate_ok=None` bilinçlidir:
    hız durumu BİLİNMİYORSA "rate" kapısı ret verir (fail-closed).
    """
    return PolicyState(
        vault_locked=bool(vault_locked),
        spent_usd=float(spent_usd or 0.0),
        budget_usd=budget_usd,
        rate_ok=rate_ok,
        enabled_flags=enabled_flags(env),
        minor_case=minor_case,
    )
