"""
PINEAL-HERETIC - Instagram Ghost Scraper Testleri
Halüsinasyon yok mu? Test et.

Bu testler compileall değil, gerçek hata enjeksiyonu.
"""
import pytest
import sys
sys.path.insert(0, '/mnt/data')

from agent_core.scraper.instagram_ghost import InstagramGhostScraper, InstagramProfile, InstagramPost, InsufficientEvidenceError


def test_private_account_should_not_hallucinate_posts():
    """Gizli hesapta post uydurma"""
    scraper = InstagramGhostScraper()
    html_private = '{"is_private":true,"edge_followed_by":{"count":123}} <meta property="og:description" content="Gizli hesap">'
    with pytest.raises(InsufficientEvidenceError):
        scraper._parse_real_profile({}, html_private, "gizli_kullanici")

def test_empty_html_should_halt_not_hallucinate():
    """Boş HTML gelirse halt etmeli, uydurma profil üretmemeli"""
    scraper = InstagramGhostScraper()
    with pytest.raises(InsufficientEvidenceError):
        scraper._parse_real_profile({}, "<html></html>", "bos_kullanici")

def test_rate_limit_detection():
    """Rate limit duvarını yakalamalı"""
    scraper = InstagramGhostScraper()
    # _extract_from_html JSON bulamazsa InsufficientEvidenceError fırlatır - bu doğru davranış
    with pytest.raises(InsufficientEvidenceError):
        scraper._extract_from_html("<html>Try again later</html>", "rate_limited_user")

def test_confidence_scoring_prevents_hallucination():
    """Güven < 0.6 ise halt - Faz 4 kuralı"""
    scraper = InstagramGhostScraper()
    
    # Yetersiz kanıt: sadece username var
    weak_profile = InstagramProfile(
        username="zayif",
        is_private=False,
        posts=[]
    )
    assert scraper.evaluate_confidence(weak_profile) < 0.6

    # Güçlü kanıt: bio + 3 post + follower
    strong_profile = InstagramProfile(
        username="guclu",
        biography="Gerçek bir bio",
        is_private=False,
        follower_count=1000,
        posts=[
            InstagramPost(shortcode="abc", display_url="https://example.com/1.jpg"),
            InstagramPost(shortcode="def", display_url="https://example.com/2.jpg"),
            InstagramPost(shortcode="ghi", display_url="https://example.com/3.jpg"),
        ]
    )
    assert scraper.evaluate_confidence(strong_profile) >= 0.6

def test_pydantic_forbids_hallucinated_fields():
    """Pydantic extra=forbid - uydurma field eklenemez"""
    with pytest.raises(Exception):
        InstagramProfile(
            username="test",
            is_private=False,
            uydurma_alan="bu halüsinasyondur"  # Pydantic bunu reddetmeli
        )

def test_url_must_be_real():
    """Sahte URL halüsinasyondur"""
    with pytest.raises(Exception):
        InstagramPost(shortcode="abc", display_url="sahte_url_degil_http")

def test_scrape_without_playwright_page_should_halt():
    """Playwright page verilmezse kendi kendine tarayıcı açıp uydurma"""
    import asyncio
    scraper = InstagramGhostScraper()
    
    async def run():
        with pytest.raises(InsufficientEvidenceError):
            await scraper.scrape_async("test_user", playwright_page=None)
    
    asyncio.run(run())


def _html_with_posts(n: int) -> str:
    """n adet gerçek shortcode + display_url çifti taşıyan profil HTML'i."""
    units = []
    for i in range(n):
        units.append(
            '"shortcode":"sc%02d","display_url":"https://scontent.cdninstagram.com/v/sc%02d.jpg"'
            % (i, i)
        )
    return (
        '{"is_private":false,"edge_followed_by":{"count":1500},'
        '"biography":"gerçek bio https://linktr.ee/hedef",'
        + ",".join(units)
        + "}"
    )


def test_ham_html_yolu_12_tavanini_asmali():
    """[2026-10-23] Sabit 12 tavanı kalktı: 20 gönderi de toplanır.

    Bu yol Playwright'sız ham HTML ayrıştırmasıdır ve `min(len(display_urls), 12)`
    ile sessizce kırpıyordu; artık tavan operatör ayarıdır.
    """
    scraper = InstagramGhostScraper()
    profile = scraper._parse_real_profile({}, _html_with_posts(20), "hedef")
    assert len(profile.posts) == 20, f"12 tavanı geri gelmiş: {len(profile.posts)}"


def test_ham_html_yolu_operator_tavanina_uyar(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_MAX_POSTS", "5")
    scraper = InstagramGhostScraper()
    profile = scraper._parse_real_profile({}, _html_with_posts(20), "hedef")
    assert len(profile.posts) == 5
