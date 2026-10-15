"""Dalga 1 + Dalga 2 düzeltmelerinin regresyon sözleşmeleri.

[023] tanınmayan platform -> unsupported_web (IG'ye zorlama yok)
[024] following=None "ölçülmedi"; 0 ölçümdür
[025] yapısal post extraction (caption/taken_at/like/comment) + hizalı
      post_times/posts_meta glue mapping'i
[026] sentetik "Instagram Profili: ..." postu ÜRETİLMEZ
[027] boş posts_meta -> sahte 1-post sentinel'i yok
[028] 3/3 executor hatası -> WS'de terminal result_error (UI asılı kalmaz)
[029] task_id benzersiz (saniye çakışması yok)
[030] ShadowExecutor executor'ın anahtarlı gateway'ini kullanır
[031] Shadow mirror kullanıcı alan adlarını payload sözleşmesinden okur
[035] geçici görseller her çıkış yolunda silinir
"""

import re
import tempfile
import os
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.scraper.instagram_ghost import InstagramGhostScraper, InstagramProfile, InstagramPost
from agent_core.services.follower_audit import audit_followers
from backend.api import (
    InitiatePayload,
    _effective_scraper_type,
    _ig_target_profile_update,
    _new_task_id,
    run_mission,
)


# ------------------------------------------------------------------ #
# [023] platform routing registry
# ------------------------------------------------------------------ #
def test_unrecognized_platform_never_becomes_instagram():
    assert _effective_scraper_type("https://tiktok.com/@hedef", "cross") == "unsupported_web"
    assert _effective_scraper_type("https://ornek.com/profil/foo", "instagram") == "unsupported_web"
    assert _effective_scraper_type("https://www.instagram.com/p/Cabc/", "cross") == "instagram"
    assert _effective_scraper_type("https://x.com/hedef", "cross") == "x"


@pytest.mark.asyncio
async def test_unsupported_platform_halts_without_scraping_or_analysis():
    """Tanınmayan URL: kazıma YOK, executor YOK, terminal result_error VAR."""
    executor = MagicMock()
    executor.execute_task = AsyncMock()

    errors = []

    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result"), \
         patch("backend.api.broadcast_result_error", side_effect=lambda *a: errors.append(a)):
        await run_mission(InitiatePayload(
            client_id="fx_unsup", url="https://tiktok.com/@baskasi",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="cross",
        ))

    executor.execute_task.assert_not_awaited()
    assert errors and errors[0][1] == "unsupported_platform"


# ------------------------------------------------------------------ #
# [024]/[025]/[026] IG -> payload glue mapping
# ------------------------------------------------------------------ #
def _profile_fixture():
    return InstagramProfile(
        username="hedef",
        full_name="Hedef Kişi",
        biography="biyografi",
        is_private=False,
        follower_count=1200,
        following_count=None,  # ölçülmedi
        post_count=3,
        posts=[
            InstagramPost(  # tam kanıtlı post
                shortcode="C1",
                caption="gece yarısı notu",
                display_url="https://scontent.cdn.example/a1.jpg",
                taken_at=datetime(2024, 5, 1, 23, 30, tzinfo=timezone.utc),
                like_count=45,
                comment_count=3,
            ),
            InstagramPost(  # caption'sız, zamansız, ölçüsüz post
                shortcode="C2",
                display_url="https://scontent.cdn.example/a2.jpg",
            ),
            InstagramPost(  # yalnız zaman damgalı post
                shortcode="C3",
                display_url="https://scontent.cdn.example/a3.jpg",
                taken_at=datetime(2024, 5, 3, 4, 10, tzinfo=timezone.utc),
            ),
        ],
    )


def test_ig_mapping_never_fabricates_placeholder_post():
    update = _ig_target_profile_update(_profile_fixture())
    joined = str(update)
    assert "Instagram Profili:" not in joined, "[026] sentetik post üretildi"
    assert "Instagram:" not in joined


def test_ig_mapping_posts_times_meta_are_index_aligned():
    """posts[i]/post_times[i]/posts_meta[i] aynı postu anlatır ([025]).
    Hizasız listeler frequency_engine'de caption'a başka postun zamanını
    yanlış eşleştirir."""
    update = _ig_target_profile_update(_profile_fixture())
    assert len(update["posts"]) == 3
    assert len(update["post_times"]) == 3
    assert len(update["posts_meta"]) == 3

    assert update["posts"][0] == "gece yarısı notu"
    assert update["posts"][1] == ""            # caption yoksa "" (uydurma yok)
    assert update["post_times"][0].startswith("2024-05-01T23:30")
    assert update["post_times"][1] == ""       # zaman yoksa "" (None sızması yok)
    assert update["post_times"][2].startswith("2024-05-03T04:10")
    assert update["posts_meta"][0] == {"like_count": 45, "comment_count": 3}
    assert update["posts_meta"][1] == {"like_count": None, "comment_count": None}


