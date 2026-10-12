import pytest
from agent_core.services.quote_guard import guard_report
from agent_core.services.timing_forensics import analyze_timing
from agent_core.services.follower_audit import audit_followers
from agent_core.services.search_engine import SearchEngine, SearchResult

def test_timing_forensics_arithmetic():
    times = [
        "2026-08-20T02:15:00",
        "2026-08-21T03:30:00",
        "2026-08-22T01:45:00",
        "2026-08-23T14:00:00"
    ]
    res = analyze_timing(times)
    assert res is not None
    assert res["samples"] == 4
    assert res["night_share"] == 0.75  # 3 out of 4 are night
    assert "gece" in res["machine_note"]

def test_follower_audit_inflated():
    posts = [
        {"like_count": 25, "comment_count": 2},
        {"like_count": 30, "comment_count": 1},
        {"like_count": 20, "comment_count": 0}
    ]
    rep = audit_followers(11000, 900, posts)
    assert "ŞİŞİRME" in rep.verdict or "ŞÜPHELİ" in rep.verdict
    assert rep.data_completeness == 1.0

def test_quote_guard_drops_unanchored_findings():
    input_data = {
        "target_profile": {
            "bio": "Sos Music Production Company 🎙",
            "posts": ["Gece stüdyo kayıtları devam ediyor"]
        },
        "visual_evidence": {
            "detected_objects": ["yelkenli tekne", "şarap kadehi"]
        }
    }
    
    dirty_report = {
        "reality_findings": [
            {
                "topic": "Müzik Şirketi",
                "observation": "Gerçek şirket kimliği var",
                "evidence_quotes": ["Sos Music Production Company 🎙"]
            },
            {
                "topic": "Uzay Yolculuğu",
                "observation": "Mars'a roket fırlattı",
                "evidence_quotes": ["Mars Roketi Uçuşu 2026"]
            }
        ],
        "contradictions": [
            {
                "topic": "Tekne Lüksü",
                "observation": "Deniz aktiviteleri sergileniyor",
                "evidence_quotes": ["yelkenli tekne"]
            }
        ]
    }
    
    cleaned, stats = guard_report(dirty_report, input_data)
    assert stats["checked"] == 3
    assert stats["kept"] == 2
    assert stats["dropped_fake_quote"] == 1
    assert len(cleaned["reality_findings"]) == 1
    assert cleaned["reality_findings"][0]["topic"] == "Müzik Şirketi"

@pytest.mark.asyncio
async def test_search_engine_fallback_duckduckgo(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    engine = SearchEngine(tavily_key="", serpapi_key="", exa_key="")
    async def fake_ddg(query, num, **kwargs):
        return [SearchResult(query=query, content="Sos Music Production Records", source_url="https://sosmusic.com", provider="duckduckgo")]
    monkeypatch.setattr(engine, "_search_duckduckgo", fake_ddg)
    
    outcome = await engine.search("Sos Music")
    assert outcome.status == "OK"
    assert len(outcome.results) == 1
    assert outcome.results[0].provider == "duckduckgo"
