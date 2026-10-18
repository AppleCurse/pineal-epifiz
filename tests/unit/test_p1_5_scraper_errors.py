"""
P1.5 — Scraper hata zinciri testleri.

Kanıtlanacak garantiler:
  A. playwright_page=None → InsufficientEvidenceError, sessiz başarı değil
  B. navigation timeout → InsufficientEvidenceError (3 deneme sonrası)
  C. Kalıcı browser hatası → tek denemede InsufficientEvidenceError
  D. Login duvarı → InsufficientEvidenceError (hassas cookie bilgisi sızmıyor)
  E. Rate-limit duvarı → InsufficientEvidenceError
  F. Boş HTML (hiç JSON yok) → InsufficientEvidenceError
  G. Private + post yok → InsufficientEvidenceError
  H. evaluate_confidence: düşük veri → score < 0.6
  I. Hata mesajında stack trace / iç IP / cookie gibi hassas veri sızmamalı
  J. run_scraper.py: executor, scraper failure'ını başarılı gibi raporlamıyor
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_core.scraper.instagram_ghost import (
    InstagramGhostScraper,
    InstagramProfile,
    InsufficientEvidenceError,
)


# ------------------------------------------------------------------
# TEST A: playwright_page=None → InsufficientEvidenceError
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_playwright_page_raises_insufficient_evidence():
    """page verilmezse sessiz başarı değil, InsufficientEvidenceError fırlatılmalı."""
    scraper = InstagramGhostScraper()
    with pytest.raises(InsufficientEvidenceError) as exc_info:
        await scraper.scrape_async("hedef_kullanici", playwright_page=None)
    assert "playwright" in str(exc_info.value).lower() or "page" in str(exc_info.value).lower()


# ------------------------------------------------------------------
# TEST B: navigation timeout (transient × 3) → InsufficientEvidenceError
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_navigation_timeout_raises_after_retries():
    """3 kez timeout alınırsa InsufficientEvidenceError fırlatılmalı."""
    mock_page = AsyncMock()
    mock_page.goto.side_effect = Exception("net::ERR_CONNECTION_TIMED_OUT timeout")

    scraper = InstagramGhostScraper()
    with patch.object(scraper, "_random_delay", new_callable=AsyncMock):
        with patch("asyncio.sleep", new_callable=AsyncMock):  # asyncio modülünden patch
            with pytest.raises(InsufficientEvidenceError) as exc_info:
                await scraper.scrape_async("hedef", playwright_page=mock_page)

    assert mock_page.goto.call_count == 3, (
        f"3 deneme bekleniyor, {mock_page.goto.call_count} yapıldı"
    )
    err = str(exc_info.value)
    assert "timeout" in err.lower() or "transient" in err.lower() or "network" in err.lower()


# ------------------------------------------------------------------
# TEST C: Kalıcı (non-transient) browser hatası → tek denemede HALT
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_permanent_browser_error_raises_immediately():
    """Kalıcı hata (not timeout/net::) → 1 denemede InsufficientEvidenceError."""
    # goto: sadece exception fırlatan coroutine — AsyncMock dangling bırakmıyor
    async def _failing_goto(*args, **kwargs):
        raise Exception("FATAL: unsupported protocol scheme")

    mock_page = MagicMock()
    mock_page.goto = _failing_goto
    # goto call_count için wrapper
    call_tracker = {"n": 0}
    _orig = _failing_goto

    async def _tracked_goto(*args, **kwargs):
        call_tracker["n"] += 1
        return await _orig(*args, **kwargs)

    mock_page.goto = _tracked_goto

    scraper = InstagramGhostScraper()
    with patch.object(scraper, "_random_delay", new_callable=AsyncMock):
        with pytest.raises(InsufficientEvidenceError) as exc_info:
            await scraper.scrape_async("hedef", playwright_page=mock_page)

    # Kalıcı hatada yalnızca 1 kez goto çağrılmalı
    assert call_tracker["n"] == 1, (
        f"Kalıcı hatada 1 deneme bekleniyor, {call_tracker['n']} yapıldı"
    )
    assert "kalıcı" in str(exc_info.value).lower() or "scraper" in str(exc_info.value).lower()


# ------------------------------------------------------------------
# TEST D: Login duvarı → InsufficientEvidenceError (cookie bilgisi sızmıyor)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_wall_raises_no_cookie_leak():
    """Login duvarı tespitinde InsufficientEvidenceError; hata mesajında 'cookie value' yok."""
    mock_page = AsyncMock()
    mock_page.goto.return_value = None
    mock_page.content.return_value = (
        '<html><body>Login • Instagram '
        'name="username" name="password"</body></html>'
    )

    scraper = InstagramGhostScraper(vault_cookies={"sessionid": "SECRET_COOKIE_VALUE_12345"})
    with patch.object(scraper, "_random_delay", new_callable=AsyncMock):
        with pytest.raises(InsufficientEvidenceError) as exc_info:
            await scraper.scrape_async("hedef", playwright_page=mock_page)

    err = str(exc_info.value)
    assert "login" in err.lower(), f"Login mesajı bekleniyor: {err}"
    # Hassas cookie değeri hata mesajına sızmamalı
    assert "SECRET_COOKIE_VALUE_12345" not in err, (
        "GÜVENLİK İHLALİ: cookie değeri hata mesajında görünüyor!"
    )


# ------------------------------------------------------------------
# TEST E: Rate-limit duvarı → InsufficientEvidenceError
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limit_raises_insufficient_evidence():
    """Rate-limit tespitinde InsufficientEvidenceError fırlatılmalı."""
    mock_page = AsyncMock()
    mock_page.goto.return_value = None
    mock_page.content.return_value = (
        "<html><body>Try again later We restrict certain activity</body></html>"
    )

    scraper = InstagramGhostScraper()
    with patch.object(scraper, "_random_delay", new_callable=AsyncMock):
        with pytest.raises(InsufficientEvidenceError) as exc_info:
            await scraper.scrape_async("hedef", playwright_page=mock_page)

    assert "rate" in str(exc_info.value).lower() or "restrict" in str(exc_info.value).lower()


# ------------------------------------------------------------------
# TEST F: Boş HTML (JSON pattern bulunamıyor) → InsufficientEvidenceError
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_html_no_json_raises():
    """HTML'de hiçbir JSON pattern bulunamazsa InsufficientEvidenceError."""
    mock_page = AsyncMock()
    mock_page.goto.return_value = None
    mock_page.content.return_value = "<html><body>Beklenmedik sayfa</body></html>"

    scraper = InstagramGhostScraper()
    with patch.object(scraper, "_random_delay", new_callable=AsyncMock):
        with pytest.raises(InsufficientEvidenceError) as exc_info:
            await scraper.scrape_async("hedef", playwright_page=mock_page)

    assert "json bulunamadı" in str(exc_info.value).lower() or "bulunamad" in str(exc_info.value).lower()


