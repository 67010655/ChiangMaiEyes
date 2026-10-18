from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.community_field import ResearchRecord, research_records, save_research_record


def test_research_payload_accepts_model_evidence_and_bounds_json():
    record = ResearchRecord(id=uuid4(), kind='model', data={'version': 'baseline-v1', 'score': 0.7})
    assert record.kind == 'model'
    with pytest.raises(ValidationError):
        ResearchRecord(id=uuid4(), kind='fuel', data={'large': 'x' * 400_001})
    with pytest.raises(ValidationError):
        ResearchRecord(id=uuid4(), kind='model', data={'score': float('nan')})


def test_research_reads_use_user_token_and_rls_filters():
    class Store:
        def call(self, method, path, **kwargs):
            assert method == 'GET'
            assert path == '/rest/v1/cme_research_records'
            assert kwargs['token'] == 'session-token'
            assert kwargs['params']['forest_id'] == 'eq.forest-1'
            assert kwargs['params']['kind'] == 'eq.model'
            assert kwargs['params']['limit'] == '25'
            return []

    assert research_records('forest-1', kind='model', limit=25, ctx=(Store(), 'session-token', {})) == []


def test_research_save_returns_no_recorder_account_identifier():
    class Store:
        def call(self, method, path, **kwargs):
            assert method == 'POST'
            assert path == '/rest/v1/rpc/cme_research_save'
            assert kwargs['token'] == 'session-token'
            assert kwargs['json']['p_kind'] == 'burned_area'
            return {'id': kwargs['json']['p_id'], 'forest_id': 'forest-1', 'kind': 'burned_area',
                    'data': {'source': 'fixture'}, 'corrects_id': None, 'created_at': '2026-10-10T10:00:00Z',
                    'recorded_by': 'private-user-id'}

    record = ResearchRecord(id=uuid4(), kind='burned_area', data={'source': 'fixture'})
    result = save_research_record('forest-1', record, (Store(), 'session-token', {}))
    assert result['kind'] == 'burned_area'
    assert 'recorded_by' not in result


def test_research_save_rejects_invalid_forest_id():
    class Store:
        def call(self, *args, **kwargs):
            raise AssertionError('must reject before database call')

    record = ResearchRecord(id=uuid4(), kind='fuel', data={'plot': 'fixture'})
    with pytest.raises(HTTPException) as error:
        save_research_record('', record, (Store(), 'session-token', {}))
    assert error.value.status_code == 422


def test_single_research_read_is_scoped_and_uses_rls():
    from app.community_field import research_record
    record_id = uuid4()
    class Store:
        def call(self, method, path, **kwargs):
            assert kwargs['token'] == 'session-token'
            assert kwargs['params']['id'] == 'eq.' + str(record_id)
            assert kwargs['params']['forest_id'] == 'eq.forest-1'
            assert 'recorded_by' not in kwargs['params']['select']
            return []
    with pytest.raises(HTTPException) as error:
        research_record('forest-1', record_id, (Store(),'session-token',{}))
    assert error.value.status_code == 404


@pytest.mark.parametrize('tamper', [False, True])
def test_comparison_save_verifies_against_private_parent_and_retains_retry_payload(tamper):
    import copy
    from app.spread_scenario import Scenario, run_scenario, SnapshotEvaluation, evaluate_snapshot
    from test_spread_scenario import payload
    parent_id = uuid4()
    snapshot = run_scenario(Scenario(**payload()))
    observations = [dict(latitude=18.79,longitude=98.99,observed_at='2020-01-01T00:30:00Z',kind='field_arrival',source='synthetic unit test only')]
    evaluation = evaluate_snapshot(SnapshotEvaluation(snapshot=snapshot, observations=observations))
    if tamper: evaluation['mean_absolute_arrival_error_minutes'] = 0
    data = dict(schema='cme-spread-evaluation-v1',scenario_record_id=str(parent_id),evaluation=evaluation,observations=observations)
    record = ResearchRecord(id=uuid4(),kind='model',data=data)
    saved = []
    class Store:
        def call(self, method, path, **kwargs):
            assert kwargs['token'] == 'user-session'
            if method == 'GET':
                assert kwargs['params']['forest_id'] == 'eq.forest-1'
                return [dict(id=str(parent_id),kind='model',data=dict(schema='cme-spread-scenario-v1',result=snapshot))]
            saved.append(copy.deepcopy(kwargs['json']))
            return dict(id=str(record.id),forest_id='forest-1',kind='model',data=kwargs['json']['p_data'])
    ctx = (Store(),'user-session',{})
    if tamper:
        with pytest.raises(HTTPException) as error: save_research_record('forest-1',record,ctx)
        assert error.value.status_code == 422
        assert not saved
    else:
        save_research_record('forest-1',record,ctx)
        save_research_record('forest-1',record,ctx)
        assert saved[0] == saved[1]
