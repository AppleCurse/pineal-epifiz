from datetime import datetime, timedelta, timezone
import json
import pytest
from pydantic import ValidationError
from agent_core.domain.pillar_models import EvidenceStatus, FrequencyReport, SeismicKind
from agent_core.domain.pillar_wave2_models import FullPillarBundle
from agent_core.engines.frequency_engine import FrequencyEngine, parse_timestamp
from agent_core.engines.seismos_engine import SeismosEngine
from agent_core.engines.void_engine import VoidEngine
from agent_core.engines.strata_engine import StrataEngine
from agent_core.engines.gravity_engine import GravityEngine
from agent_core.engines.pulse_engine import PulseEngine
from agent_core.engines.pillar_orchestrator import PillarOrchestrator

def data(n=24, gap=12):
    t = datetime(2025, 1, 1, 20, tzinfo=timezone.utc)
    ts = []
    posts = []
    meta = []
    for i in range(n):
        t += timedelta(days=20) if i == gap else timedelta(hours=26 + i % 7)
        ts.append(t.isoformat())
        posts.append('Harika bir gün, müzik sanat tasarım teşekkürler!' if i < n // 2 else 'Yorgun ve bitkin, stres çok fazla.')
        meta.append({'like_count': 10 + i * 2, 'comment_count': i % 4, 'created_at': t.isoformat()})
    return {'target_profile': {'platform': 'instagram', 'bio': 'sanat tasarım fotoğraf', 'posts': posts, 'post_times': ts, 'posts_meta': meta, 'interests': ['politics']}}

@pytest.mark.parametrize('v', ["2025-03-15T10:30:00Z", 1700000000, 1700000000000, datetime.now(timezone.utc)])
def test_timestamp(v):
    assert parse_timestamp(v) is not None

def test_strict_models():
    with pytest.raises(ValidationError):
        FrequencyReport(nope=True)

@pytest.mark.asyncio
async def test_frequency():
    r = await FrequencyEngine().analyze(data())
    assert r.status == EvidenceStatus.OBSERVED and len(r.waveform) == len(r.timeline) and 0 <= r.night_energy_share <= 1

@pytest.mark.asyncio
async def test_seismos():
    r = await SeismosEngine(min_silence_hours=48, silence_factor=3).analyze(data())
    assert SeismicKind.SILENCE_GAP in {e.kind for e in r.events} and all(1 <= e.intensity <= 10 for e in r.events)

@pytest.mark.asyncio
async def test_void():
    r = await VoidEngine(min_tokens=20).analyze(data())
    assert r.signals and 0 <= r.global_absence_index <= 1

@pytest.mark.asyncio
async def test_strata():
    r = await StrataEngine().analyze(data())
    assert len(r.drifts) == 4 and r.early_range and r.late_range

@pytest.mark.asyncio
async def test_strata_small_sample_is_weak_and_below_floor_is_insufficient():
    r_too_few = await StrataEngine().analyze(data(n=5, gap=2))
    assert r_too_few.status == EvidenceStatus.INSUFFICIENT_DATA
    r_small = await StrataEngine().analyze(data(n=8, gap=4))
    assert r_small.status == EvidenceStatus.WEAK
    assert len(r_small.drifts) == 4
    assert "düşük örneklem" in r_small.machine_note

@pytest.mark.asyncio
async def test_gravity():
    r = await GravityEngine(min_recurrence=2).analyze(data())
    assert r.wells and r.dominant_attractor

@pytest.mark.asyncio
async def test_pulse():
    r = await PulseEngine().analyze(data())
    assert r.status == EvidenceStatus.OBSERVED and len(r.signals) == 5 and r.rhythm_signature

@pytest.mark.asyncio
async def test_orchestrator_and_json():
    f = await PillarOrchestrator().run(data())
    assert f['pillar_bundle']['version'] == 'pillar-full-v1'
    json.dumps(f)
    assert set(['frequency_map', 'seismos_events', 'void_map', 'strata_map', 'gravity_map', 'pulse_map', 'key_matrix', 'pillar_bundle']) <= set(f)

@pytest.mark.asyncio
async def test_graceful_empty():
    f = await PillarOrchestrator().run({})
    assert f['frequency_map']['status'] == 'INSUFFICIENT_DATA' and f['key_matrix']['status'] == 'INSUFFICIENT_DATA'

def test_bundle_roundtrip():
    d = FullPillarBundle().model_dump(mode='json')
    assert FullPillarBundle(**d).version == 'pillar-full-v1'

@pytest.mark.asyncio
async def test_output_language_safety():
    blob = json.dumps(await PillarOrchestrator().run(data()), ensure_ascii=False).lower()
    for term in ('exploitability', 'manipulation', 'narsist', 'psikopat', 'bipolar', 'subconscious_hook', 'ego_mine'):
        assert term not in blob
