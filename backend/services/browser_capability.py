"""Tarayıcı ikilisi (Chromium) ölçümü — tek kaynak.

Neden var (ölçülen kusur, 2026-11-11):
    Playwright Python paketi kurulu ama **tarayıcı ikilisi yokken**
    (`~/.cache/ms-playwright/...` boş) Instagram kazıması üç kez deneniyor,
    her denemede `BrowserType.launch: Executable doesn't exist` alınıyor ve
    görev "kazıma altyapısı denemeleri tüketti" ile ölüyordu. Operatöre
    söylenen tek şey buydu; NE yapacağı söylenmiyordu ve durum `/health`
    içinde hiç görünmüyordu. Yani ürün çalışamayacağını baştan bilebilirdi.

Bu modül üç soruyu TEK yerde yanıtlar:
    1. Tarayıcı çalıştırılabilir mi? (`browser_binary_status`)
    2. Çalışmıyorsa NE yapmalı? (`remediation_hint`)
    3. Bu, görevi baştan durdurmayı gerektirir mi? (`is_fatal_infrastructure_failure`)

Tasarım kuralları:
    - Yol YALNIZ sabit adaylardan okunur; keyfî komut çalıştırılmaz.
    - Ölçüm her çağrıda dosya sistemi kontrolü yapar (ucuz); sonucu çağıran
      isterse önbelleğe alır (`/api/telemetry` 300 sn TTL kullanır).
    - Hiçbir şey uydurulmaz: ikili yoksa `available=False` + makine-okunur
      `reason` döner.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Optional

__all__ = [
    "BrowserBinaryStatus",
    "browser_binary_status",
    "is_fatal_infrastructure_failure",
    "remediation_hint",
    "BROWSER_MISSING_REASON",
]

#: Makine-okunur sebep kodu (telemetri/health/UI aynı dizeyi kullanır).
BROWSER_MISSING_REASON = "browser_binary_missing"

#: `playwright install chromium` çıktısının düştüğü kök (PLAYWRIGHT_BROWSERS_PATH
#: ile değiştirilebilir; Playwright bu değişkeni kendisi de okur).
_DEFAULT_BROWSERS_ROOT = "~/.cache/ms-playwright"

#: Chromium'u taşıyan bilinen ikili adları (headless shell dâhil).
_BINARY_NAMES = (
    "chrome",
    "chrome-linux64/chrome",
    "chrome-linux/chrome",
    "chrome-headless-shell-linux64/chrome-headless-shell",
    "headless_shell",
)


@dataclass(frozen=True)
class BrowserBinaryStatus:
    """Tarayıcı ikilisinin ölçülmüş durumu (uydurma yok)."""

    available: bool
    source: str
    path: Optional[str] = None
    reason: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def _env_browsers_root() -> str:
    return (
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
        or os.environ.get("PINEAL_PLAYWRIGHT_BROWSERS_PATH", "").strip()
        or _DEFAULT_BROWSERS_ROOT
    )


def _pinned_chromium() -> str:
    """Operatörün açıkça sabitlediği Chromium yolu (deploy ortamı)."""
    return (
        os.environ.get("PINEAL_CHROMIUM_PATH", "").strip()
        or os.environ.get("CHROME_PATH", "").strip()
    )


def _scan_playwright_cache(root: str) -> Optional[str]:
    """`ms-playwright/chromium-*/...` altındaki ikiliyi bul (sabit adlar)."""
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return None
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    for entry in entries:
        if not entry.startswith("chromium"):
            continue
        for name in _BINARY_NAMES:
            candidate = os.path.join(root, entry, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def browser_binary_status() -> BrowserBinaryStatus:
    """Chromium çalıştırılabilir mi? Sonuç her zaman kanıta dayanır."""
    pinned = _pinned_chromium()
    if pinned:
        if os.path.isfile(pinned) and os.access(pinned, os.X_OK):
            return BrowserBinaryStatus(available=True, source="pinned", path=pinned)
        # Açıkça sabitlenmiş ama yok: bu bir YAPILANDIRMA hatasıdır, sessizce
        # "ikili yok"a düşmek operatörü yanıltır — sebebi ayrı raporlanır.
        return BrowserBinaryStatus(
            available=False,
            source="pinned",
            path=pinned,
            reason="pinned_browser_path_missing",
        )

    root = _env_browsers_root()
    found = _scan_playwright_cache(root)
    if found:
        return BrowserBinaryStatus(available=True, source="playwright_cache", path=found)

    # [ÖLÇÜM] Playwright sürücüsüne SORMAK yerine sabit adaylar tarandı: sürücü
    # çağrısı süreç açar (ölçüldü: telemetri ucunda pahalı) ve bu fonksiyon
    # senkron bağlamdan da çağrılabilsin istiyoruz.
    return BrowserBinaryStatus(
        available=False,
        source="playwright_cache",
        path=None,
        reason=BROWSER_MISSING_REASON,
    )


def remediation_hint(status: Optional[BrowserBinaryStatus] = None) -> str:
    """Operatörün UYGULAYABİLECEĞİ tek cümlelik düzeltme yolu."""
    status = status or browser_binary_status()
    if status.available:
        return ""
    if status.reason == "pinned_browser_path_missing":
        return (
            f"PINEAL_CHROMIUM_PATH/CHROME_PATH tanımlı ama dosya yok: {status.path}. "
            "Yolu düzeltin veya değişkeni kaldırın."
        )
    return (
        "Chromium ikilisi yok. Kurulum: `python -m playwright install chromium` "
        "(çevrimdışı ortamda) veya çalışan bir Chromium'u PINEAL_CHROMIUM_PATH ile "
        "sabitleyin. Bu ikili olmadan Instagram/X kazıması çalışmaz."
    )


#: Altyapı arızası olarak sayılan hata imzaları. Bunlar KİŞİYE ÖZEL değildir
#: (gizli hesap, boş profil vb. değil); tüm kazıma yolunu kapatan sistem
#: arızalarıdır ve tekrar denemek sonucu değiştirmez.
_INFRA_FAILURE_SIGNATURES = (
    "executable doesn't exist",
    "executable doesn’t exist",
    "browserType.launch",
    "browser_type.launch",
    "failed to launch browser",
    "playwright install",
)


def is_fatal_infrastructure_failure(error: BaseException | str) -> bool:
    """Hata yeniden denemeyle düzelmeyecek bir ALTYAPI arızası mı?

    Doğruysa çağıran taraf yeniden denemeyi bırakmalı: üç kez 5 sn beklemek
    operatöre yalnızca gecikme yaşatır (ölçüldü: 3 deneme ~7 sn).
    """
    text = str(error).lower()
    if any(sig.lower() in text for sig in _INFRA_FAILURE_SIGNATURES):
        return True
    name = type(error).__name__.lower() if not isinstance(error, str) else ""
    return name in {"browsertypelaunch", "error"} and "browser" in text
