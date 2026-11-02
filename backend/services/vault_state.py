"""Pure vault key classification helpers shared by API gates.

These helpers inspect key material but never log or expose it.
"""

_PLACEHOLDER_KEY_PREFIXES: tuple = ("sk-or-v1-YOUR",)
_PLACEHOLDER_KEY_MARKERS: tuple = (
    "YOUR_", "YOUR-", "YOUR ", "_YOUR",
    "PLACEHOLDER", "EXAMPLE", "CHANGE_ME", "CHANGEME",
    "REPLACE_ME", "REPLACEME", "INSERT_", "SAMPLE_KEY",
)

def _is_placeholder_key(value: object) -> bool:
    """Placeholder/örnek anahtar metni mi? (fail-closed sınıflandırıcı)"""
    if not isinstance(value, str):
        return True
    text = value.strip()
    if not text:
        return True
    for prefix in _PLACEHOLDER_KEY_PREFIXES:
        if text.startswith(prefix):
            return True
    upper = text.upper()
    return any(marker in upper for marker in _PLACEHOLDER_KEY_MARKERS)


def _is_real_key(value: object) -> bool:
    """Gerçek sır malzemesi mi? Boş + placeholder reddedilir."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not _is_placeholder_key(value)
    )


def _cookie_pool_has_key(value: object) -> bool:
    """Çok satırlı cookie havuzunda en az bir gerçek satır var mı?"""
    if not isinstance(value, str):
        return False
    lines = [line for line in value.splitlines() if line.strip()]
    if not lines:
        return _is_real_key(value)
    return any(_is_real_key(line) for line in lines)


def _room_vault_unlocked(vault: dict) -> bool:
    """Oda kasası açık mı? Bayraklar YALNIZCA gerçek malzemeyle kurulur
    (`get_room` + `/api/vault` aynı kapıdan geçer), bu yüzden bayraklar
    güvenilirdir. `/api/vault/lock` bayrakları temizler -> kilitli."""
    if not isinstance(vault, dict):
        return False
    if vault.get("or_key") is True:
        return True
    if vault.get("provider_keys_set"):
        return True
    if vault.get("search_keys") is True:
        return True
    if _is_real_key(vault.get("ig_sessionid")):
        return True
    return _cookie_pool_has_key(vault.get("x_cookie"))
