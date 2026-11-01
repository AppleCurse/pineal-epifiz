"""Dalga-1 `PillarBundle` ↔ dalga-2 `FullPillarBundle` köprüsü.

[2026-10-23] Ölçüm: `PillarBundle` üretimde HİÇ çağrılmıyordu; üretim
`FullPillarBundle` (dalga 2) ile koşuyor. İki şema ayrı ayrı yaşadığı için
"ölü ama kırılabilir" durumdaydı: dalga-2'de bir alan değişse dalga-1 görünümü
sessizce yalan söylerdi.

Silmedik; sözleşmeye bağladık:
  * `PillarBundle.from_full(...)` dalga-2 paketini DOĞRULANMIŞ dalga-1
    görünümüne çevirir (eksik alan uydurulmaz, ValidationError yükselir).
  * Alan adları iki şemada AYNI kalmalı — bu test onu kilitler.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent_core.domain.pillar_models import PillarBundle
from agent_core.domain.pillar_wave2_models import FullPillarBundle


def test_from_full_round_trips_the_production_bundle():
    full = FullPillarBundle()
    view = PillarBundle.from_full(full)
    assert view.frequency.model_dump() == full.frequency.model_dump()
    assert view.seismos.model_dump() == full.seismos.model_dump()
    assert view.void.model_dump() == full.void.model_dump()
    # Zaman damgası KAYNAKTAN taşınır (yeni zaman uydurulmaz).
    assert view.computed_at == full.computed_at


def test_from_full_accepts_a_plain_snapshot_dict():
    full = FullPillarBundle()
    snapshot = full.as_snapshot_fields()
    view = PillarBundle.from_full({
        "frequency": snapshot["frequency_map"],
        "seismos": snapshot["seismos_events"],
        "void": snapshot["void_map"],
        "computed_at": full.computed_at.isoformat(),
    })
    assert view.void.model_dump() == full.void.model_dump()


def test_from_full_rejects_garbage_instead_of_inventing_fields():
    with pytest.raises((ValidationError, TypeError)):
        PillarBundle.from_full(None)
    with pytest.raises(ValidationError):
        PillarBundle.from_full({"frequency": {"status": "NOT_A_STATUS"}})


def test_wave1_view_still_produces_snapshot_fields():
    view = PillarBundle.from_full(FullPillarBundle())
    snapshot = view.as_snapshot_fields()
    assert set(snapshot) == {"frequency_map", "seismos_events", "void_map", "pillar_bundle"}
    assert snapshot["pillar_bundle"]["version"] == "pillar-wave1-v1"


def test_both_bundles_share_the_same_pillar_field_names():
    """Şema kayması kilidi: dalga-2 yeni bir sütun eklerse burası kırılır."""
    wave1 = set(PillarBundle.model_fields)
    wave2 = set(FullPillarBundle.model_fields)
    shared = {"frequency", "seismos", "void", "computed_at"}
    assert shared <= wave1, f"dalga-1 görünümü alan kaybetti: {shared - wave1}"
    assert shared <= wave2, f"üretim paketi alan kaybetti: {shared - wave2}"


def test_from_full_preserves_computed_at_type_semantics():
    stamp = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    view = PillarBundle.from_full({"computed_at": stamp})
    assert view.computed_at == stamp