def test_ig_mapping_following_none_is_explicit_not_zero():
    update = _ig_target_profile_update(_profile_fixture())
    assert update["following"] is None  # [024] ölçülmedi


def test_missing_follower_count_stays_unmeasured_through_audit_producer():
    profile = InstagramProfile(
        username="hedef",
        biography=None,
        is_private=False,
        follower_count=None,
        following_count=None,
        posts=[
            InstagramPost(
                shortcode="C10",
                display_url="https://scontent.cdn.example/x.jpg",
                like_count=10,
                comment_count=1,
            )
        ],
    )
    update = _ig_target_profile_update(profile)
    assert update["followers"] is None
    report = audit_followers(update["followers"], update["following"], update["posts_meta"])
    assert report.follower_count is None
    assert report.engagement_rate is None
    assert report.verdict_code == "insufficient"


def test_zero_follower_count_remains_a_measured_zero():
    report = audit_followers(0, None, [])
    assert report.follower_count == 0
    assert report.verdict_code == "insufficient"
    assert "ölçülmedi" not in report.evidence[0]


def test_ig_mapping_captionless_profile_yields_empty_strings_not_fake_posts():
    profile = InstagramProfile(
        username="hedef", biography=None, is_private=False, follower_count=10,
        posts=[InstagramPost(shortcode="C9", display_url="https://scontent.cdn.example/x.jpg")],
    )
    update = _ig_target_profile_update(profile)
    assert update["posts"] == [""]
    assert "Instagram Profili" not in str(update)


# ------------------------------------------------------------------ #
# [024]/[027] follower audit ölçülmedi sözleşmesi
# ------------------------------------------------------------------ #
def test_audit_following_none_reports_not_measured():
    rep = audit_followers(1000, None, [])
    assert rep.following_count is None
    assert any("ölçülmedi" in e for e in rep.evidence)
    assert not any("Takip Edilen: 0" in e for e in rep.evidence)


def test_audit_following_measured_reports_number():
    rep = audit_followers(1000, 123, [])
    assert rep.following_count == 123
    assert any("Takip Edilen: 123" in e for e in rep.evidence)


def test_audit_empty_posts_meta_reports_zero_posts_not_one():
    """[027] sahte 1-post sentinel'i kaldırıldı."""
    rep = audit_followers(1000, None, [])
    assert rep.post_count == 0
    assert any("İncelenen Post: 0" in e for e in rep.evidence)
    assert not any("İncelenen Post: 1" in e for e in rep.evidence)


# ------------------------------------------------------------------ #
# [025] yapısal post extraction
# ------------------------------------------------------------------ #
def _structured_raw_json():
    return {
        "entry_data": {
            "ProfilePage": [{
                "graphql": {
                    "user": {
                        "edge_owner_to_timeline_media": {
                            "edges": [
                                {"node": {
                                    "shortcode": "S1",
                                    "display_url": "https://scontent.cdn.example/s1.jpg",
                                    "taken_at_timestamp": 1714585800,
                                    "is_video": False,
                                    "edge_media_to_caption": {"edges": [{"node": {"text": "ilk gönderi"}}]},
                                    "edge_liked_by": {"count": 12},
                                    "edge_media_to_comment": {"count": 2},
                                }},
                                {"node": {
                                    "shortcode": "S2",
                                    "display_url": "https://scontent.cdn.example/s2.jpg",
                                    "taken_at_timestamp": 1714499400,
                                    "is_video": True,
                                }},
                            ]
                        }
                    }
                }
            }]
        }
    }


def _og_html(followers=True):
    parts = ["<html><head>"]
    if followers:
        parts.append('<meta property="og:description" content="1,204 Followers, 310 Following, 42 Posts - n">')
    parts.append('<meta property="og:title" content="Hedef Kişi (@hedef) • Instagram photos and videos">')
    parts.append('<meta property="og:image" content="https://scontent.cdn.example/pp.jpg">')
    parts.append("</head><body></body></html>")
    return "".join(parts)


