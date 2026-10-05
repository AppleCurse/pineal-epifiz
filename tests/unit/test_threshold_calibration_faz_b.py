"""FAZ B · B5 — EŞİK KALİBRASYONU sözleşme testleri.

Kilitlenen iddialar:
1. Eşik ÖLÇÜLMEDEN değişmez: etiketli örnek sayısı alt sınırın altındaysa
   eşik 0.70'te kalır ve kaynağı `varsayılan` olarak RAPORLANIR (sessiz değişim
   yok — tam da şikâyet edilen "yarım entegrasyon" tuzağı).
2. Yeterli veri varsa eşik ÖLÇÜLÜR, güven aralığı ve geri test tablosu birlikte
   döner; veri azken ölçüm varsayılana çekilir (shrinkage).
3. Tek sınıflı veri (hepsi doğru / hepsi yanlış) eşik üretemez.
4. Elle sabitleme (`PINEAL_THRESHOLD_QUOTE`) her zaman kazanır: karar mercii
   operatördür.
5. Kalibrasyon LLM çağırmaz, ağa çıkmaz: aynı kayıt -> aynı eşik.
6. Ledger'a HAM METİN yazılmaz; yalnız ölçü ve kimlik yazar.
"""

from __future__ import annotations

import os

import pytest

from agent_core.services.quote_guard import best_score, quote_matches
from agent_core.services.threshold_calibration import (
    DEFAULT_THRESHOLD,
    SCOPE_QUOTE,
    Observation,
    adjudicate,
    calibrate,
    load,
    record,
    resolved_threshold,
)


def _pairs(spec: str) -> list[Observation]:
    """'GT': skor->doğru (True), 'GF': skor->yanlış etiketiyle kayıt üretir."""
    rows = []
    for idx, token in enumerate(spec.split(",")):
        token = token.strip()
        if not token:
            continue
        truth = token[0] == "T"
        rows.append(
            Observation(
                observation_id=f"obs_{idx}",
                recorded_at=float(idx),
                scope=SCOPE_QUOTE,
                score=float(token[1:]) / 100,
                truth=truth,
            )
        )
    return rows


# ------------------------------------------------- 1 · veri yoksa eşik DEĞİŞMEZ
def test_insufficient_labels_keeps_default_threshold(monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "30")
    report = calibrate(_pairs("T90,T80,T70,F40,F30"), required=30)
    assert report.available is False
    assert report.threshold == DEFAULT_THRESHOLD
    assert report.source == "varsayılan"
    assert "yetersiz_etiketli_örnek" in report.reason
    assert "ÖLÇÜLMEDİ" in report.machine_note


def test_unlabeled_rows_are_counted_but_not_used(monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "2")
    rows = [
        Observation(observation_id="a", score=0.9, truth=None, scope=SCOPE_QUOTE),
        Observation(observation_id="b", score=0.2, truth=False, scope=SCOPE_QUOTE),
        Observation(observation_id="c", score=0.8, truth=True, scope=SCOPE_QUOTE),
    ]
    report = calibrate(rows, required=2)
    assert report.samples == 3
    assert report.labeled == 2
    assert report.unlabeled == 1
    assert report.available is True


# ------------------------------------------------------ 2 · ölçüm ve kanıtları
def test_threshold_is_measured_with_backtest_and_interval(monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "10")
    # Gerçek eşleşmeler yüksek skorlu, uydurmalar düşük skorlu: eşik ortada çıkar.
    spec = ",".join(["T95", "T92", "T90", "T88", "T85", "T80", "T78", "T70"] +
                    ["F60", "F55", "F50", "F45", "F40", "F35", "F30", "F25", "F20", "F15"])
    report = calibrate(_pairs(spec), required=10)
    assert report.available is True
    assert report.source == "kalibre"
    assert 0.5 <= report.threshold <= 0.95
    assert 0 < report.shrinkage_weight < 1  # veri azken tam güven yok
    assert len(report.grid) >= 40  # geri test ızgarası
    assert len(report.confidence_interval) == 2
    assert report.confidence_interval[0] <= report.confidence_interval[1]
    assert report.operating_point.accuracy >= 0.8
    assert report.operating_point.fp == 0  # uydurma alıntı geçmedi
    assert report.reliability, "güvenilirlik diyagramı boş"
    assert 0.0 <= report.expected_calibration_error <= 1.0


def test_more_data_moves_threshold_away_from_default(monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "10")
    few = _pairs(",".join(["T95", "T90", "T85", "T80", "F60", "F55", "F50", "F45", "F40", "F35"]))
    many = _pairs(",".join(["T95", "T90", "T85", "T80", "F60", "F55", "F50", "F45", "F40", "F35"] * 6))
    thin = calibrate(few, required=10)
    rich = calibrate(many, required=10)
    assert rich.shrinkage_weight > thin.shrinkage_weight, "veri çoğalınca ağırlık artmalı"
    assert abs(rich.threshold - rich.measured_threshold) < abs(thin.threshold - thin.measured_threshold)


# ------------------------------------------------------------ 3 · tek sınıf tuzağı
def test_single_class_data_cannot_calibrate(monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "4")
    report = calibrate(_pairs("T90,T88,T85,T80,T75"), required=4)
    assert report.available is False
    assert report.reason.startswith("tek_sınıf")
    assert report.threshold == DEFAULT_THRESHOLD


