"""Tarayıcı ikilisi yokken kazımanın TAMAMEN düşmesi (P1, 2026-11-11).

Ölçülen kusur (düzeltme ÖNCESİ, gerçek kurulumda):
    Playwright paketi kurulu, Chromium ikilisi YOK. Instagram kazıması
    ``PINEAL_SCRAPE_MAX_ATTEMPTS`` (varsayılan 3) kez denendi, her denemede
    ``BrowserType.launch: Executable doesn't exist`` alındı, ~7 sn boşa
    beklendi ve operatöre yalnızca "kazıma altyapısı denemeleri tüketti"
    dendi. ``/health`` bu durumu HİÇ göstermiyordu.

Düzeltme sonrası sözleşme:
    1. Denemeden önce gerçek ölçüm: ikili yoksa TEK deneme, ret mesajı
       kurulum komutunu içerir (``KAZIMA ALTYAPISI KULLANILAMIYOR: ...``).
    2. Kalıcı altyapı arızası görülürse yeniden deneme KESİLİR (bekleme yok).
    3. Kişiye özel kanıt yetersizliği (gizli hesap) altyapı arızası SAYILMAZ;
       mevcut dürüst davranış korunur.
    4. ``/health`` ikili yokken ``degraded`` + ``browser_binary_missing`` der.

Testler DAVRANIŞI ölçer: kazıma fonksiyonu çağrı sayısı, uyku çağrı sayısı,
ret metni ve gerçek ``browser_binary_status()`` ölçümü üzerinden.
"""

from __future__ import annotations


import pytest

from backend.services.browser_capability import (
    BROWSER_MISSING_REASON,
    BrowserBinaryStatus,
    browser_binary_status,
    is_fatal_infrastructure_failure,
    remediation_hint,
)
from backend.services.scrape_dispatch import (
    EVIDENCE_REJECT_MESSAGE,
    INSTAGRAM_REJECT_PREFIX,
    run_scrape_attempts,
)


class _Log:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def __call__(self, level: str, message: str) -> None:
        self.lines.append((level, message))

    @property
    def text(self) -> str:
        return "\n".join(m for _, m in self.lines)


