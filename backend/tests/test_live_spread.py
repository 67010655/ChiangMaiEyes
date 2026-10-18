from datetime import datetime, timezone, timedelta
import copy
import pytest
import httpx
from app import live_spread as live
from app import forecast_archive as archive
from app.spread_scenario import frame

START=datetime(2026,3,29,tzinfo=timezone.utc)
POINT={'latitude':18.85,'longitude':98.75,'detected_at':START.isoformat()}

def weather():
    return {'hourly':{'time':[(START+timedelta(hours=h)).isoformat() for h in range(7)],
                     'wind_speed_10m':[3]*7,'wind_direction_10m':[270]*7}}

def test_constant_wind_matches_original_extents():
    steps=live.segments(POINT,weather(),START,{'slope_deg':0,'upslope_to_deg':0})
    actual=live.footprint(POINT,steps,180)['coordinates'][0]
    original=frame(POINT['latitude'],POINT['longitude'],steps[0]['rates'],180)['geometry']['coordinates'][0]
    for axis in (0,1):
        assert min(p[axis] for p in actual)==pytest.approx(min(p[axis] for p in original),abs=1e-5)
        assert max(p[axis] for p in actual)==pytest.approx(max(p[axis] for p in original),abs=1e-5)

def test_future_points_never_enter_prediction():
    future={**POINT,'detected_at':(START+timedelta(seconds=1)).isoformat()}
    old={**POINT,'detected_at':(START-timedelta(hours=25)).isoformat()}
    result=live.build([POINT,future,old,POINT],{(18.85,98.75):weather()},as_of=START,source_mode='test',source_retrieved_at=None)
    assert result['eligible_points']==result['used_points']==1
    assert result['overall_accuracy_percent'] is None

def test_missing_hourly_wind_excludes_origin_instead_of_filling():
    w=weather();w['hourly']['wind_speed_10m'][2]=None
    result=live.build([POINT],{(18.85,98.75):w},as_of=START,source_mode='test',source_retrieved_at=None)
    assert result['used_points']==0
    assert len(result['excluded'])==1

def test_hourly_changes_affect_footprint():
    w=weather(); first=live.segments(POINT,w,START,{'slope_deg':0,'upslope_to_deg':0})
    w['hourly']['wind_direction_10m'][1:]=[90]*6
    second=live.segments(POINT,w,START,{'slope_deg':0,'upslope_to_deg':0})
    assert live.footprint(POINT,first,60)==live.footprint(POINT,second,60)
    assert live.footprint(POINT,first,180)!=live.footprint(POINT,second,180)

def test_archive_identity_ignores_reread_time_but_tracks_values():
    a,_=archive.envelope({'generated_at':'a','pm':12})
    b,_=archive.envelope({'generated_at':'b','pm':12})
    c,_=archive.envelope({'generated_at':'b','pm':13})
    assert a['run_id']==b['run_id']!=c['run_id']

def test_duplicate_archive_never_overwrites(monkeypatch):
    calls=[]
    def request(settings,method,path,**kwargs):
        calls.append((method,kwargs))
        return httpx.Response(400) if method=='POST' else httpx.Response(200,json={'run_id':'same','captured_at':'old'})
    monkeypatch.setattr(archive,'storage_request',request)
    assert archive.put_once(None,'test',{'run_id':'same'})=='already_stored'
    assert calls[0][1]['headers']['x-upsert']=='false'
    assert [c[0] for c in calls]==['POST','GET']

def test_failed_archive_is_retryable(monkeypatch):
    archive._seen.clear()
    def fail(*args,**kwargs):raise RuntimeError('offline')
    monkeypatch.setattr(archive,'put_once',fail)
    with pytest.raises(RuntimeError):archive.collect(None,{'test':'retry'})
    assert not archive._seen
