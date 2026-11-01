"""Derin tarama kablosu — `merge_detected_profile_urls` sözleşmeleri.

[2026-10-23] Ölçüm: Instagram bio'sundaki Linktree/X bağlantıları
`external_urls` içinde toplanıyor ama `target_profile`'a yazılmıyordu; X
gönderilerindeki adresler hiç ayrıştırılmıyordu. Sonuç: bulunan profil
linkleri derin taramaya ULAŞMIYORDU (sessiz veri kaybı).

Bu testler birleştirme kuralını kilitler:
  * `detected_urls` + `external_urls` + OSINT bulguları birleşir
  * yalnız `classify_url(...).runnable` olan yollar girer (yanlış hedef yok)
  * sıra korunur, tekrar yok, üst sınır uygulanır
  * boş/garbage girdi çökmez, uydurma üretmez
"""

from __future__ import annotations

from agent_core.services.deep_url_cables import (
    MAX_DETECTED_URLS,
    merge_detected_profile_urls,
)
from agent_core.services.platform_registry import (
    detected_profile_urls,
    ig_target_profile_update,
    x_target_profile_update,
)
from agent_core.scraper.instagram_ghost import InstagramProfile


def test_instagram_bio_links_reach_the_payload():
    profile = InstagramProfile(
        username="hedef",
        biography="iletişim: https://linktr.ee/hedef",
        external_urls=["https://x.com/hedef", "https://example.com/haber"],
        is_private=False,
    )
    payload = ig_target_profile_update(profile)
    assert "https://linktr.ee/hedef" in payload["detected_urls"]
    assert "https://x.com/hedef" in payload["detected_urls"]
    assert "https://example.com/haber" not in payload["detected_urls"]
    assert payload["platform"] == "instagram"
    # Ham liste de kaybolmaz (denetimde "ne bulundu" görünür).
    assert "https://example.com/haber" in payload["external_urls"]


def test_x_tweet_and_bio_urls_are_extracted():
    payload = x_target_profile_update(
        "@hedef",
        [
            {"text": "instagram'da da varım: https://www.instagram.com/hedef/", "created_at": ""},
            {"text": "linktree https://linktr.ee/hedef.", "created_at": ""},
            {"text": "adres yok burada", "created_at": ""},
        ],
        bio="threads: https://www.threads.net/@hedef",
    )
    assert "https://www.instagram.com/hedef/" in payload["detected_urls"]
    assert "https://linktr.ee/hedef" in payload["detected_urls"], "cümle sonu noktalama kirletti"
    assert "https://www.threads.net/@hedef" in payload["detected_urls"]
    assert payload["bio"].startswith("threads:")


def test_x_without_urls_does_not_invent_any():
    payload = x_target_profile_update("hedef", [{"text": "sadece metin", "created_at": ""}])
    assert payload["external_urls"] == []
    assert payload["detected_urls"] == []


def test_detected_profile_urls_drops_unknown_and_non_profile_hosts():
    found = detected_profile_urls(
        "yazı https://example.com/a https://youtube.com/watch?v=1 https://github.com/hedef",
    )
    assert found == ["https://github.com/hedef"], found


def test_detected_profile_urls_accepts_lists_and_dedupes():
    found = detected_profile_urls(
        ["https://x.com/a", "https://x.com/a"],
        extra=["https://www.instagram.com/a/", "https://www.instagram.com/a/"]
    )
    assert found == ["https://x.com/a", "https://www.instagram.com/a/"]


def test_merge_prefers_payload_and_adds_osint_findings():
    merged = merge_detected_profile_urls(
        {"detected_urls": ["https://github.com/a"], "external_urls": ["https://x.com/a"]},
        {
            "username_scan": {"found_sites": [{"url": "https://www.reddit.com/user/a"}]},
            "handle_probe": {"found_sites": [{"url": "https://t.me/a"}]},
        },
    )
    assert merged[0] == "https://github.com/a", "sıra korunmadı"
    assert "https://x.com/a" in merged, "external_urls kabloya girmedi"
    assert "https://www.reddit.com/user/a" in merged
    assert "https://t.me/a" in merged