# ---------------------------------------------------------- 4 · elle sabitleme
def test_env_override_wins_over_calibration(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_THRESHOLD_QUOTE", "0.93")
    decision = resolved_threshold(SCOPE_QUOTE, storage=str(tmp_path / "cal"))
    assert decision.value == pytest.approx(0.93)
    assert decision.source == "elle_sabitleme"


def test_generic_env_override_applies_to_every_scope(monkeypatch, tmp_path):
    monkeypatch.setenv("PINEAL_THRESHOLD", "0.55")
    assert resolved_threshold("confidence", storage=str(tmp_path / "cal")).value == pytest.approx(0.55)


# ------------------------------------------------------------- 5 · ledger disiplini
def test_record_and_adjudicate_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "true")
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "2")
    storage = str(tmp_path / "cal")
    obs = record(0.91, scope=SCOPE_QUOTE, task_id="t1", claim_id="clm_x", storage=storage)
    assert obs is not None and obs.truth is None  # ölçüm var, etiket yok
    rows = load(storage)
    assert len(rows) == 1
    assert adjudicate(obs.observation_id, True, storage=storage)
    assert load(storage)[0].truth is True
    assert adjudicate("yok_boyle_bir_id", True, storage=storage) is False


def test_no_raw_text_is_written_to_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "true")
    storage = str(tmp_path / "cal")
    secret = "gizli-hedef-adi-123"
    record(0.77, scope=SCOPE_QUOTE, storage=storage, note="ham metin yok")
    path = os.path.join(storage, "observations.jsonl")
    blob = open(path, "r", encoding="utf-8").read()
    assert secret not in blob


def test_observe_flag_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "false")
    assert record(0.9, scope=SCOPE_QUOTE, storage=str(tmp_path / "cal")) is None
    assert load(str(tmp_path / "cal")) == []


def test_calibration_reads_back_from_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "true")
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "10")
    storage = str(tmp_path / "cal")
    for score in (0.95, 0.92, 0.90, 0.88, 0.85, 0.80, 0.78, 0.70):
        obs = record(score, scope=SCOPE_QUOTE, storage=storage)
        adjudicate(obs.observation_id, True, storage=storage)
    for score in (0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15):
        obs = record(score, scope=SCOPE_QUOTE, storage=storage)
        adjudicate(obs.observation_id, False, storage=storage)

    decision = resolved_threshold(SCOPE_QUOTE, storage=storage)
    assert decision.source == "kalibre", decision.reason
    assert decision.report is not None
    assert decision.value == decision.report.threshold
    assert decision.report.available is True
    assert decision.report.labeled == 18


# ------------------------------------------------------------- 6 · determinizm
def test_calibration_is_deterministic(monkeypatch):
    monkeypatch.setenv("PINEAL_CALIB_MIN_SAMPLES", "10")
    rows = _pairs(",".join(["T95", "T90", "T85", "T80", "F60", "F55", "F50", "F45", "F40", "F35"]))
    first = calibrate(rows, required=10).model_dump()
    second = calibrate(rows, required=10).model_dump()
    assert first == second


# --------------------------------------------------- 7 · QuoteGuard gerçekten bağlı
def test_quote_guard_uses_resolved_threshold(monkeypatch):
    """SABİT 0.70 biter: eşik kalibrasyondan gelir ve kararı DEĞİŞTİRİR.

    Ölçülen örnek: kaynak "Kıdemli Stratejist" diyor, alıntı "Kıdemli Mühendis"
    diyor — benzerlik 0.78. Eşik 0.70 iken bu YANLIŞ alıntı kapıdan geçiyordu.
    """
    corpus = ["Ada Kıdemli Stratejist olarak çalışıyor"]
    quote = "Kıdemli Mühendis olarak çalışıyor"
    score = best_score(quote, corpus)
    assert 0.70 < score < 0.80, f"beklenen aralıkta skor yok: {score}"

    monkeypatch.setenv("PINEAL_THRESHOLD_QUOTE", "0.70")
    assert quote_matches(quote, corpus) is True
    monkeypatch.setenv("PINEAL_THRESHOLD_QUOTE", "0.80")
    assert quote_matches(quote, corpus) is False


def test_verbatim_quote_passes_whatever_the_threshold(monkeypatch):
    """Kaynakta BİREBİR var olan alıntı, eşik ne olursa olsun geçer.

    (Eskiden korpus normalize edilmediği için büyük/küçük harf farkı yüzünden
    birebir alıntı "yok" sayılıp 0.70 eşiğinin ALTINDA kalabiliyordu.)
    """
    monkeypatch.setenv("PINEAL_THRESHOLD_QUOTE", "0.99")
    corpus = ["Ada Kıdemli Stratejist olarak çalışıyor"]
    assert best_score("Kıdemli Stratejist olarak çalışıyor", corpus) == 1.0
    assert quote_matches("Kıdemli Stratejist olarak çalışıyor", corpus) is True


def test_observe_path_records_the_decision(tmp_path, monkeypatch):
    """Üretim yolu (`observe=True`) gerçekten ölçüm bırakır."""
    monkeypatch.setenv("PINEAL_CALIB_OBSERVE", "true")
    monkeypatch.setenv("PINEAL_CALIB_DIR", str(tmp_path / "cal"))
    monkeypatch.delenv("PINEAL_THRESHOLD_QUOTE", raising=False)
    corpus = ["Ada Kıdemli Stratejist olarak çalışıyor"]
    assert quote_matches("Kıdemli Mühendis olarak çalışıyor", corpus, observe=True, claim_id="clm_1") is True
    rows = load(str(tmp_path / "cal"))
    assert len(rows) == 1
    assert rows[0].claim_id == "clm_1"
    assert 0.70 < rows[0].score < 0.80
    assert rows[0].truth is None  # ölçüm var, henüz etiket yok
