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

import os
from typing import Any, Mapping

from agent_core.capabilities.policy import MANAGED_GATE_FLAGS, PolicyState

__all__ = [
    "MANAGED_GATE_FLAGS",
    "enabled_flags",
    "parse_bool",
    "policy_state",
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


def enabled_flags(env: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Yönetilen tüm kapıların anlık durumu (varsayılan: KAPALI).

    Varsayılan kapalı: yeni bir yetenek, operatör açmadan asla koşmaz.
    """
    source = os.environ if env is None else env
    return {flag: parse_bool(source.get(flag)) for flag in MANAGED_GATE_FLAGS}


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
