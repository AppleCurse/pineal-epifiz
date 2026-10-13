"""Canlı kazıyıcı tarayıcısı — kokpit LCD'sinden görülen gerçek Chromium.

Kullanıcı bu tarayıcıda Instagram'a bildiğin giriş yapar (şifre / Google
OAuth / 2FA hepsi serbest; tuşlar doğrudan Instagram'a gider, parola
arka-ucu asla görmez). Giriş bitince `save_session` yalnızca `sessionid`
çerezini oda kasasına yazar; kazıyıcı sonraki işlerde onu kullanır.

Dürüstlük sözleşmesi:
- **KASA MANDALI (Tüzük Md.4):** kasa kilitliyse tarayıcı HİÇBİR dış hareket
  yapamaz; `VaultLockedError` fırlatılır (API 423 Locked'e çevirir). Yalnız
  `close()` muaftır — o bir dış hareket değil, açık kanalı KAPATAN eylemdir;
  reddedilirse arkada canlı Chromium sızar.
- Chromium kurulu değilse BrowserUnavailableError (API 503'e çevirir).
- URL izin listesi dışı adresler reddedilir (kazıyıcı tarayıcısıdır).
- Parola/2FA ASLA okunmaz, loglanmaz, saklanmaz — yalnız sessionid.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

VIEWPORT_W = 800
VIEWPORT_H = 600

ALLOWED_DOMAINS = (
    "instagram.com",
    "www.instagram.com",
    "accounts.google.com",
)

DEFAULT_URL = "https://www.instagram.com/accounts/login/"

PRESS_ALLOWLIST = frozenset({
    "Enter", "Tab", "Escape", "Backspace", "Delete",
    "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
})


class BrowserUnavailableError(RuntimeError):
    """Chromium/playwright bu makinede çalışamıyor."""


class BrowserNotOpenError(RuntimeError):
    """Bu odada açık tarayıcı yok (önce /api/browser/open)."""


# [AUDIT 2026-10-08 · E-GÖZ2-3] Tek kasa-kapısı exception sınıfı: kanonik tanım
# `agent_core.services.vault_gate`'dedir; bu modül onu yeniden dışa aktarır
# (mevcut `from ...browser_session import VaultLockedError` içe aktarımları
# değişmeden çalışmaya devam eder).
from agent_core.services.vault_gate import VaultLockedError  # noqa: F401  # yeniden dışa aktarım


def _domain_ok(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in ALLOWED_DOMAINS


class BrowserSession:
    """Oda başına tek canlı Chromium bağlamı (lazy başlatılır).

    ``vault_guard``: ``True`` dönerse kasa AÇIK. ``None`` ise DAR TARAF
    (kilitli) — yani guard bağlanmamış bir oturum dışarı ÇIKAMAZ. Kararın
    tek sahibi ``backend/api.py::_check_vault_interlock``'tur; bu sınıf kasa
    durumunu asla kendisi uydurmaz, sadece zorlar.
    """

    def __init__(self, vault_guard: Optional[Callable[[], bool]] = None) -> None:
        self._lock = asyncio.Lock()
        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None
        self._vault_guard = vault_guard

    def set_vault_guard(self, vault_guard: Optional[Callable[[], bool]]) -> None:
        """Canlı kasa mandalını bağlar (``True`` = kasa açık)."""
        self._vault_guard = vault_guard

    def _ensure_vault_open(self, action: str) -> None:
        """[KASA MANDALI] Dış hareketten ÖNCE çağrılır; kilitliyse fırlatır."""
        if self._vault_guard is None:
            logger.error(
                "TARAYICI MANDALI BAĞLI DEĞİL: '%s' reddedildi (dar taraf: kasa kilitli sayılır)",
                action,
            )
            raise VaultLockedError(
                f"KASA KİLİTLİ: tarayıcı kasa mandalı bağlanmadan '{action}' yapamaz."
            )
        try:
            unlocked = bool(self._vault_guard())
        except Exception:
            # Sessiz yutma YOK: mandal okunamadıysa bu bir arızadır ve
            # dar tarafa (kilitli) düşülür.
            logger.error(
                "KASA MANDALI OKUNAMADI: '%s' reddedildi (dar taraf: kilitli)",
                action, exc_info=True,
            )
            raise VaultLockedError(
                f"KASA MANDALI OKUNAMADI: '{action}' reddedildi (fail-closed)."
            ) from None
        if not unlocked:
            logger.warning("KASA KİLİTLİ: tarayıcı eylemi '%s' reddedildi", action)
            raise VaultLockedError(
                f"KASA KİLİTLİ: operatör anahtarı çevrilmeden tarayıcı '{action}' yapamaz."
            )

    @property
    def live(self) -> bool:
        return self._page is not None

    async def open(self, url: str = "") -> dict[str, Any]:
        self._ensure_vault_open("open")
        target = (url or DEFAULT_URL).strip() or DEFAULT_URL
        if not _domain_ok(target):
            raise ValueError("URL izin listesi dışı (yalnız Instagram + Google girişi): " + target[:80])
        async with self._lock:
            if self._page is None:
                await self._launch_locked()
            assert self._page is not None
            await self._page.goto(target, wait_until="domcontentloaded", timeout=30_000)
            # [FIX] Açık-yönlendirme (open-redirect) deliği: izin listesi
            # kontrolü yalnızca goto ÖNCESİ url'ye yapılıyordu; bir
            # yönlendirme sayfayı farklı bir kökene taşıyabilirdi ve
            # SON url doğrulanmadan raporlanıyordu. Son url yeniden
            # kontrol edilir; izin listesi dışına taşan reddedilir.
            final_url = self._page.url
            if not _domain_ok(final_url):
                raise ValueError(
                    "Yönlendirme izin listesi dışı kökene ulaştı (reddedildi): "
                    + final_url[:80]
                )
            return {"status": "opened", "url": final_url}

    async def _launch_locked(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            raise BrowserUnavailableError("playwright import edilemedi: " + str(e)[:100])
        try:
            self._pw = await async_playwright().start()
            launch_kw: dict[str, Any] = {
                "headless": True,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            # PINEAL_CHROMIUM_PATH set ise sistem Chromium'u kullanılır
            # (playwright indirmesi olmayan makineler için kaçış kapağı).
            sys_chromium = os.getenv("PINEAL_CHROMIUM_PATH", "").strip()
            if sys_chromium:
                launch_kw["executable_path"] = sys_chromium
            self._browser = await self._pw.chromium.launch(**launch_kw)
            self._ctx = await self._browser.new_context(
                viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = await self._ctx.new_page()
        except Exception as e:
            await self._teardown_locked()
            raise BrowserUnavailableError(
                "Chromium başlatılamadı (`playwright install chromium` ya da PINEAL_CHROMIUM_PATH): "
                + str(e)[:160]
            )

    async def _teardown_locked(self) -> None:
        for attr in ("_page", "_ctx", "_browser"):
            obj = getattr(self, attr)
            if obj is not None:
                try:
                    await obj.close()
                except Exception:
                    # Kapatma sürdürülür (Chromium sızmasın) ama arıza
                    # YUTULMAZ: operatör görmeli.
                    logger.error("TARAYICI KAPANMADI: %s kapatılamadı", attr, exc_info=True)
            setattr(self, attr, None)
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                logger.error("TARAYICI KAPANMADI: playwright durdurulamadı", exc_info=True)
            self._pw = None

    async def _require_page(self):
        if self._page is None:
            raise BrowserNotOpenError("Önce /api/browser/open ile tarayıcıyı açın.")
        return self._page

    async def shot(self) -> bytes:
        self._ensure_vault_open("shot")
        async with self._lock:
            page = await self._require_page()
            return await page.screenshot(type="png")

    async def click(self, x: int, y: int) -> dict[str, Any]:
        self._ensure_vault_open("click")
        x = max(0, min(VIEWPORT_W - 1, int(x)))
        y = max(0, min(VIEWPORT_H - 1, int(y)))
        async with self._lock:
            page = await self._require_page()
            await page.mouse.click(x, y)
            return {"status": "clicked", "x": x, "y": y, "url": page.url}

    async def type_text(self, text: str) -> dict[str, Any]:
        self._ensure_vault_open("type")
        text = (text or "")[:500]
        if not text:
            raise ValueError("Boş metin yazılamaz.")
        async with self._lock:
            page = await self._require_page()
            await page.keyboard.type(text, delay=15)
            return {"status": "typed", "chars": len(text), "url": page.url}

    async def press(self, key: str) -> dict[str, Any]:
        self._ensure_vault_open("press")
        if key not in PRESS_ALLOWLIST:
            raise ValueError("Tuş izin listesi dışı: " + str(key)[:20])
        async with self._lock:
            page = await self._require_page()
            await page.keyboard.press(key)
            return {"status": "pressed", "key": key, "url": page.url}

    async def back(self) -> dict[str, Any]:
        self._ensure_vault_open("back")
        async with self._lock:
            page = await self._require_page()
            await page.go_back(wait_until="domcontentloaded", timeout=15_000)
            return {"status": "back", "url": page.url}

    async def state(self) -> dict[str, Any]:
        self._ensure_vault_open("state")
        async with self._lock:
            if self._page is None:
                return {"live": False, "url": "", "title": ""}
            try:
                title = await self._page.title()
            except Exception as exc:
                # Sessiz boş başlık YOK: arıza loglanır ve UI'ye dürüstçe
                # "okunamadı" taşınır (boş string "başlık yok" gibi görünürdü).
                logger.error("TARAYICI DURUMU: sayfa başlığı okunamadı", exc_info=True)
                title = ""
                return {
                    "live": True,
                    "url": self._page.url,
                    "title": "",
                    "title_error": type(exc).__name__,
                }
            return {"live": True, "url": self._page.url, "title": title[:120]}

    async def session_cookie(self) -> Optional[str]:
        """Varsa instagram sessionid değerini döndürür (parola DEĞİL)."""
        self._ensure_vault_open("save")
        async with self._lock:
            if self._ctx is None:
                return None
            try:
                cookies = await self._ctx.cookies()
            except Exception:
                # "çerez yok" ile "çerez OKUNAMADI" farklı şeylerdir; ikincisi
                # loglanır (sessiz yutma yok).
                logger.error("KASA: tarayıcı çerezleri okunamadı", exc_info=True)
                return None
        for c in cookies:
            if c.get("name") == "sessionid" and (c.get("value") or ""):
                return str(c["value"])
        return None

    async def close(self) -> dict[str, Any]:
        async with self._lock:
            was_live = self._page is not None
            await self._teardown_locked()
            return {"status": "closed" if was_live else "was_not_open"}
