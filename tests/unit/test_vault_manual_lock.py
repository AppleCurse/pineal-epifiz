"""The reported vault lock must also close the actual backend interlock."""
import json
import uuid

from fastapi.testclient import TestClient
from backend import api


def test_lock_overrides_file_keys_and_unlock_restores_access(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PINEAL_ROUTER_LIVE', raising=False)
    # Synthetic key material: never contact a provider.
    (tmp_path / '.pineal_vault.json').write_text(json.dumps({'api_key': 'sk-or-v1-synthetic-key-for-test-12345'}))
    cid = f'lock_{uuid.uuid4().hex}'
    with TestClient(api.app) as c:
        assert c.get('/api/vault/status', params={'client_id': cid}).json()['locked'] is False
        assert c.post('/api/vault/status', json={'client_id': cid, 'action': 'lock'}).json()['status'] == 'locked'
        assert c.get('/api/vault/status', params={'client_id': cid}).json()['locked'] is True
        assert api._check_vault_interlock(cid) is False
        blocked = c.post('/api/browser/open', json={'client_id': cid, 'url': ''})
        assert blocked.status_code == 423
        assert c.post('/api/vault/status', json={'client_id': cid, 'action': 'unlock'}).json()['status'] == 'unlocked'
        assert c.get('/api/vault/status', params={'client_id': cid}).json()['locked'] is False


def test_no_key_cannot_unlock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PINEAL_ROUTER_LIVE', raising=False)
    cid = f'lock_{uuid.uuid4().hex}'
    with TestClient(api.app) as c:
        assert c.post('/api/vault/status', json={'client_id': cid, 'action': 'unlock'}).status_code == 423
        assert c.get('/api/vault/status', params={'client_id': cid}).json()['locked'] is True


def test_unlock_cannot_claim_success_when_interlock_is_closed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PINEAL_ROUTER_LIVE', raising=False)
    cid = f'lock_{uuid.uuid4().hex}'
    with TestClient(api.app) as c:
        room = api.get_room(cid)
        room['vault'] = {'provider_keys_set': ['synthetic-provider']}
        room['vault_manually_locked'] = True
        response = c.post('/api/vault/status', json={'client_id': cid, 'action': 'unlock'})
        assert response.status_code == 423
        assert c.get('/api/vault/status', params={'client_id': cid}).json()['locked'] is True


def test_search_policy_failure_cannot_unlock_manual_vault(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('PINEAL_ROUTER_LIVE', raising=False)
    (tmp_path / '.pineal_vault.json').write_text(json.dumps({'api_key': 'sk-or-v1-synthetic-for-test-only'}))
    cid = f'lock_{uuid.uuid4().hex}'
    with TestClient(api.app) as c:
        room = api.get_room(cid)
        room['vault_manually_locked'] = True
        def fail_policy(_policy):
            raise RuntimeError('policy failure')
        monkeypatch.setattr(room['executor'].search_engine, 'set_policy', fail_policy)
        result = c.post('/api/vault', json={'client_id': cid, 'tavily_key': 'synthetic-search-key-for-test'})
        assert result.status_code == 503
        assert room['vault_manually_locked'] is True
        assert api._check_vault_interlock(cid) is False
        assert c.get('/api/vault/status', params={'client_id': cid}).json()['locked'] is True


def test_empty_vault_submission_does_not_clear_manual_lock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cid = f'lock_{uuid.uuid4().hex}'
    with TestClient(api.app) as c:
        room = api.get_room(cid)
        room['vault']['or_key'] = True
        room['vault_manually_locked'] = True
        response = c.post('/api/vault', json={'client_id': cid})
        assert response.status_code == 200
        assert room['vault_manually_locked'] is True
        assert api._check_vault_interlock(cid) is False
