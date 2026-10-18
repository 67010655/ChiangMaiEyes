from datetime import datetime,timezone
from types import SimpleNamespace
import httpx
from fastapi.testclient import TestClient
from app.archive_jobs import plan_firms,firms_chunk,model_chunk,work_one
from app.environment_archive import backfill
from app.community import session
from app.main import app

NOW=datetime(2026,10,12,0,tzinfo=timezone.utc)
START=datetime(2026,10,1,0,tzinfo=timezone.utc)
def response(text='',doc=None):
    return httpx.Response(200,**({'json':doc} if doc is not None else {'text':text}),request=httpx.Request('GET','https://fixture.invalid'))

def test_planner_covers_exact_utc_window_and_caps_requests_at_five_days():
    meta,rows,tasks=plan_firms('secret',START,NOW,get=lambda *args,**kw:response('data_id,min_date,max_date\nVIIRS_SNPP_SP,2020-01-01,2026-10-11\n'))
    assert rows==[] and meta['status']=='received'
    assert all(1<=t['payload']['days']<=5 for t in tasks)
    assert sum(t['payload']['days'] for t in tasks if t['payload']['sensor']=='SNPP')==11
    assert all(t['status']=='not_available' for t in tasks if t['payload']['sensor']!='SNPP')

def test_source_rectangle_covers_every_province_vertex_including_the_south():
    from app.providers.hotspot_provider import _province_ring,province_bbox
    from app.providers.verified_history import BBOX
    w,s,e,n=map(float,province_bbox().split(','))
    assert BBOX==province_bbox()
    assert s<17.35
    assert all(w<=lon<=e and s<=lat<=n for lon,lat in _province_ring())

def test_firms_keeps_exact_time_native_confidence_and_rejects_invalid_rows(monkeypatch):
    monkeypatch.setattr('app.archive_jobs._province_ring',lambda:None)
    csv='latitude,longitude,acq_date,acq_time,satellite,confidence,frp\n19,99,2026-10-10,0600,N21,h,0\nnan,99,2026-10-10,0600,N21,h,1\n'
    meta,rows,_=firms_chunk('secret',{'sensor':'NOAA-21','source':'VIIRS_NOAA21_NRT','utc_start':'2026-10-10','days':1},START,NOW,now=NOW,get=lambda *args,**kw:response(csv))
    assert meta['status']=='partial' and meta['invalid_rows']==1
    assert len(rows)==1 and rows[0]['payload']['confidence_level']=='high' and rows[0]['payload']['frp']==0
    assert rows[0]['observed_at']=='2026-10-10T13:00:00+07:00'
    assert 'secret' not in str(meta)+str(rows)

def test_model_grid_is_not_in_forest_sensor_and_null_is_not_zero():
    doc={'latitude':18.75,'longitude':99,'hourly_units':{'pm2_5':'μg/m³'},
         'hourly':{'time':[int(START.timestamp()),int(START.timestamp()+3600)],'pm2_5':[8,None]}}
    meta,rows,_=model_chunk('pm25_model',{'utc_start':'2026-10-01','days':1},START,NOW,now=NOW,get=lambda *args,**kw:response(doc=doc))
    assert meta['status']=='partial' and meta['missing_hours']==23 and len(rows)==1
    assert rows[0]['payload']['measurement_kind']=='model'
    assert rows[0]['latitude'] is None and rows[0]['forest_ids']==[]
    assert rows[0]['payload']['reference_latitude']==18.75

def test_worker_saves_sanitized_failure_and_never_leaks_key():
    calls=[]
    class Store:
        settings=SimpleNamespace(nasa_firms_map_key='secret-key')
        def call(self,method,path,**kwargs):
            calls.append((path,kwargs['json']))
            if path.endswith('claim'):
                return {'id':1,'kind':'firms_plan','start_at':START.isoformat(),'end_at':NOW.isoformat(),'payload':{}}
    def fail(*args,**kwargs): raise ValueError('URL with secret-key')
    assert work_one(Store(),now=NOW,get=fail)=={'status':'processed'}
    assert 'secret-key' not in str(calls)
    assert calls[-1][1]['p_result']['error']=='upstream_request_or_format_failed'

def test_only_admin_can_enqueue_or_read_private_progress():
    class Store:
        def rpc(self,*args): return {'is_admin':False}
    app.dependency_overrides[session]=lambda:(Store(),'token',{})
    try:
        c=TestClient(app)
        assert c.post('/api/archive/backfill?days=180').status_code==403
        assert c.get('/api/archive/jobs').status_code==403
        assert c.post('/api/archive/jobs/00000000-0000-0000-0000-000000000001/retry').status_code==403
    finally:app.dependency_overrides.clear()
