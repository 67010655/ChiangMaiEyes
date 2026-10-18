from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.community_practice import Action, evolve, visible, router as practice_router
from app.community_field import FieldCheck, router as field_router


def initial():
    return {'id':str(uuid4()),'version':1,'data':{'mode':'practice','title':'Fixture only','scenario':'smoke','incidents':[],'events':[],'feedback':[]}}


def step(run, action, actor='A', **kw):
    payload=Action(request_id=uuid4(),version=run['version'],actor=actor,action=action,**kw)
    data=evolve(run,payload)
    return {**run,'version':run['version']+1,'data':data}


def test_full_rehearsal_roles_and_closure():
    run=initial();iid=uuid4()
    run=step(run,'create',incident_id=iid,note='Fixture smoke')
    assert visible(run,'B')['data']['incidents']==[]
    assert visible(run,'outsider')['data']['incidents']==[]
    run=step(run,'status',incident_id=iid,status='confirmed',note='Fixture checked')
    run=step(run,'claim',incident_id=iid)
    run=step(run,'invite',incident_id=iid)
    assert not visible(run,'B')['data']['incidents'][0]['permissions']['note']
    with pytest.raises(HTTPException) as denied:
        step(run,'note',actor='B',incident_id=iid,note='Not accepted')
    assert denied.value.status_code==403
    run=step(run,'respond',actor='B',incident_id=iid,status='accepted')
    run=step(run,'note',actor='B',incident_id=iid,note='Fixture support')
    with pytest.raises(HTTPException):
        step(run,'status',actor='B',incident_id=iid,status='closed',note='Forged control')
    run=step(run,'status',incident_id=iid,status='coordinating',note='Fixture coordination')
    run=step(run,'status',incident_id=iid,status='controlled',note='Fixture controlled')
    run=step(run,'status',incident_id=iid,status='closed',note='Fixture followup')
    assert run['data']['incidents'][0]['status']=='closed'
    assert run['data']['incidents'][0]['coordinator']=='A'


@pytest.mark.parametrize('actor',['B','outsider'])
def test_non_members_cannot_create(actor):
    with pytest.raises(HTTPException):step(initial(),'create',actor=actor,incident_id=uuid4())


def test_duplicate_event_replay_and_changed_payload():
    run=initial();payload=Action(request_id=uuid4(),version=1,actor='A',action='create',incident_id=uuid4(),note='Same request')
    data=evolve(run,payload)
    assert run['data']['incidents']==[]  # Pure function never mutates prior data.
    saved={**run,'version':2,'data':data}
    assert evolve(saved,payload) is None
    with pytest.raises(HTTPException):evolve(saved,payload.model_copy(update={'note':'Changed request'}))
    assert len(saved['data']['events'])==1


def test_stale_actor_write_and_illegal_transition():
    run=step(initial(),'create',incident_id=uuid4())
    iid=run['data']['incidents'][0]['id']
    with pytest.raises(HTTPException) as stale:
        evolve(run,Action(request_id=uuid4(),version=1,actor='A',action='claim',incident_id=iid))
    assert stale.value.status_code==409
    with pytest.raises(HTTPException):step(run,'status',incident_id=iid,status='closed',note='Invalid skip')


def test_duplicate_link_preserves_incidents_and_cannot_reopen_link():
    a,b=uuid4(),uuid4();run=step(step(initial(),'create',incident_id=a),'create',incident_id=b)
    run=step(run,'merge',incident_id=b,target_id=a,note='Fixture same smoke')
    duplicate=run['data']['incidents'][1]
    assert duplicate['linked_id']==str(a) and duplicate['status']=='cancelled'
    with pytest.raises(HTTPException):step(run,'status',incident_id=b,status='pending',note='Invalid reopen')
    assert len(run['data']['incidents'])==2


def check_values():
    return dict(id=uuid4(),checked_at=datetime.now(timezone.utc),outcome='unverified',method='unavailable',note='Fixture no evidence yet')


@pytest.mark.parametrize('patch',[
    {'checked_at':datetime(2026,1,1)}, {'checked_at':'2099-01-01T10:00:00Z'},
    {'outcome':'fire_found'}, {'latitude':18.5}, {'position_accuracy_m':-1},
    {'satellite_match':'matched'}, {'satellite_detected_at':'2020-01-01T00:00:00Z'},
    {'method':'photo','outcome':'no_fire_found','satellite_match':'matched','satellite_source':'Fixture','satellite_detected_at':'2020-01-02T00:00:00Z','web_received_at':'2020-01-01T00:00:00Z'},
    {'email_delivered_at':'2020-01-02T00:00:00Z','message_seen_at':'2020-01-01T00:00:00Z'}
])
def test_field_check_rejects_unjustified_results_unknown_positions_and_bad_time(patch):
    with pytest.raises(ValidationError):FieldCheck(**{**check_values(),**patch})


def test_unknown_values_stay_null_and_practice_evidence_stays_in_practice():
    check=FieldCheck(**check_values())
    assert check.position_accuracy_m is None and check.email_delivered_at is None
    iid=uuid4();run=step(initial(),'create',incident_id=iid)
    run=step(run,'check',incident_id=iid,field_check=check)
    assert len(run['data']['incidents'][0]['checks'])==1
    assert run['data']['mode']=='practice'
    with pytest.raises(HTTPException):step(run,'check',incident_id=iid,field_check=check)


def test_outsider_cannot_read_other_actors_feedback_or_export_run():
    from app.community_practice import export
    run=step(initial(),'feedback',note='Fixture private feedback',outcome='done')
    assert visible(run,'outsider')['data']['events']==[]
    assert visible(run,'outsider')['data']['feedback']==[]
    with pytest.raises(HTTPException) as error:
        export(uuid4(),actor='B',ctx=(None,None,None))
    assert error.value.status_code==403


def test_practice_and_field_api_require_a_real_verified_session():
    app=FastAPI();app.include_router(practice_router);app.include_router(field_router)
    with TestClient(app) as client:
        assert client.get('/api/community/practice/runs').status_code==401
        assert client.post('/api/community/practice/runs',json={'id':str(uuid4())}).status_code==401
        assert client.get(f'/api/community/incidents/{uuid4()}/field-checks').status_code==401


def test_rehearsal_paths_never_write_to_live_incident_or_mail_tables():
    import inspect
    import app.community_practice as practice
    code=inspect.getsource(practice)
    assert 'cme_action' not in code and 'cme_email_outbox' not in code and 'resend' not in code