# ------------------------------------------------------------------
# TEST G: Private profil + 0 post → InsufficientEvidenceError
# ------------------------------------------------------------------
def test_private_profile_no_posts_halts():
    """_parse_real_profile: private + 0 post → InsufficientEvidenceError."""
    scraper = InstagramGhostScraper()
    html_private_no_posts = (
        '{"is_private":true}'  # JSON body
        '"is_private":true'    # raw signal
    )
    with pytest.raises(InsufficientEvidenceError) as exc_info:
        scraper._parse_real_profile({}, html_private_no_posts, "gizli_kullanici")

    assert "private" in str(exc_info.value).lower() or "gizli" in str(exc_info.value).lower()


# ------------------------------------------------------------------
# TEST H: evaluate_confidence — düşük veri → score < 0.6
# ------------------------------------------------------------------
def test_evaluate_confidence_low_data_below_threshold():
    """Follower ve bio yok, post yok → confidence < 0.6 (executor HALT yapmalı)."""
    scraper = InstagramGhostScraper()
    profile = InstagramProfile(
        username="boş_profil",
        is_private=False,
        follower_count=None,
        biography=None,
        posts=[],
    )
    score = scraper.evaluate_confidence(profile)
    assert score < 0.6, f"Beklenen score < 0.6, gelen: {score}"


