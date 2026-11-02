"""Recorded support responses are not proof of cleared blockers."""
from backend import checkpoint_store as ckpt


def _seed(task, requires='operator_response', kind='operator_response'):
    ckpt.set_input(task, {})
    ckpt.update(task, lambda d: d.update(status={'support_requests': [{
        'support_id': 'support1', 'status': 'pending', 'requires': requires,
        'kind': kind, 'blocks_resume': True,
    }]}))


def test_rejected_response_is_recorded_but_not_resolved():
    _seed('reject')
    code, entry = ckpt.record_support_response('reject', 'support1', principal='operator', approved=False)
    assert code == 'BLOCKER_NOT_CLEARED'
    assert entry['status'] == 'pending'
    assert entry['approved'] is False
    assert len(entry['responses']) == 1
    assert ckpt.load('reject')['status']['support_requests'][0]['status'] == 'pending'


def test_unknown_requirement_never_closes_on_response_alone():
    _seed('unknown', requires='external_condition')
    code, entry = ckpt.record_support_response('unknown', 'support1', principal='operator')
    assert code == 'BLOCKER_NOT_CLEARED'
    assert entry['status'] == 'pending'


def test_vault_finalize_does_not_close_other_requirement():
    _seed('wrong_kind', requires='external_condition')
    ckpt.update('wrong_kind', lambda d: d['status']['support_requests'][0].update(approved=True))
    result = ckpt.finalize_support('wrong_kind', 'support1')
    assert result['status'] == 'pending'


def test_legacy_unproven_resolved_is_not_shown_as_closed():
    view = ckpt.support_view({'support_id': 'old', 'status': 'resolved', 'approved': False, 'responses': []})
    assert view['status'] == 'legacy_unverified'


def test_budget_check_fails_closed_without_reader():
    from types import SimpleNamespace
    from backend.routes.support import _budget_blocked
    assert _budget_blocked({'executor': SimpleNamespace(llm_gateway=SimpleNamespace())}) is True


def test_legacy_unknown_requirement_cannot_be_displayed_as_resolved():
    view = ckpt.support_view({'support_id': 'old', 'status': 'resolved', 'approved': True,
                              'responses': [{'by': 'operator'}], 'requires': 'external_condition',
                              'resolution': 'operator_response'})
    assert view['status'] == 'legacy_unverified'
