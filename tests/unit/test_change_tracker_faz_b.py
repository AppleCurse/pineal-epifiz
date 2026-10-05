"""FAZ B · B7 — DEĞİŞİM İZLEME sözleşme testleri.

Soru: "bu hedefi daha önce de taramıştık, NE DEĞİŞTİ?"

Kilitlenen iddialar:
1. Parmak izi kanıdın KENDİSİNDEN üretilir; `evidence_id` kullanılmaz (her
   görevde yeniden üretildiği için her şey "yeni" görünürdü).
2. Önceki kayıt yoksa fark UYDURULMAZ (`available:false` + `no_baseline`).
3. Ekleme / kayıp / değişen DOĞRU ayrıştırılır; değişmeyen sayısı tutar.
4. Kayıt yazma atomiktir ve hedef başına son N anlık görüntü tutulur.
"""

from __future__ import annotations

import json

import pytest

from agent_core.services.change_tracker import (
    ChangeReport,
    build_snapshot,
    diff_snapshots,
    latest_before,
    load_history,
    record_snapshot,
    target_key,
)


def _item(content: str, engine: str = "maigret", site: str = "github", ref: str = "https://github.com/h") -> dict:
    return {
        "evidence_id": "ev_" + str(abs(hash(content)) % 10**20).zfill(20),
        "epistemic_type": "observation",
        "source_engine": engine,
        "content": content,
        "provenance_refs": [ref],
        "scope": {"kind": "identity_presence", "site": site},
    }


# ------------------------------------------------- 1 · kararlı parmak izi
def test_fingerprint_ignores_evidence_id_and_timestamps():
    """Aynı bulgu, farklı evidence_id/observed_at ile de AYNI parmak izini verir."""
    a = build_snapshot([_item("kullanıcı github'da var")], {"username": "hedef"}, task_id="t1")
    b = build_snapshot(
        [
            {
                **_item("kullanıcı github'da var"),
                "evidence_id": "ev_" + "9" * 20,
                "observed_at": "2030-01-01T00:00:00+00:00",
            }
        ],
        {"username": "hedef"},
        task_id="t2",
    )
    assert a.fingerprint == b.fingerprint
    assert diff_snapshots(a, b).available is True
    assert diff_snapshots(a, b).machine_note.startswith("DEĞİŞİM:")


def test_target_key_prefers_username_then_falls_back_to_host():
    assert target_key({"username": "@Hedef"}) == "hedef"
    assert target_key({}, [_item("x", ref="https://www.ornek.com/u")]) == "ornek.com"
    assert target_key({}, []) == ""


# ------------------------------------------------------ 2 · dürüstlük
def test_no_baseline_means_no_invented_diff():
    after = build_snapshot([_item("a")], {"username": "hedef"}, task_id="t1")
    report = diff_snapshots(None, after)
    assert report.available is False
    assert report.reason == "no_baseline"
    assert report.added == [] and report.removed == [] and report.changed == []


def test_missing_either_side_is_not_a_diff():
    only = build_snapshot([_item("a")], {"username": "hedef"}, task_id="t1")
    assert diff_snapshots(only, None).reason == "no_baseline"
    assert diff_snapshots(None, None).available is False


# ------------------------------------------- 3 · ekleme / kayıp / değişen
def test_added_removed_and_changed_are_separated():
    """Kimlik (motor+kapsam+kaynak) aynı, METİN değişmişse -> "değişen"."""
    before = build_snapshot(
        [
            _item("ortak bulgu"),
            _item("silinen bulgu", site="twitter", ref="https://twitter.com/h"),
            _item("metni değişecek bulgu", site="reddit", ref="https://reddit.com/u/h"),
        ],
        {"username": "hedef"},
        task_id="t1",
    )
    after = build_snapshot(
        [
            _item("ortak bulgu"),
            _item("metni DEĞİŞTİ bulgu", site="reddit", ref="https://reddit.com/u/h"),
            _item("yeni bulgu", site="x", ref="https://x.com/h"),
        ],
        {"username": "hedef"},
        task_id="t2",
    )
    report = diff_snapshots(before, after)
    assert report.available is True
    assert len(report.added) == 1      # yeni bulgu (x.com)
    assert len(report.removed) == 1    # silinen bulgu (twitter)
    assert len(report.changed) == 1    # aynı kaynak, farklı metin (reddit)
    assert report.unchanged_count == 1  # ortak bulgu
    assert report.before_task_id == "t1"
    assert report.after_task_id == "t2"


def test_identical_evidence_reports_zero_change():
    items = [_item("aynı bulgu"), _item("ikinci bulgu", site="x")]
    before = build_snapshot(items, {"username": "hedef"}, task_id="t1")
    after = build_snapshot(items, {"username": "hedef"}, task_id="t2")
    report = diff_snapshots(before, after)
    assert report.available is True
    assert (report.added, report.removed, report.changed) == ([], [], [])
    assert report.unchanged_count == 2
    assert "değişim yok" in report.machine_note


def test_content_change_is_reported_as_changed_not_lost():
    """Aynı kaynak, farklı metin -> "değişen"; "kayıp+yeni" DEĞİL."""
    base = _item("eski metin")
    before = build_snapshot([base], {"username": "hedef"}, task_id="t1")
    after = build_snapshot([{**base, "content": "yeni metin"}], {"username": "hedef"}, task_id="t2")
    report = diff_snapshots(before, after)
    assert report.available is True
    assert report.added == [] and report.removed == []
    assert len(report.changed) == 1
    assert report.unchanged_count == 0


# ------------------------------------------------------------ 4 · depolama
def test_record_and_reload_history(tmp_path):
    storage = str(tmp_path / "memory")
    first = build_snapshot([_item("a")], {"username": "hedef"}, task_id="t1")
    record_snapshot(storage, first)
    second = build_snapshot([_item("a"), _item("b", site="x")], {"username": "hedef"}, task_id="t2")
    record_snapshot(storage, second)

    history = load_history(storage, "hedef")
    assert [s.task_id for s in history] == ["t1", "t2"]
    # "kendisi hariç en son": t2 için önceki t1; t1 için t2 (kendisi DEĞİL).
    assert latest_before(storage, "hedef", "t2").task_id == "t1"
    assert latest_before(storage, "hedef", "t1").task_id == "t2"
    assert latest_before(storage, "hedef", "yok") .task_id == "t2"


def test_history_is_capped(tmp_path):
    storage = str(tmp_path / "memory")
    for i in range(14):
        record_snapshot(
            storage,
            build_snapshot([_item(f"b{i}")], {"username": "hedef"}, task_id=f"t{i}"),
            keep=5,
        )
    history = load_history(storage, "hedef")
    assert len(history) == 5
    assert [s.task_id for s in history] == ["t9", "t10", "t11", "t12", "t13"]


def test_history_file_is_valid_json(tmp_path):
    storage = str(tmp_path / "memory")
    record_snapshot(storage, build_snapshot([_item("a")], {"username": "hedef"}, task_id="t1"))
    with open(tmp_path / "memory" / "changes" / "hedef.json", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["target"] == "hedef"
    assert payload["snapshots"][0]["entry_count"] == 1


def test_report_model_rejects_unknown_fields():
    with pytest.raises(Exception):
        ChangeReport(available=True, uydurma=1)  # type: ignore[call-arg]
