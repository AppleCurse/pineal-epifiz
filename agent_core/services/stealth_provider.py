"""STEALTH_PROVIDER seçici — playwright_stealth | invisible | cloak | none (FAZ 5).

Sözleşme (projenin dürüstlük ilkeleriyle hizalı):
- `STEALTH_PROVIDER` unset/boş => `playwright_stealth` (MEVCUT davranış;
  scrape_instagram bugün de try-import playwright_stealth + apply yapar).
- Geçersiz değer => asla sessiz değişim: efektif sağlayıcı default'a döner,
  `reason="invalid_provider:<ham>"` ile makine-okunur kayıt.
- Sağlayıcı kullanılamıyorsa `available=False` + makine-okunur sebep
  (library_missing / binary_missing); çağıran dürüstçe stealthsiz devam eder
  (bugünkü import-başarısız davranışıyla aynı) ve nedeni loglar.
- AĞIR BINARY İNDİRME runtime request yolunda ASLA tetiklenmez:
  invisible/cloak yalnızca operatorün env ile gösterdiği binary yolu varsa
  available olur (invisible launcher'ı `binary_path=` ile indirmeyi atlar;
  cloak Chromium fork'u `executable_path=` ile drop-in'dir).
- invisible LAUNCH-level sağlayıcıdır (patched Firefox + kendi async_playwright
  modülü); page-bazlı `apply_stealth_async` ona uygulanamaz — dürüst
  `launch_level_provider` döner.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Tuple

from pydantic import BaseModel, ConfigDict

DEFAULT_PROVIDER = "playwright_stealth"
VALID_PROVIDERS = ("playwright_stealth", "invisible", "cloak", "none")

INVISIBLE_BINARY_ENV = "INVISIBLE_BROWSER_BINARY"
CLOAK_BINARY_ENV = "CLOAK_BROWSER_EXECUTABLE"


class StealthSelection(BaseModel):
    requested: str                       # env'deki ham değer (normalize öncesi)
    provider: str                        # efektif sağlayıcı
    available: bool = False
    reason: Optional[str] = None         # unavailable ise makine-okunur sebep
    kind: str = "page"                   # page | launch | none
    model_config = ConfigDict(extra="forbid")


def _lib_present(name: str) -> bool:
    # Tek kaynak: `optional_deps.module_available` (noktalı ad + ValueError dahil).
    from agent_core.utils.optional_deps import module_available

    return module_available(name)


def _env_binary_path(env: Any, name: str) -> Optional[Path]:
    raw = (env.get(name) or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def resolve_stealth(override: Optional[str] = None, env: Any = None) -> StealthSelection:
    """STEALTH_PROVIDER'ı çözümler. `override` (ör. uç sorgu parametresi)
    verilirse env yerine o geçerli olur; env yoksa os.environ kullanılır."""
    env = os.environ if env is None else env
    raw_value = override if override is not None else env.get("STEALTH_PROVIDER")
    requested = (raw_value or "").strip()
    normalized = requested.lower()

    if not normalized:
        normalized = DEFAULT_PROVIDER
        requested = DEFAULT_PROVIDER
    if normalized not in VALID_PROVIDERS:
        return StealthSelection(
            requested=requested,
            provider=DEFAULT_PROVIDER,
            available=_lib_present("playwright_stealth"),
            reason=f"invalid_provider:{requested[:40]}",
        )

    if normalized == "none":
        return StealthSelection(requested=requested, provider="none",
                                available=True, reason=None, kind="none")

    if normalized == "playwright_stealth":
        available = _lib_present("playwright_stealth")
        return StealthSelection(requested=requested, provider=normalized,
                                available=available,
                                reason=None if available else "library_missing",
                                kind="page")

    if normalized == "invisible":
        if not _lib_present("invisible_playwright"):
            return StealthSelection(requested=requested, provider=normalized,
                                    available=False, reason="library_missing",
                                    kind="launch")
        # Dürüst varlık yoklaması: indirme YOK. Launcher `binary_path=`
        # kabul eder (indirmeyi atlar); binary yoksa deploy'da
        # `invisible-playwright ensure-binary` opsiyoneldir.
        if _env_binary_path(env, INVISIBLE_BINARY_ENV) is None:
            return StealthSelection(requested=requested, provider=normalized,
                                    available=False, reason="binary_missing",
                                    kind="launch")
        return StealthSelection(requested=requested, provider=normalized,
                                available=True, reason=None, kind="launch")

    # cloak: Chromium fork binary (pip paketi değil) — yalnız operator path'i.
    if _env_binary_path(env, CLOAK_BINARY_ENV) is None:
        return StealthSelection(requested=requested, provider="cloak",
                                available=False, reason="binary_missing",
                                kind="launch")
    return StealthSelection(requested=requested, provider="cloak",
                            available=True, reason=None, kind="launch")


async def apply_page_stealth(
    selection: StealthSelection, page: Any
) -> Tuple[bool, Optional[str]]:
    """Page-bazlı stealth uygular. Döner: (uygulandı mı, sebep-notu).

    launch-level sağlayıcılar için dürüstçe `(False, 'launch_level_provider')`
    — onlar tarayıcı başlatma katmanında devreye girer (bkz. platform_registry).
    """
    if not selection.available:
        return False, selection.reason
    if selection.provider == "none":
        return True, None
    if selection.provider == "playwright_stealth":
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)
            return True, None
        except Exception as exc:
            return False, f"apply_error:{type(exc).__name__}"
    return False, "launch_level_provider"


def use_invisible_module(selection: StealthSelection) -> bool:
    """Tarayıcı başlatımı invisible_playwright'in kendi async_playwright
    modülüyle mi yapılmalı (patched Firefox)?"""
    return selection.provider == "invisible" and selection.available


def browser_kind(selection: StealthSelection) -> str:
    """Başlatılacak tarayıcı: invisible => firefox (patched), diğerleri chromium."""
    return "firefox" if use_invisible_module(selection) else "chromium"


def launch_overrides(selection: StealthSelection, env: Any = None) -> dict:
    """p.<browser>.launch(...) kwargs'e eklenecek sağlayıcı-özel argümanlar.
    invisible kendi modülü üzerinden binary'yi çözer (override YOK);
    cloak `executable_path=` ile drop-in'dir."""
    env = os.environ if env is None else env
    if selection.provider == "cloak" and selection.available:
        path = _env_binary_path(env, CLOAK_BINARY_ENV)
        if path is not None:
            return {"executable_path": str(path)}
    return {}