def test_structured_json_posts_carry_real_caption_time_and_counts():
    scraper = InstagramGhostScraper()
    profile = scraper._parse_real_profile(_structured_raw_json(), _og_html(), "hedef")

    assert len(profile.posts) == 2
    first = profile.posts[0]
    assert first.caption == "ilk gönderi"
    assert first.like_count == 12
    assert first.comment_count == 2
    assert first.taken_at is not None and first.taken_at.year == 2024
    # eksik alan uydurulmaz
    second = profile.posts[1]
    assert second.caption is None
    assert second.like_count is None


def test_meta_only_page_leaves_temporal_fields_honestly_none():
    """Yapısal JSON yoksa regex URL kurtarır; caption/time/like UYDURULMAZ."""
    html = _og_html() + '<script>..."display_url":"https://scontent.cdn.example/fallback.jpg"...</script>'
    scraper = InstagramGhostScraper()
    profile = scraper._parse_real_profile({"_source": "meta_tags"}, html, "hedef")

    assert len(profile.posts) == 1
    post = profile.posts[0]
    assert post.caption is None
    assert post.taken_at is None
    assert post.like_count is None
    assert post.comment_count is None


# ------------------------------------------------------------------ #
# [028] retry tükenmesi terminal sonuç gönderir
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_triple_executor_failure_emits_terminal_result_error():
    executor = MagicMock()
    executor.execute_task = AsyncMock(side_effect=RuntimeError("boom"))

    errors = []
    results = []

    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result", side_effect=lambda *a: results.append(a)), \
         patch("backend.api.broadcast_result_error", side_effect=lambda *a: errors.append(a)):
        await run_mission(InitiatePayload(
            client_id="fx_triple", url="",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="instagram",
        ))

    assert executor.execute_task.await_count == 3
    assert results == [], "başarı mesajı gidemez"
    assert errors and errors[0][0] == "fx_triple"
    assert errors[-1][1] == "failed", "[028] UI sonsuz 'işleniyor' durumunda bırakıldı"


