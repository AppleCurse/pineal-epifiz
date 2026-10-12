"""X yetki sonrası alternatif public-web araştırma sözleşmesi.

Kurallar:
- Sahte biyografi/gönderi/kişilik ÜRETİLMEZ; yalnızca gerçek arama
  kayıtları döner (source_url + provider + content).
- Subject matching: hedef kullanıcı adı URL'de veya içerikte geçmeyen
  sonuçlar düşürülür.
- Sağlayıcı yok -> available=False; sonuç yok -> sıfır + dürüst note.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent_core.services.search_engine import SearchOutcome, SearchResult
from backend.api import (
    _extract_handle_from_url,
    _run_public_web_research,
    app,
    get_room,
)


class _FakeSearch:
    def __init__(self, outcome):
        self._outcome = outcome

    async def search(self, query, num_results=5):
        self.last_query = query
        return self._outcome


def _outcome(*results):
    return SearchOutcome(results=list(results), status="OK", available=True)


@pytest.mark.asyncio
async def test_extract_handle_from_urls():
    assert _extract_handle_from_url("https://x.com/SomeUser?lang=tr") == "someuser"
    assert _extract_handle_from_url("https://twitter.com/@TestUser") == "testuser"
    assert _extract_handle_from_url("https://instagram.com/photo.fan") == "photo.fan"
    assert _extract_handle_from_url("https://example.com/not-a-target") == "not-a-target"
    assert _extract_handle_from_url("") == ""


@pytest.mark.asyncio
async def test_subject_matching_keeps_only_target_results():
    engine = _FakeSearch(_outcome(
        SearchResult(query="x", content="Alper'in blogu hakkında bir yazı",
                     source_url="https://blog.example.com/alper", provider="tavily"),
        SearchResult(query="x", content="Başka biriyle ilgili içerik",
                     source_url="https://blog.example.com/other", provider="tavily"),
    ))
    research = await _run_public_web_research("https://x.com/alper", engine)

    assert research["status"] == "ok"
    assert research["available"] is True
    assert research["matched_username"] == "alper"
    assert research["total_results_searched"] == 2
    assert len(research["results"]) == 1
    assert research["results"][0]["source_url"].endswith("/alper")
    assert research["results"][0]["subject_match"] is True
    assert engine.last_query == '"alper"'


@pytest.mark.asyncio
async def test_no_subject_match_is_honest_not_empty_ok():
    engine = _FakeSearch(_outcome(
        SearchResult(query="x", content="İlgisiz içerik",
                     source_url="https://blog.example.com/other", provider="tavily"),
    ))
    research = await _run_public_web_research("https://x.com/ghost", engine)
    assert research["status"] == "no_subject_match"
    assert research["results"] == []
    assert "eşleşmedi" in research["note"]


@pytest.mark.asyncio
async def test_unavailable_provider_is_reported():
    engine = _FakeSearch(SearchOutcome(
        results=[], status="UNAVAILABLE", available=False,
        error="RATE_LIMITED",
    ))
    research = await _run_public_web_research("https://x.com/alper", engine)
    assert research["available"] is False
    assert research["status"] == "unavailable"
    assert research["note"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_invalid_target_url():
    research = await _run_public_web_research("", _FakeSearch(_outcome()))
    assert research["status"] == "invalid_target"
    assert research["available"] is False


def test_endpoint_authorize_runs_real_research(vault_open):
    # Ön koşul: kasa AÇIK (bu test mandalı değil, gerçek araştırma akışını ölçer).
    cid = "fx_alt_research"
    with TestClient(app) as client:
        client.websocket_connect  # noqa: B018 — ws kullanılmıyor, HTTP yolu test ediliyor
        room = get_room(cid)
        room["pending_alternative_authorization"] = {
            "url": "https://x.com/alper",
            "requested_at": "2026-08-26T00:00:00",
            "alternatives": ["public_web_search"],
        }
        executor = MagicMock()
        executor.search_engine = _FakeSearch(_outcome(
            SearchResult(query='"alper"', content="alper hakkında kamuya açık yazı",
                         source_url="https://haber.example.com/alper-yazisi", provider="tavily"),
            SearchResult(query='"alper"', content="Başka konu",
                         source_url="https://blog.example.com/x", provider="tavily"),
        ))
        import backend.api as api
        original = api.get_executor
        api.get_executor = lambda _cid: executor
        try:
            r = client.post("/api/scraper/authorize-alternative", json={
                "client_id": cid,
                "alternative": "public_web_search",
                "approved": True,
            })
        finally:
            api.get_executor = original

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "research_completed"
    assert body["research"]["status"] == "ok"
    assert len(body["research"]["results"]) == 1
    saved = room.get("web_research")
    assert saved is not None and saved["matched_username"] == "alper"
    assert "pending_alternative_authorization" not in room
