"""FAZ D · D2 — YEREL JÜRİ: bağımsız koltuklar, açık kural, uydurma yok.

Kilitlenen iddialar:
    * Uç YALNIZ yereldir; uzak adres reddedilir ve uzak adres verildiğinde
      yerel sunucuya BİLE gidilmez (sessiz düşüş yok).
    * Koltuk = ayrı model; tekrar eden model ikinci koltuk sayılmaz.
    * Kural açıkça yazılır: oy_birligi · cokluk · berabere · gecerli_oy_yok ·
      tek_koltuk. Yeter sayı karşılanmadan ``consensus`` true olamaz.
    * Koltuk hataları ve sözlük dışı oylar SESSİZCE yutulmaz.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agent_core.services import local_jury
from agent_core.services.jury_consensus import (
    VOTE_CONTRADICTED,
    VOTE_FALSE,
    VOTE_UNKNOWN,
    VOTE_VERIFIED,
)

CLAIM = "Hedef hesap 2021'den beri aktif."
EVIDENCE = "Arşiv kaydı: ilk gönderi 2021-03-04."


class _LocalLLM:
    """Yerel OpenAI-uyumlu uç taklidi: model başına oy haritası."""

    def __init__(self, votes: dict[str, object], *, status: int = 200, raw: str | None = None):
        self.votes = votes
        self.status = status
        self.raw = raw
        self.hits: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                model = request.get("model", "")
                outer.hits.append(model)
                if outer.status >= 400:
                    self.send_response(outer.status)
                    self.end_headers()
                    return
                if outer.raw is not None:
                    content = outer.raw
                else:
                    vote = outer.votes.get(model, "DOĞRULANDI")
                    if isinstance(vote, dict):
                        content = json.dumps(vote, ensure_ascii=False)
                    else:
                        content = json.dumps({"vote": vote, "confidence": 0.7, "reason": "test"})
                body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(autouse=True)
def _clean_jury_env(monkeypatch):
    """Hermetik: jüri ucu/modelleri her testte açıkça kurulur."""
    for name in (
        "PINEAL_JURY_LOCAL_URL",
        "PINEAL_JURY_LOCAL_MODELS",
        "PINEAL_JURY_SEATS",
        "PINEAL_JURY_QUORUM",
        "LOCAL_LLM_URL",
        "LOCAL_LLM_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture()
def stubs():
    created: list[_LocalLLM] = []
    yield created
    for stub in created:
        stub.close()


def _configure(monkeypatch, stub: _LocalLLM, models: str, **extra) -> None:
    """Jüriyi bu testin yerel ucuna ve modellerine bağlar (tek env kaynağı)."""
    monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", stub.url)
    monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", models)
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


class TestEndpointPolicy:
    def test_default_endpoint_is_local(self):
        url, reason = local_jury.local_endpoint()
        assert url == "http://127.0.0.1:11434/v1" and reason == ""

    def test_remote_endpoint_is_rejected(self, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", "https://api.openai.com/v1")
        url, reason = local_jury.local_endpoint()
        assert url == "" and reason == "non_local_endpoint"

    def test_gateway_local_url_is_reused(self, monkeypatch):
        # Tek kaynak: gateway'in LOCAL_LLM_URL'i ile aynı değişken okunur.
        monkeypatch.setenv("LOCAL_LLM_URL", "http://127.0.0.1:8080/v1")
        url, _ = local_jury.local_endpoint()
        assert url == "http://127.0.0.1:8080/v1"

    def test_remote_configuration_never_falls_back_to_local(self, stubs, monkeypatch):
        stub = _LocalLLM({"a": VOTE_VERIFIED})
        stubs.append(stub)
        # Uzak adres + yerel modeller: uzak REDDEDİLİR, yerel sunucuya gidilmez.
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", "https://uzak.example.com/v1")
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "a")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.available is False
        assert verdict.reason == "non_local_endpoint"
        assert stub.hits == []


class TestSeatModels:
    def test_models_parsed_in_order(self, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1, m2 ,m3")
        models, duplicates = local_jury.seat_models()
        assert models == ["m1", "m2", "m3"] and duplicates == []

    def test_duplicates_are_not_extra_seats(self, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2,m1")
        models, duplicates = local_jury.seat_models()
        assert models == ["m1", "m2"] and duplicates == ["m1"]

    def test_seat_cap_applies(self, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "a,b,c,d,e,f,g")
        monkeypatch.setenv("PINEAL_JURY_SEATS", "3")
        models, _ = local_jury.seat_models()
        assert models == ["a", "b", "c"]

    def test_falls_back_to_gateway_local_model(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_MODEL", "dolphin-llama3:latest")
        models, _ = local_jury.seat_models()
        assert models == ["dolphin-llama3:latest"]

    def test_no_models_means_unavailable(self):
        available, reason = local_jury.availability()
        assert available is False and reason == "no_local_models"

    def test_status_is_honest_about_single_model(self, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "tek-model")
        status = local_jury.status()
        assert status["available"] is True
        assert status["independent_seats"] is False
        assert "konsensüs" in status["note"]


def _run(coro):
    import asyncio

    return asyncio.run(coro)


class TestAggregation:
    def test_unanimity_is_consensus(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED, "m2": VOTE_VERIFIED, "m3": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2,m3")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.available is True
        assert verdict.verdict == VOTE_VERIFIED
        assert verdict.rule == "oy_birligi"
        assert verdict.consensus is True
        assert verdict.tally == {VOTE_VERIFIED: 3}
        assert sorted(stub.hits) == ["m1", "m2", "m3"]

    def test_majority_wins_with_dissent_recorded(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_FALSE, "m2": VOTE_FALSE, "m3": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2,m3")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.verdict == VOTE_FALSE
        assert verdict.rule == "cokluk"
        assert verdict.consensus is True
        assert verdict.dissent == ["m3"]

    def test_tie_is_unknown_not_invented(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED, "m2": VOTE_CONTRADICTED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.verdict == VOTE_UNKNOWN
        assert verdict.rule == "berabere"
        assert verdict.consensus is False

    def test_quorum_gate_blocks_thin_consensus(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED, "m2": VOTE_VERIFIED, "m3": "BOŞ LAF"})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2,m3", PINEAL_JURY_QUORUM="3")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.counted == 2
        assert verdict.consensus is False
        assert "yeter sayı" in verdict.machine_note

    def test_single_seat_is_not_consensus(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.rule == "tek_koltuk"
        assert verdict.consensus is False
        assert verdict.verdict == VOTE_VERIFIED  # karar o koltuktan gelir, ama konsensüs değil


class TestHonestFailures:
    def test_invalid_vocabulary_is_not_counted(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED, "m2": "kesinlikle doğru", "m3": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2,m3")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.counted == 2
        rejected = [vote for vote in verdict.votes if vote.error]
        assert len(rejected) == 1 and rejected[0].error == "sozluk_disi"
        assert rejected[0].raw_vote == "kesinlikle doğru"

    def test_unparseable_output_is_reported(self, stubs, monkeypatch):
        stub = _LocalLLM({}, raw="Elbette, bence doğru görünüyor!")
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.rule == "gecerli_oy_yok"
        assert verdict.votes[0].error == "seat_unparseable"

    def test_http_error_records_seat_error(self, stubs, monkeypatch):
        stub = _LocalLLM({}, status=500)
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.votes[0].error == "seat_status:500"
        assert verdict.available is True  # jüri koştu; karar üretemedi
        assert verdict.rule == "gecerli_oy_yok"

    def test_surviving_seat_still_counts(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED, "m2": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.counted == 2 and verdict.consensus is True

    def test_unreachable_endpoint_is_honest(self, monkeypatch):
        monkeypatch.setenv("PINEAL_JURY_LOCAL_URL", "http://127.0.0.1:1/v1")
        monkeypatch.setenv("PINEAL_JURY_LOCAL_MODELS", "m1,m2")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.available is True
        assert verdict.rule == "gecerli_oy_yok"
        assert all(vote.error.startswith("seat_request_failed:") for vote in verdict.votes)


class TestInputs:
    def test_empty_claim_is_rejected(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1")
        verdict = _run(local_jury.evaluate("", EVIDENCE))
        assert verdict.available is False and verdict.reason == "empty_claim"

    def test_empty_evidence_is_rejected(self, stubs, monkeypatch):
        stub = _LocalLLM({"m1": VOTE_VERIFIED})
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1")
        verdict = _run(local_jury.evaluate(CLAIM, "  "))
        assert verdict.available is False and verdict.reason == "empty_evidence"

    def test_confidences_average_into_no_single_truth(self, stubs, monkeypatch):
        stub = _LocalLLM(
            {
                "m1": {"vote": VOTE_VERIFIED, "confidence": 0.9, "reason": "a"},
                "m2": {"vote": VOTE_VERIFIED, "confidence": 0.5, "reason": "b"},
            }
        )
        stubs.append(stub)
        _configure(monkeypatch, stub, "m1,m2")
        verdict = _run(local_jury.evaluate(CLAIM, EVIDENCE))
        assert verdict.consensus is True
        assert {vote.confidence for vote in verdict.votes} == {0.9, 0.5}
