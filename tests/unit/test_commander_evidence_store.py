"""Commander storage must not masquerade as evidence injected into agents."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.commander import register_commander_routes


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = FastAPI()
    register_commander_routes(app, rate_limit=lambda *_: True, rate_identity=lambda *_: "test",
                              gateway_provider=lambda: None)
    with TestClient(app) as c:
        yield c


PAYLOAD = {"client_id": "test", "evidence_type": "note", "evidence_value": "proof", "target_agent": "all"}


def test_stored_does_not_claim_agent_injection(client, tmp_path):
    response = client.post('/api/commander/inject', json=PAYLOAD)
    assert response.status_code == 200
    assert response.json()['status'] == 'stored'
    assert response.json()['applied_to_agent'] is False
    assert json.loads((tmp_path / '.pineal_memory/learnings.json').read_text())[0]['fact'].endswith('proof')


def test_unwritable_store_returns_error_not_success(client, tmp_path):
    (tmp_path / '.pineal_memory').write_text('not a directory')
    response = client.post('/api/commander/inject', json=PAYLOAD)
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'EVIDENCE_STORE_FAILED'
    assert not (tmp_path / '.pineal_memory/learnings.json').exists()


def test_atomic_replace_failure_keeps_previous_evidence(client, tmp_path, monkeypatch):
    assert client.post('/api/commander/inject', json=PAYLOAD).status_code == 200
    path = tmp_path / '.pineal_memory/learnings.json'
    before = path.read_text()
    def fail_replace(*_args):
        raise OSError('test failure')
    monkeypatch.setattr('backend.routes.commander.os.replace', fail_replace)
    response = client.post('/api/commander/inject', json={**PAYLOAD, 'evidence_value': 'next'})
    assert response.status_code == 500
    assert path.read_text() == before
    assert {p.name for p in path.parent.iterdir()} == {path.name, ".learnings.lock"}


def test_corrupt_store_is_not_overwritten(client, tmp_path):
    path = tmp_path / '.pineal_memory/learnings.json'
    path.parent.mkdir()
    path.write_text('{broken')
    assert client.post('/api/commander/inject', json=PAYLOAD).status_code == 500
    assert path.read_text() == '{broken'


def _parallel_inject(directory, barrier, results, value):
    """Separate worker and API instance; delay file reads to expose lost updates."""
    import os
    import time
    from backend.routes import commander

    os.chdir(directory)
    original_load = commander.json.load

    def slow_load(*args, **kwargs):
        result = original_load(*args, **kwargs)
        time.sleep(0.4)
        return result

    commander.json.load = slow_load
    app = FastAPI()
    register_commander_routes(app, rate_limit=lambda *_: True, rate_identity=lambda *_: "test",
                              gateway_provider=lambda: None)
    with TestClient(app) as c:
        barrier.wait(timeout=15)
        r = c.post('/api/commander/inject', json={**PAYLOAD, 'evidence_value': value})
        results.put(r.status_code)


def test_distinct_worker_writes_do_not_lose_acknowledged_entries(tmp_path):
    import multiprocessing

    directory = tmp_path / '.pineal_memory'
    directory.mkdir()
    (directory / 'learnings.json').write_text('[]')
    ctx = multiprocessing.get_context('fork')
    barrier, results = ctx.Barrier(2), ctx.Queue()
    workers = [ctx.Process(target=_parallel_inject, args=(str(tmp_path), barrier, results, x))
               for x in ('first', 'second')]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    assert sorted([results.get(timeout=5), results.get(timeout=5)]) == [200, 200]
    entries = json.loads((directory / 'learnings.json').read_text())
    assert len(entries) == 2
    assert {entry['fact'].split('] ')[-1] for entry in entries} == {'first', 'second'}


def test_idempotency_key_retries_and_conflicts(client, tmp_path):
    headers = {'Idempotency-Key': 'retry-001'}
    first = client.post('/api/commander/inject', json=PAYLOAD, headers=headers)
    retry = client.post('/api/commander/inject', json=PAYLOAD, headers=headers)
    conflict = client.post('/api/commander/inject', json={**PAYLOAD, 'evidence_value': 'other'}, headers=headers)
    assert first.status_code == retry.status_code == 200
    assert conflict.status_code == 409
    assert len(json.loads((tmp_path / '.pineal_memory/learnings.json').read_text())) == 1


def test_retry_after_uncertain_directory_sync_is_idempotent(client, tmp_path, monkeypatch):
    import os
    import stat

    real_fsync = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('directory sync failure')
        return real_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr('backend.routes.commander.os.fsync', fail_directory)
        failed = client.post('/api/commander/inject', json=PAYLOAD, headers={'Idempotency-Key': 'uncertain'})
    assert failed.status_code == 500
    retry = client.post('/api/commander/inject', json=PAYLOAD, headers={'Idempotency-Key': 'uncertain'})
    assert retry.status_code == 200
    assert len(json.loads((tmp_path / '.pineal_memory/learnings.json').read_text())) == 1


def test_retry_does_not_acknowledge_while_sync_still_failing(client, monkeypatch):
    import os
    import stat

    real_fsync = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError('directory sync failure')
        return real_fsync(fd)

    with monkeypatch.context() as patch:
        patch.setattr('backend.routes.commander.os.fsync', fail_directory)
        for _ in range(2):
            result = client.post('/api/commander/inject', json=PAYLOAD, headers={'Idempotency-Key': 'sync-retry'})
            assert result.status_code == 500
    assert client.post('/api/commander/inject', json=PAYLOAD, headers={'Idempotency-Key': 'sync-retry'}).status_code == 200
