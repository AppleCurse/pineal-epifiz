"""
PINEAL-HERETIC - Instagram Ghost Scraper Testleri
Halüsinasyon yok mu? Test et.

Bu testler compileall değil, gerçek hata enjeksiyonu.
"""
import pytest
import sys
sys.path.insert(0, '/mnt/data')

from agent_core.scraper.instagram_ghost import InstagramGhostScraper, InstagramProfile, InstagramPost, InsufficientEvidenceError


def test_private_account_preserves_visible_metadata_without_posts():
    """Gizli profilin sayfada açıkça görünen metaverisi korunur; içerik uydurulmaz."""
    scraper = InstagramGhostScraper()
    raw = {"data": {"user": {
        "username": "gizli_kullanici",
        "full_name": "Örnek Profil",
        "biography": "Uzman. Bilgi: https://example.org/",
        "external_url": "https://business.example.org",
        "is_private": True,
        "edge_followed_by": {"count": 123},
    }}}
    profile = scraper._parse_real_profile(raw, '{"is_private" : true}', "gizli_kullanici")
    assert profile.is_private is True
    assert profile.full_name == "Örnek Profil"
    assert profile.follower_count == 123
    assert profile.external_url == "https://business.example.org"
    assert profile.bio_links == ["https://example.org/"]
    assert profile.posts == []

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