def test_evaluate_confidence_private_caps_at_04():
    """Private profil: confidence maksimum 0.4 (yetersiz kanıt)."""
    scraper = InstagramGhostScraper()
    profile = InstagramProfile(
        username="gizli",
        is_private=True,
        follower_count=1000,
        biography="bir bio",
        posts=[],
    )
    score = scraper.evaluate_confidence(profile)
    assert score <= 0.4, f"Private profil max 0.4 olmalı, gelen: {score}"


# ------------------------------------------------------------------
# TEST I: Hata mesajında iç detaylar (traceback içeriği) sızmamalı
# ------------------------------------------------------------------
def test_extract_from_html_error_message_no_internal_leak():
    """_extract_from_html hata mesajında Python traceback frame yok."""
    scraper = InstagramGhostScraper()
    with pytest.raises(InsufficientEvidenceError) as exc_info:
        scraper._extract_from_html("<html>hiç pattern yok</html>", "test_user")

    err = str(exc_info.value)
    # Traceback frame'leri sızdırmamalı
    for leak in ("File \"", "Traceback", "line ", "__pycache__"):
        assert leak not in err, f"İç detay sızdı: '{leak}' mesajda: {err}"


# ------------------------------------------------------------------
# TEST J: run_scraper.py — InsufficientEvidenceError üst katmana yayılır
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scraper_error_propagates_not_swallowed(monkeypatch, tmp_path):
    """
    InstagramGhostScraper hata fırlattığında run_scraper.py onu yakalamalı
    ve başarılı gibi boş JSON dönmemeli.
    """
    from agent_core.scraper import run_scraper

    # [E-GÖZ2-3] CLI kapısı (strict) yetkili ortamda açılır: test GERÇEK
    # kasa malzemesiyle yetkilendirilir (kapı devre dışı BIRAKILMAZ).
    vault = tmp_path / "vault.json"
    vault.write_text(
        '{"pineal": {"vault": {"api_key": "sk-test-real-key-123"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("PINEAL_VAULT_FILE", str(vault))
    monkeypatch.delenv("PINEAL_ENV", raising=False)

    # scrape_async'ı direkt InsufficientEvidenceError atacak şekilde mock'la
    mock_scraper = AsyncMock()
    mock_scraper.side_effect = InsufficientEvidenceError("Test: Kanıt yetersiz")

    captured_output = []

    def fake_print(s):
        captured_output.append(s)

    # run_scraper.main'in sys.argv[1] ile çalıştığını simüle et
    with patch("sys.argv", ["run_scraper.py", "test_user"]), \
         patch("agent_core.scraper.run_scraper.InstagramGhostScraper") as MockScraper, \
         patch("builtins.print", side_effect=fake_print), \
         patch("agent_core.scraper.run_scraper.async_playwright") as mock_pw:

        # Playwright context manager mock'u
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_pw.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            chromium=MagicMock(launch=AsyncMock(return_value=mock_browser))
        ))
        mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        # Scraper instance'ının scrape_async'ı hata fırlatsın
        mock_instance = AsyncMock()
        mock_instance.scrape_async.side_effect = InsufficientEvidenceError("Playwright sayfası yok")
        MockScraper.return_value = mock_instance

        await run_scraper.main()

    # Çıktıda en az bir şey olmalı ve başarı mesajı içermemeli
    assert len(captured_output) > 0, "run_scraper.main hiç çıktı vermedi"
    output_str = " ".join(str(x) for x in captured_output)
    # Hata durumunda başarılı profile JSON döndürmemeli
    assert '"username"' not in output_str or '"error"' in output_str, (
        "Scraper hata alırken başarılı profile JSON döndürdü — başarı yanlış raporlandı!"
    )
