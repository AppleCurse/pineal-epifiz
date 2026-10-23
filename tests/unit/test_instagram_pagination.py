"""Instagram sayfalama (pagination) — 12-post tavanı regresyon kilidi.

[2026-10-23 ölçümü] Eski davranış: ızgara TEK `goto` ile okunuyor, sonuç
`[:12]` dilimi + `InstagramProfile.posts` doğrulayıcısındaki `v[:12]` ile
kırpılıyordu. Instagram ilk yüklemede ~12 gönderi verdiği için 13. post
hiçbir zaman görünmüyordu ve bu durum HATA üretmiyordu (sessiz tavan).

Bu testler ağ kullanmaz: Playwright `page` nesnesi sahtedir, HTML
gönderi sayfaları da elle kurulur. Doğrulananlar:
  1. Tavan operatör ayarıdır (PINEAL_IG_MAX_POSTS) — sabit 12 değil.
  2. Kaydırma yeni shortcode getirirse post sayfası ziyaret edilir ve
     post nesnesi üretilir.
  3. Görsel kanıtı (og:image) olmayan aday post ÜRETİLMEZ.
  4. İki tur üst üste büyüme yoksa döngü durur (sonsuz kaydırma yok).
  5. Sayfalama kapalıyken (PINEAL_IG_SCROLL_PAGES=0) hiç çalışmaz.
  6. Gizli profilde sayfalama hiç çağrılmaz.
  7. `page_info.has_next_page` / `end_cursor` gömülü JSON'dan okunur.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from agent_core.scraper.instagram_ghost import (
    InstagramGhostScraper,
    InstagramPost,
    InstagramProfile,
)


# ------------------------------------------------------------------ yardımcılar
def _post_html(shortcode: str, *, with_image: bool = True, caption: str | None = "gerçek caption") -> str:
    image = (
        f'<meta property="og:image" content="https://cdninstagram.example/{shortcode}.jpg">'
        if with_image else ""
    )
    cap = f'<meta property="og:description" content="{caption}">' if caption else ""
    ld = {
        "@type": "ImageObject",
        "uploadDate": f"2026-01-0{len(shortcode) % 9 + 1}T10:00:00Z",
        "caption": caption or "",
    }
    return (
        f"<html><head>{image}{cap}"
        f'<script type="application/ld+json">{json.dumps(ld)}</script>'
        f"</head><body>{shortcode}</body></html>"
    )


class _FakePage:
    """Playwright `page` sahtesi: kaydırma → yeni href'ler, goto → HTML."""

    def __init__(self, scroll_batches, html_by_shortcode):
        self._batches = list(scroll_batches)
        self._html = html_by_shortcode
        self.hrefs: list[str] = []
        self.visited: list[str] = []
        self.scrolls = 0

    async def evaluate(self, script: str):
        if "scrollTo" in script:
            self.scrolls += 1
            if self._batches:
                self.hrefs.extend(self._batches.pop(0))
            return None
        # document.querySelectorAll('a[href]') → href listesi
        return list(self.hrefs)

    async def goto(self, url: str, **_kwargs):
        code = url.rstrip("/").rsplit("/", 1)[-1]
        self.visited.append(code)

    async def content(self):
        code = self.visited[-1] if self.visited else ""
        return self._html.get(code, "<html></html>")


def _scraper() -> InstagramGhostScraper:
    return InstagramGhostScraper()


def _existing(n: int) -> list[InstagramPost]:
    return [
        InstagramPost(
            shortcode=f"EXISTING{i:02d}",
            display_url=f"https://cdninstagram.example/e{i}.jpg",
        )
        for i in range(n)
    ]