def test_merge_falls_back_to_external_urls_for_old_payloads():
    """Eski/gizli-profil payload'ında yalnız `external_urls` dolu olabilir."""
    merged = merge_detected_profile_urls({"external_urls": ["https://linktr.ee/hedef"]})
    assert merged == ["https://linktr.ee/hedef"]


def test_merge_applies_the_cap_and_keeps_order():
    many = [f"https://github.com/user{i}" for i in range(40)]
    merged = merge_detected_profile_urls({"detected_urls": many})
    assert len(merged) == MAX_DETECTED_URLS
    assert merged[0] == many[0]


def test_merge_survives_garbage_input():
    assert merge_detected_profile_urls(None, None) == []
    assert merge_detected_profile_urls({"detected_urls": "https://x.com/a"}, {}) == []
    assert merge_detected_profile_urls({"detected_urls": [None, 5, ""]}, {}) == []


# ==================================================== gerçek veri akışı (uçtan uca)
# Bu test kaynak metnini GREP'lemez: sahte `twscrape` ile sensörü çalıştırır,
# sensörün ürettiği payload'ı registry'ye verir ve derin tarama kablosunun
# çıktısını (`merge_detected_profile_urls`) doğrular. Zincir:
#   twscrape user.description → CapabilityResult.payload["bio"]
#     → x_target_profile_update(bio=...) → target_profile["detected_urls"]
#       → merge_detected_profile_urls → derin tarama listesi
import sys
import types

import pytest


class _FakeAccount:
    def __init__(self, active: bool) -> None:
        self.active = active


class _FakePool:
    def __init__(self, accounts) -> None:
        self._accounts = list(accounts)
        self._db_file = "/tmp/fake-x-accounts.db"

    async def get_all(self):
        return list(self._accounts)


class _FakeTweet:
    def __init__(self, text: str) -> None:
        self.id = 1234567890
        self.date = None
        self.rawContent = text
        self.likeCount = 1
        self.retweetCount = 0
        self.replyCount = 0
        self.quoteCount = 0


class _FakeUser:
    def __init__(self, description: str) -> None:
        self.id = 42
        self.description = description


class _FakeTwscrapeAPI:
    def __init__(self, pool=None, **kwargs) -> None:
        self.pool = _FakePool([_FakeAccount(True)])
        self.user = _FakeUser("iletişim: https://www.instagram.com/hedef/")
        self.tweets = [_FakeTweet("gönderi metni (link yok)")]

    async def user_by_login(self, username):
        return self.user

    def user_tweets(self, user_id, limit=50):
        async def _gen():
            for tweet in self.tweets:
                yield tweet

        return _gen()


async def _fake_gather(agen):
    return [item async for item in agen]


@pytest.mark.asyncio
async def test_x_sensor_bio_reaches_deep_scan(monkeypatch):
    """twscrape biyografisi → payload → profil → derin tarama (kablo kopuk değil)."""
    from agent_core.capabilities import adapters_sensors
    from agent_core.capabilities.adapters_sensors import XTwscrapeCapability
    from agent_core.capabilities.base import CapabilityContext

    monkeypatch.setitem(
        sys.modules,
        "twscrape",
        types.SimpleNamespace(API=_FakeTwscrapeAPI, gather=_fake_gather),
    )
    monkeypatch.setattr(adapters_sensors, "_module_available", lambda _name: True)
    monkeypatch.setenv("PINEAL_X_ACCOUNTS_DB", "/tmp/fake-x-accounts.db")

    result = await XTwscrapeCapability().run(CapabilityContext(subject="hedef"))
    assert result.available is True, result.unavailable_reason
    payload = result.payload or {}
    assert "https://www.instagram.com/hedef/" in payload.get("bio", ""), payload

    profile = x_target_profile_update(
        "hedef", list(payload.get("series") or []), bio=str(payload.get("bio") or "")
    )
    assert "https://www.instagram.com/hedef/" in profile["detected_urls"], profile

    merged = merge_detected_profile_urls(
        profile, {"username_scan": {"found_sites": [{"url": "https://github.com/hedef"}]}}
    )
    assert "https://www.instagram.com/hedef/" in merged
    assert "https://github.com/hedef" in merged
