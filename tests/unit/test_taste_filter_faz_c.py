"""FAZ C · C1 — JENERİK YANIT FİLTRESİ sözleşme testleri.

Kilitlenen iddialar:
1. Jenerik laf salatası ÖLÇÜLÜR (deterministik; LLM yok) ve KULLANICIYA ÇIKMAZ.
2. En ağır sinyal: elde VERİ varken yanıtın o veriye hiç değinmemesi.
3. Düşen yanıtın yerine kanıttan derlenmiş DÜRÜST cümle konur; veri yoksa
   "yok" denir, uydurulmaz.
4. Telemetri: düşen her yanıt, nedeniyle birlikte yazılır (operatör görür).
5. Eşik kalibrasyon disiplinine bağlıdır: elle sabitlenebilir, ölçülmeden
   değişmez.
6. Normal (kanıta dayalı, kısa) yanıtlara DOKUNULMAZ.
"""

from __future__ import annotations

import json
import os

import pytest

from agent_core.services import taste_filter


GENERIC = (
    "Tabii ki! Kesinlikle harika bir soru sormuşsunuz. Elbette size bu konuda "
    "yardımcı olabilirim. Bir yapay zeka olarak genel olarak şunları söyleyebilirim: "
    "belki bu durum, muhtemelen şu şekilde, sanırım böyle olabilir. Daha fazla bilgi "
    "verirseniz size nasıl yardımcı olabilirim, onu da anlatırım. "
    "Çok önemli bir konu, gerçekten oldukça önemli, kesinlikle çok önemli."
)

CONCRETE = (
    "Mösyö, görev fx_1 tamamlandı: 7 sütundan 5'i kanıt üretti, gerçeklik endeksi 0.62. "
    "Kanıt zincirinde 3 alıntı doğrulandı; kalan iki sütun için veri yok."
)


# ------------------------------------------------------------ 1 · ölçüm
def test_generic_answer_scores_high_with_reasons():
    verdict = taste_filter.score_response(GENERIC)
    assert verdict.available is True
    assert verdict.generic_score >= 0.70, verdict.signals
    assert "jenerik açılış" in " ".join(verdict.reasons)
    assert "kalıp sorumluluk reddi" in " ".join(verdict.reasons)
    assert verdict.machine_note.startswith("TASTE:")


def test_concrete_answer_scores_low():
    verdict = taste_filter.score_response(CONCRETE)
    assert verdict.generic_score < 0.30, verdict.signals


def test_data_ignored_is_the_heaviest_signal():
    """Elde veri VAR, yanıt ona hiç değinmiyor -> en ağır sinyal düşer."""
    context = {"verdict": "Görev fx_1: 7 kanıt, gerçeklik 0.62, 3 alıntı doğrulandı."}
    plain = "Tabii ki! Elbette yardımcı olabilirim, harika bir soru."
    without = taste_filter.score_response(plain)
    with_ctx = taste_filter.score_response(plain, context=context)
    assert with_ctx.signals.get("veri_kullanilmadi", 0) >= 0.2
    assert with_ctx.generic_score > without.generic_score


# ---------------------------------------------------------- 2 · düşürme
def test_generic_answer_is_dropped_and_replaced_by_evidence_line():
    context = {"verdict": "HÜKÜM: 7 kanıt kaydı, 3'ü doğrulandı."}
    decision = taste_filter.filter_response(GENERIC, context=context)
    assert decision.kept is False
    assert decision.reason == "jenerik_yanit"
    assert decision.message != GENERIC
    assert "doğrulandı" in decision.message or "kanıt" in decision.message


def test_concrete_answer_passes_untouched():
    decision = taste_filter.filter_response(CONCRETE)
    assert decision.kept is True
    assert decision.message == CONCRETE


def test_replacement_falls_back_to_telemetry_then_honest_absence():
    telemetry = {"telemetry": "Görev: fx_1 | Durum: completed"}
    from_telemetry = taste_filter.filter_response(GENERIC, context=telemetry)
    assert "fx_1" in from_telemetry.message
    assert from_telemetry.kept is False

    empty = taste_filter.filter_response(GENERIC, context={})
    assert "uydurmayacağım" in empty.message, "veri yokken yine de uydurdu"


def test_empty_text_is_never_judged_generic():
    decision = taste_filter.filter_response("")
    assert decision.kept is True
    assert decision.verdict.available is False


# ---------------------------------------------------------- 3 · eşik disiplini
def test_threshold_can_be_pinned_by_operator(monkeypatch):
    monkeypatch.setenv("PINEAL_THRESHOLD_TASTE", "0.20")
    assert taste_filter.threshold() == pytest.approx(0.20)
    # Eşik düşünce orta karar bir yanıt da jenerik sayılır.
    mild = "Tabii ki, belki de öyle olabilir, muhtemelen böyledir."
    assert taste_filter.filter_response(mild).kept is False


def test_default_threshold_stays_unmeasured(monkeypatch):
    monkeypatch.delenv("PINEAL_THRESHOLD_TASTE", raising=False)
    monkeypatch.delenv("PINEAL_THRESHOLD", raising=False)
    assert taste_filter.threshold() == pytest.approx(0.70)


# ------------------------------------------------------------- 4 · telemetri
def test_dropped_answers_are_written_to_telemetry(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_TELEMETRY_DIR", str(tmp_path / "tel"))
    taste_filter.filter_response(GENERIC, context={"verdict": "HÜKÜM: 2 kanıt"})
    taste_filter.filter_response(CONCRETE)  # geçen yanıt yazılmaz

    summary = taste_filter.telemetry_summary()
    assert summary["total"] == 1
    assert summary["dropped"] == 1
    assert summary["top_reasons"], "neden kaydı yok"
    assert summary["machine_note"].startswith("TASTE:")


def test_telemetry_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_TELEMETRY_DIR", str(tmp_path / "tel"))
    monkeypatch.setenv("PINEAL_TASTE_LOG", "false")
    taste_filter.filter_response(GENERIC, context={"verdict": "HÜKÜM: 2 kanıt"})
    assert taste_filter.telemetry_summary()["total"] == 0


def test_telemetry_stores_only_an_excerpt(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_TELEMETRY_DIR", str(tmp_path / "tel"))
    taste_filter.filter_response(GENERIC, context={"verdict": "HÜKÜM: 2 kanıt"})
    path = os.path.join(str(tmp_path / "tel"), "taste.jsonl")
    row = json.loads(open(path, encoding="utf-8").read().strip().splitlines()[0])
    assert len(row["excerpt"]) <= 200
    assert set(row) >= {"recorded_at", "kept", "score", "reasons", "excerpt"}


# --------------------------------------------------------- 5 · determinizm
def test_scoring_is_deterministic():
    first = taste_filter.score_response(GENERIC).model_dump()
    second = taste_filter.score_response(GENERIC).model_dump()
    assert first == second


def test_repetition_and_length_are_penalised():
    repeated = ("Aynı cümleyi tekrar ediyorum. " * 8).strip()
    verdict = taste_filter.score_response(repeated)
    assert verdict.signals.get("tekrar", 0) > 0