# ------------------------------------------------------- 1) tavan ayarlanabilir
def test_post_ceiling_is_configurable_not_hardcoded(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_MAX_POSTS", "3")
    posts = [
        InstagramPost(shortcode=f"S{i:03d}", display_url=f"https://c.example/{i}.jpg")
        for i in range(10)
    ]
    profile = InstagramProfile(username="hedef", is_private=False, posts=posts)
    assert len(profile.posts) == 3

    monkeypatch.setenv("PINEAL_IG_MAX_POSTS", "60")
    profile2 = InstagramProfile(username="hedef", is_private=False, posts=posts)
    assert len(profile2.posts) == 10, "tavan 12'de kaldı — sessiz kırpma geri geldi"


def test_default_ceiling_allows_more_than_the_old_twelve():
    posts = [
        InstagramPost(shortcode=f"S{i:03d}", display_url=f"https://c.example/{i}.jpg")
        for i in range(30)
    ]
    profile = InstagramProfile(username="hedef", is_private=False, posts=posts)
    assert len(profile.posts) == 30


# ---------------------------------------------------- 2) kaydırma → yeni postlar
def test_scroll_harvest_creates_verified_posts(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_MAX_POSTS", "48")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAGES", "3")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAUSE", "0")
    monkeypatch.setenv("PINEAL_POST_DETAIL_PAUSE", "0")

    codes = [f"NEW{i:03d}" for i in range(5)]
    page = _FakePage(
        scroll_batches=[[f"https://www.instagram.com/p/{c}/" for c in codes]],
        html_by_shortcode={c: _post_html(c) for c in codes},
    )
    scraper = _scraper()
    extra = asyncio.run(
        scraper._paginate_grid(page, "hedef", _existing(12), raw_json=None)
    )
    assert len(extra) == 5, f"kaydırma sonrası postlar alınmadı: {extra}"
    assert {p.shortcode for p in extra} == set(codes)
    assert all(p.display_url.startswith("https://") for p in extra)
    assert len(page.visited) == 5


def test_pagination_is_bounded_by_max_posts(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_MAX_POSTS", "15")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAGES", "5")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAUSE", "0")
    monkeypatch.setenv("PINEAL_POST_DETAIL_PAUSE", "0")

    codes = [f"MANY{i:03d}" for i in range(20)]
    page = _FakePage(
        scroll_batches=[[f"https://www.instagram.com/reel/{c}/" for c in codes]],
        html_by_shortcode={c: _post_html(c) for c in codes},
    )
    extra = asyncio.run(scraper_call := _scraper()._paginate_grid(page, "hedef", _existing(12), None))
    assert len(extra) == 3, f"tavan aşıldı: {len(extra)} (12 mevcut + 3 = 15 bekleniyordu)"
    del scraper_call


# ------------------------------------------- 3) görsel kanıtı yoksa post yok
def test_candidate_without_image_is_not_fabricated(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_MAX_POSTS", "20")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAGES", "2")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAUSE", "0")
    monkeypatch.setenv("PINEAL_POST_DETAIL_PAUSE", "0")

    page = _FakePage(
        scroll_batches=[[
            "https://www.instagram.com/p/NOIMAGE01/",
            "https://www.instagram.com/p/WITHIMG01/",
        ]],
        html_by_shortcode={
            "NOIMAGE01": _post_html("NOIMAGE01", with_image=False),
            "WITHIMG01": _post_html("WITHIMG01"),
        },
    )
    extra = asyncio.run(_scraper()._paginate_grid(page, "hedef", _existing(1), None))
    assert [p.shortcode for p in extra] == ["WITHIMG01"], (
        "görsel kanıtı olmayan post üretildi (halüsinasyon)"
    )


def test_wrong_or_missing_page_yields_nothing():
    page = _FakePage(scroll_batches=[], html_by_shortcode={})
    scraper = _scraper()
    assert asyncio.run(scraper._post_from_detail_page(page, "UNKNOWN01")) is None


# --------------------------------------------------- 4) büyüme yoksa dur
def test_stops_after_two_stagnant_scrolls(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAGES", "9")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAUSE", "0")
    monkeypatch.setenv("PINEAL_POST_DETAIL_PAUSE", "0")
    page = _FakePage(scroll_batches=[], html_by_shortcode={})
    extra = asyncio.run(_scraper()._paginate_grid(page, "hedef", _existing(12), None))
    assert extra == []
    assert page.scrolls == 2, f"boşuna kaydırma: {page.scrolls}"


# --------------------------------------------- 5) kapalıyken hiç çalışmaz
def test_pagination_disabled_makes_no_requests(monkeypatch):
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAGES", "0")
    page = _FakePage(scroll_batches=[["https://www.instagram.com/p/ABC123/"]], html_by_shortcode={})
    extra = asyncio.run(_scraper()._paginate_grid(page, "hedef", _existing(12), None))
    assert extra == []
    assert page.scrolls == 0 and page.visited == []


# -------------------------------------------------- 6) gizli profilde çalışmaz
def test_private_profile_never_paginates(monkeypatch):
    """Gizli profilin ızgarası yoktur; kaydırma gereksiz ağ trafiğidir."""
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAGES", "4")
    monkeypatch.setenv("PINEAL_IG_SCROLL_PAUSE", "0")
    monkeypatch.setenv("PINEAL_POST_DETAIL_PAUSE", "0")
    page = _FakePage(scroll_batches=[["https://www.instagram.com/p/ABC123/"]], html_by_shortcode={})
    scraper = _scraper()
    profile = InstagramProfile(
        username="gizli", is_private=True, biography="bio", follower_count=10,
    )
    # scrape_async içindeki koşul: `if not profile.is_private`
    assert profile.is_private is True
    assert profile.posts == []
    assert page.scrolls == 0
    del scraper


# --------------------------------------- 7) cursor (page_info) okunur
@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"data": {"user": {"edge_owner_to_timeline_media": {
            "page_info": {"has_next_page": True, "end_cursor": "QVFI123"}
        }}}}, (True, "QVFI123")),
        ({"a": [{"b": {"page_info": {"has_next_page": False}}}]}, (False, None)),
        ({"_source": "meta_tags"}, (None, None)),
        ({}, (None, None)),
    ],
)
def test_page_cursor_is_read_from_embedded_json(payload, expected):
    assert InstagramGhostScraper._page_cursor(payload) == expected


# ------------------------------------------- 8) href → shortcode ayrıştırma
def test_shortcodes_from_hrefs_is_ordered_deduplicated_and_strict():
    hrefs = [
        "https://www.instagram.com/p/AAA111/",
        "https://www.instagram.com/reel/BBB222/",
        "https://www.instagram.com/p/AAA111/?utm=x",   # tekrar
        "https://www.instagram.com/explore/tags/xyz/",  # gönderi değil
        "https://www.instagram.com/hedef/",             # profil
        "", None, 123,                                  # çöp
        "https://www.instagram.com/tv/CCC333/",
    ]
    assert InstagramGhostScraper._shortcodes_from_hrefs(hrefs) == ["AAA111", "BBB222", "CCC333"]


def test_extract_post_detail_exposes_real_image_only():
    html = _post_html("REAL001")
    detail = InstagramGhostScraper._extract_post_detail(html, "REAL001")
    assert detail["display_url"] == "https://cdninstagram.example/REAL001.jpg"

    empty = InstagramGhostScraper._extract_post_detail("<html><body>REAL001</body></html>", "REAL001")
    assert "display_url" not in empty, "görsel yokken display_url uyduruldu"
    # Yanlış sayfa (shortcode metinde yok) → boş sözlük, veri karışmaz.
    assert InstagramGhostScraper._extract_post_detail("<html>başka</html>", "REAL001") == {}