class _Sleep:
    """Gerçek bekleme YOK; kaç kez bekleneceğini sayar."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float):
        self.calls.append(seconds)


# --------------------------------------------------------------- 1 · ölçüm
def test_browser_status_is_measured_not_guessed():
    """Ölçüm gerçek dosya sisteminden gelir; ikili yoksa makine-okunur sebep."""
    state = browser_binary_status()
    assert state.reason in {
        "",
        BROWSER_MISSING_REASON,
        "pinned_browser_path_missing",
    }, f"beklenmeyen sebep kodu: {state.reason!r}"
    if state.available:
        assert state.reason == ""
    else:
        assert state.reason, "ikili yoksa sebep kodu BOŞ olamaz (sessiz ret yasak)"
        # Mesaj operatöre NE YAPACAĞINI söyler — bu, düzeltmenin ölçülebilir kısmı.
        hint = remediation_hint(state)
        assert "playwright install" in hint
        assert "python" in hint


def test_fatal_infrastructure_failure_classification():
    """Gerçek Playwright hatası altyapı arızası; gizli hesap DEĞİL."""
    launch_error = RuntimeError(
        "BrowserType.launch: Executable doesn't exist at "
        "/root/.cache/ms-playwright/chromium_headless_shell-1254/chrome-linux/headless_shell"
    )
    assert is_fatal_infrastructure_failure(launch_error) is True
    assert is_fatal_infrastructure_failure(RuntimeError("private account")) is False


# ------------------------------------------------- 2 · ikili yokken tek deneme
@pytest.mark.asyncio
async def test_missing_binary_makes_one_attempt_and_tells_operator(monkeypatch):
    """Kusurun tam kalbi: ikili yokken ÜÇ deneme değil TEK deneme + komut."""
    calls: list[str] = []

    async def scrape(url, cookie, log=None):
        calls.append(url)
        raise AssertionError("tarayıcı ikilisi yokken kazıma HİÇ çağrılmamalı")

    monkeypatch.setattr(
        "backend.services.scrape_dispatch.browser_binary_status",
        lambda: BrowserBinaryStatus(
            available=False, source="playwright_cache", reason=BROWSER_MISSING_REASON
        ),
    )
    sleep = _Sleep()
    log = _Log()
    result = await run_scrape_attempts(
        url="https://www.instagram.com/hedef/",
        cookie="",
        max_attempts=3,
        scrape=scrape,
        log=log,
        sleep=sleep,
    )

    assert calls == [], "preflight başarısızken kazıma çağrılmamalı"
    assert result.attempts == 1, f"tek deneme bekleniyordu, {result.attempts} denendi"
    assert sleep.calls == [], "altyapı yokken BEKLENMEZ (boşa 7 sn harcanmaz)"
    assert result.infrastructure_failure is True
    message = result.reject_message()
    assert message.startswith(INSTAGRAM_REJECT_PREFIX)
    assert "playwright install" in message, "ret mesajı kurulum komutunu içermeli"


@pytest.mark.asyncio
async def test_retry_is_cut_when_infrastructure_failure_is_permanent(monkeypatch):
    """Preflight geçse bile kalıcı arıza görülürse İKİNCİ deneme yapılmaz."""
    attempts: list[int] = []

    async def scrape(url, cookie, log=None):
        attempts.append(1)
        raise RuntimeError("BrowserType.launch: Executable doesn't exist")

    class _Available:
        available = True
        reason = ""
        source = "pinned"
        path = "/usr/bin/chromium"

    monkeypatch.setattr(
        "backend.services.scrape_dispatch.browser_binary_status", lambda: _Available()
    )
    sleep = _Sleep()
    result = await run_scrape_attempts(
        url="https://www.instagram.com/hedef/",
        cookie="",
        max_attempts=3,
        scrape=scrape,
        log=_Log(),
        sleep=sleep,
    )
    assert len(attempts) == 1, f"kalıcı arızada 1 deneme bekleniyordu, {len(attempts)}"
    assert sleep.calls == []
    assert result.infrastructure_failure is True


@pytest.mark.asyncio
async def test_transient_failure_still_retries_until_max(monkeypatch):
    """Geçici hata (altyapı arızası DEĞİL) eskisi gibi denenir — davranış korunur."""
    attempts: list[int] = []

    async def scrape(url, cookie, log=None):
        attempts.append(1)
        raise TimeoutError("sayfa zaman aşımı")

    class _Available:
        available = True
        reason = ""
        source = "pinned"
        path = "/usr/bin/chromium"

    monkeypatch.setattr(
        "backend.services.scrape_dispatch.browser_binary_status", lambda: _Available()
    )
    sleep = _Sleep()
    result = await run_scrape_attempts(
        url="https://www.instagram.com/hedef/",
        cookie="",
        max_attempts=3,
        scrape=scrape,
        log=_Log(),
        sleep=sleep,
    )
    assert len(attempts) == 3
    assert sleep.calls == [2, 4], f"bekleme aralığı korunmalı, {sleep.calls}"
    assert result.infrastructure_failure is False
    assert result.reject_message() == EVIDENCE_REJECT_MESSAGE


@pytest.mark.asyncio
async def test_private_account_is_not_treated_as_infrastructure_failure(monkeypatch):
    """Gizli hesap: kanıt yetersizliği çağırana AYNEN taşınır (OSINT dalı korunur)."""
    from agent_core.scraper.instagram_ghost import InsufficientEvidenceError

    class _Available:
        available = True
        reason = ""
        source = "pinned"
        path = "/usr/bin/chromium"

    monkeypatch.setattr(
        "backend.services.scrape_dispatch.browser_binary_status", lambda: _Available()
    )

    async def scrape(url, cookie, log=None):
        raise InsufficientEvidenceError("private account")

    result = await run_scrape_attempts(
        url="https://www.instagram.com/hedef/",
        cookie="",
        max_attempts=3,
        scrape=scrape,
        log=_Log(),
        sleep=_Sleep(),
    )
    assert isinstance(result.insufficient_evidence, InsufficientEvidenceError)
    assert result.infrastructure_failure is False
    assert result.last_error is None


# ------------------------------------------------------- 3 · /health kapısı
def test_health_reports_missing_browser_as_degraded():
    """/health, ürünün çalışamayacağını ilk saniyede söyler (gerçek ölçüm)."""
    from fastapi.testclient import TestClient

    from backend.api import app

    state = browser_binary_status()
    with TestClient(app) as client:
        body = client.get("/health").json()

    components = body.get("components") or {}
    assert "browser" in components, "sağlık yanıtı tarayıcı bileşenini taşımalı"
    assert components["browser"]["available"] is state.available
    assert components["browser"]["reason"] == state.reason
    if not state.available:
        assert body["status"] == "degraded"
        assert BROWSER_MISSING_REASON in body["degraded_reasons"]


def test_health_gate_does_not_fire_when_binary_exists(monkeypatch):
    """Ters yön: ikili VARSA sağlık kapısı gürültü üretmez (yanlış alarm yok)."""

    from fastapi.testclient import TestClient

    import backend.api as api_module

    # lifespan `browser_binary_status` adını çalışma anında çözer → yama etkilidir.
    monkeypatch.setattr(
        api_module,
        "browser_binary_status",
        lambda: BrowserBinaryStatus(
            available=True, source="pinned", path="/usr/bin/chromium", reason=None
        ),
    )
    with TestClient(api_module.app) as client:
        body = client.get("/health").json()

    assert body.get("components", {}).get("browser", {}).get("available") is True
    assert BROWSER_MISSING_REASON not in (body.get("degraded_reasons") or [])
