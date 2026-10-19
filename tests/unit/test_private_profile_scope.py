"""Privacy boundary and public-metadata handling for private Instagram profiles."""

import asyncio

from agent_core.scraper.instagram_ghost import InstagramProfile
from agent_core.services.cross_profiler import correlate_profiles
from agent_core.services.platform_registry import check_scrape_confidence, ig_target_profile_update


def test_private_profile_is_mapped_as_metadata_only():
    profile = InstagramProfile(
        username="private_example", full_name="Example", biography="Public bio",
        external_url="https://example.org", bio_links=["https://example.org/about"],
        is_private=True, follower_count=42, posts=[],
    )

    class Scorer:
        @staticmethod
        def evaluate_confidence(_profile):
            return 0.4

    assert check_scrape_confidence(Scorer(), profile, lambda *_: None) == 0.4
    mapped = ig_target_profile_update(profile)
    assert mapped["profile_access"] == "metadata_only"
    assert mapped["bio"] == "Public bio"
    assert mapped["posts"] == []
    assert mapped["is_private"] is True


def test_private_target_does_not_expand_into_identity_graph():
    result = correlate_profiles(
        {
            "platform": "instagram", "username": "private_example",
            "is_private": True, "bio": "See https://example.org",
            "detected_urls": ["https://x.com/private_example"],
        },
        {"username_scan": {"found_sites": [
            {"site": "github", "url": "https://github.com/private_example"},
        ]}},
    )
    assert result.matches == []
    assert result.items == []


def test_private_profile_executor_returns_metadata_only_without_running_agents():
    from agent_core.domain.pipeline_status import PipelineStatus
    from agent_core.task_executor import PinealExecutor

    executor = object.__new__(PinealExecutor)
    snapshots = []
    events = []
    logs = []
    executor._snapshot = snapshots.append
    executor._emit = events.append
    executor._log = lambda level, message: logs.append((level, message))

    result = asyncio.run(executor._execute_task_impl({
        "target_profile": {
            "platform": "instagram", "username": "@private_example",
            "full_name": "Example", "bio": "Public bio",
            "followers": 42, "following": 7,
            "external_url": "https://example.org",
            "bio_links": ["https://example.org/about"],
            "is_private": True, "posts": [],
            "detected_urls": ["https://x.com/private_example"],
        },
    }, "private-scope-test"))

    assert result.status == PipelineStatus.PARTIALLY_COMPLETED
    assert result.telemetry["result_kind"] == "public_profile_metadata_only"
    assert result.telemetry["profile_metadata"]["bio"] == "Public bio"
    assert result.telemetry["profile_metadata"]["posts"] == []
    assert snapshots == [result]
    assert len(events) == 2  # lifecycle still completes for the UI