@pytest.mark.asyncio
async def test_first_failure_then_success_still_returns_result():
    calls = {"n": 0}

    async def flaky(payload, task_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("geçici")
        return MagicMock(status="completed")

    executor = MagicMock()
    executor.execute_task = flaky

    results, errors = [], []
    with patch("backend.api.get_room", return_value={}), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result", side_effect=lambda *a: results.append(a)), \
         patch("backend.api.broadcast_result_error", side_effect=lambda *a: errors.append(a)):
        await run_mission(InitiatePayload(
            client_id="fx_flaky", url="",
            rituals="", playlist="", envies="",
            aggressiveness=1.0, evidence_th=3, scraper_type="instagram",
        ))

    assert len(results) == 1
    assert errors == []


# ------------------------------------------------------------------ #
# [029] benzersiz task_id
# ------------------------------------------------------------------ #
def test_task_ids_are_unique_and_memory_safe():
    ids = {_new_task_id() for _ in range(500)}
    assert len(ids) == 500
    pattern = re.compile(r"^[a-zA-Z0-9_-]+$")  # CanonicalMemory._validate_task_id
    for tid in ids:
        assert pattern.match(tid), tid


# ------------------------------------------------------------------ #
# [030]/[031] shadow wiring
# ------------------------------------------------------------------ #
def test_executor_shares_keyed_gateway_with_shadow():
    from agent_core.task_executor import PinealExecutor

    executor = PinealExecutor()
    assert executor.agents["shadow_executor"].llm_gateway is executor.llm_gateway, (
        "[030] shadow yetimsiz gateway ile çalışıyor"
    )


@pytest.mark.asyncio
async def test_shadow_mirror_receives_payload_contract_user_fields():
    from agent_core.shadow.shadow_executor import ShadowExecutor

    shadow = ShadowExecutor()
    captured = {}

    async def fake_mirror(input_data):
        captured.update(input_data)
        return MagicMock(model_dump=lambda: {"alignment_score": 0.0})

    shadow.mirror = types.SimpleNamespace(execute=fake_mirror)

    async def failing_pattern(*args, **kwargs):
        raise RuntimeError("pattern LLM yok")

    shadow.pattern = types.SimpleNamespace(execute=failing_pattern)
    shadow.dark_triad = types.SimpleNamespace(
        analyze=lambda p: types.SimpleNamespace(
            model_dump=lambda: {},
            machiavellianism=0.0,
            narcissism=0.8,
            psychopathy=0.0,
            exploitability=0.5,
        ),
        generate_strategy=lambda d: {"vector": "mirroring", "tactic": "x"},
    )

    result = await shadow.execute({
        "target_profile": {"bio": "biyografi", "posts": ["gönderi"]},
        "user_profile": {
            "private_rituals": ["gece koşusu"],
            "late_night_playlist": ["neşet ertaş"],
            "secret_envies": ["bağ"],
        },
        "user_context": {"rituals": "gece koşusu", "playlist": "neşet ertaş", "envies": "bağ"},
    })

    assert result.data_confidence is True
    assert result.confidence == 0.8
    assert result.trait_scores_measured is True
    assert captured.get("user_profile", {}).get("private_rituals") == ["gece koşusu"], (
        "[031] kullanıcı ritüelleri mirror'a ulaşmıyor"
    )
    assert captured.get("user_context", {}).get("playlist") == "neşet ertaş"


# ------------------------------------------------------------------ #
# [035] geçici görseller her çıkış yolunda silinir
# ------------------------------------------------------------------ #
@pytest.mark.asyncio
async def test_temp_images_removed_on_success():
    from agent_core.task_executor import PinealExecutor

    executor = PinealExecutor()
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(b"x")
    tmp.close()
    input_data = {"_downloaded_temp_images": [tmp.name], "target_profile": {}}

    async def fake_impl(data, task_id):
        return MagicMock(status="completed")

    executor._execute_task_impl = fake_impl
    await executor.execute_task(input_data, "fx_tmp_ok")
    assert not os.path.exists(tmp.name)
    assert "_downloaded_temp_images" not in input_data


@pytest.mark.asyncio
async def test_temp_images_removed_on_crash():
    from agent_core.task_executor import PinealExecutor

    executor = PinealExecutor()
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(b"x")
    tmp.close()
    input_data = {"_downloaded_temp_images": [tmp.name], "target_profile": {}}

    async def exploding_impl(data, task_id):
        raise RuntimeError("patladı")

    executor._execute_task_impl = exploding_impl
    with pytest.raises(RuntimeError):
        await executor.execute_task(input_data, "fx_tmp_crash")
    assert not os.path.exists(tmp.name), "[035] crash yolunda görsel temp'te kaldı"


@pytest.mark.asyncio
async def test_api_x_sensor_profile_is_merged_without_search_dossier_fallback():
    """The direct x_profile producer reaches execute_task with unknown metrics intact."""
    from types import SimpleNamespace

    x_profile = {
        "username": "@target",
        "name": "target",
        "bio": "",
        "posts": ["Observed X post"],
        "post_times": ["2026-10-01T22:30:00+00:00"],
        "posts_meta": [{"like_count": 3}],
        "post_types": ["text"],
        "images": [],
        "followers": None,
        "following": 0,
        "is_private": None,
        "platform": "x",
    }
    seen = {}

    async def _execute(payload, task_id):
        seen["payload"] = payload
        seen["task_id"] = task_id
        return SimpleNamespace(status="completed", task_id=task_id)

    search = SimpleNamespace(
        set_policy=MagicMock(),
        search=AsyncMock(side_effect=AssertionError("successful X sensor must not use web fallback")),
    )
    executor = SimpleNamespace(search_engine=search, execute_task=_execute)
    results, errors = [], []
    with patch("backend.api.get_executor", return_value=executor), \
         patch("backend.api.get_vault", return_value={}), \
         patch("backend.api.scrape_x", new=AsyncMock(return_value=x_profile)) as scrape, \
         patch("backend.api._check_vault_interlock", return_value=True), \
         patch("backend.api.broadcast_log"), \
         patch("backend.api.broadcast_result", side_effect=lambda *a: results.append(a)), \
         patch("backend.api.broadcast_result_error", side_effect=lambda *a: errors.append(a)):
        await run_mission(InitiatePayload(
            client_id="fx_x_profile",
            url="https://x.com/target",
            rituals="",
            playlist="",
            envies="",
            scraper_type="x",
        ), task_id="op_x_contract")

    scrape.assert_awaited_once()
    search.search.assert_not_awaited()
    profile = seen["payload"]["target_profile"]
    assert profile["platform"] == "x"
    assert profile["posts"] == ["Observed X post"]
    assert profile["post_times"] == ["2026-10-01T22:30:00+00:00"]
    assert profile["followers"] is None
    assert profile["following"] == 0
    assert profile["bio"] == ""
    assert len(results) == 1
    assert errors == []
