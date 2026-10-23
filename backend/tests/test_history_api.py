from fastapi.testclient import TestClient
from fastapi import HTTPException
from app.config import Settings,get_settings
from app.main import app
from app.models import HistoryResponse
from app.services import _cache,get_history
from app.archive_history import read_history

def setup_function(): _cache.clear()

def test_history_uses_durable_archive_and_cache_is_keyed_by_window(monkeypatch):
    calls=[]
    def read(settings,days,**kwargs):
        calls.append((days,kwargs))
        return HistoryResponse(days=days,latest_update='2026-10-12T00:00:00Z')
    monkeypatch.setattr('app.archive_history.read_history',read)
    monkeypatch.setattr('app.services.fetch_hotspot_history',lambda *args: (_ for _ in ()).throw(AssertionError('live NASA requested')))
    s=Settings(cache_dir='.')
    get_history(s,7);get_history(s,7);get_history(s,30);get_history(s,7,as_of='2026-10-10T00:00:00Z')
    assert len(calls)==3
    assert [x[0] for x in calls]==[7,30,7]

def test_history_route_bounds_and_replay_arguments(monkeypatch):
    calls=[]
    def read(settings,days=30,**kwargs):
        calls.append(kwargs)
        return HistoryResponse(days=days,latest_update='2026-10-12T00:00:00Z')
    monkeypatch.setattr('app.main.get_history',read)
    app.dependency_overrides[get_settings]=lambda:Settings(cache_dir='.')
    try:
        client=TestClient(app)
        assert client.get('/api/history?days=180&end=2026-10-10T00:00:00Z&as_of=2026-10-10T00:00:00Z').status_code==200
        assert calls[0]['end']==calls[0]['as_of']=='2026-10-10T00:00:00Z'
        assert client.get('/api/history?days=0').status_code==422
        assert client.get('/api/history?days=366').status_code==200
        assert client.get('/api/history?days=367').status_code==422
    finally: app.dependency_overrides.clear()

def test_archive_failure_is_unavailable_not_fake_zero(monkeypatch):
    def unavailable(*args,**kwargs): raise HTTPException(503,'database unavailable')
    monkeypatch.setattr('app.archive_history.read_history',unavailable)
    h=get_history(Settings(cache_dir='.'),30)
    assert h.status=='unavailable' and h.hotspots==[] and h.analytics=={}

def test_bad_time_is_rejected_before_archive_access():
    import pytest
    for args in [{'end':'2026-10-10T00:00:00'}, {'as_of':'2040-01-01T00:00:00Z'}, {'end':'invalid'}]:
        with pytest.raises(HTTPException) as exc: read_history(Settings(cache_dir='.'),7,**args)
        assert exc.value.status_code==422

def test_archive_preserves_gaps_and_pm_classes(monkeypatch):
    def call(self,*args,**kwargs):
        assert kwargs['json']['p_as_of']=='2026-10-11T00:00:00+00:00'
        return {'start':'2026-10-04T00:00:00Z','end':'2026-10-11T00:00:00Z','as_of':'2026-10-11T00:00:00Z',
          'hotspots':[{'date':'2026-10-10','count':None,'observed_count':0,'source_requests_complete':False}],
          'pm25':[{'date':'2026-10-10','value':8,'measurement_kind':'measured'},{'date':'2026-10-10','value':80,'measurement_kind':'model'}],
          'weather':[],'hour_histogram':[0]*24,'checked_at':'2026-10-12T00:00:00Z'}
    monkeypatch.setattr('app.community_store.CommunityStore.call',call)
    h=read_history(Settings(cache_dir='.',supabase_url='https://fixture.invalid',supabase_service_role_key='test'),7,end='2026-10-11T00:00:00Z',as_of='2026-10-11T00:00:00Z')
    assert h.hotspots[0].count is None and h.pm25[0].value==8 and h.pm25_model[0].value==80

def test_dashboard_trend_compares_equal_full_days_and_does_not_drop_an_inner_gap(monkeypatch):
    from app.models import HotspotResponse,HotspotHistoryDay
    from app.services import _hotspot_trend
    days=[HotspotHistoryDay(date=f'2026-10-{i:02d}',count=i,source_requests_complete=True,partial_day=i in (1,6)) for i in range(1,7)]
    def history(*args,**kwargs): return HistoryResponse(days=6,hotspots=days,latest_update='2026-10-12T00:00:00Z')
    monkeypatch.setattr('app.services.get_history',history)
    snapshot=HotspotResponse(count=99,density_per_100_km2=0,latest_update='2026-10-12T00:00:00Z',source='fixture',items=[])
    r=_hotspot_trend(Settings(cache_dir='.'),snapshot,6)
    assert r.window_days==4 and r.previous_count==5 and r.recent_count==9
    days[2].source_requests_complete=False
    r=_hotspot_trend(Settings(cache_dir='.'),snapshot,6)
    assert r.window_days==0 and r.change_percent is None

def test_trend_zero_reference_has_no_invented_percentage(monkeypatch):
    from app.models import HotspotResponse,HotspotHistoryDay
    from app.services import _hotspot_trend
    h=HistoryResponse(days=4,hotspots=[HotspotHistoryDay(date=f'2026-10-{i+1:02d}',count=n,source_requests_complete=True) for i,n in enumerate([0,0,1,1])],latest_update='2026-10-12T00:00:00Z')
    monkeypatch.setattr('app.services.get_history',lambda *a,**kw:h)
    s=HotspotResponse(count=99,density_per_100_km2=0,latest_update='2026-10-12T00:00:00Z',source='fixture',items=[])
    assert _hotspot_trend(Settings(cache_dir='.'),s,4).change_percent is None

def test_district_filter_reaches_the_archive_and_is_echoed(monkeypatch):
    sent={}
    class Store:
        def __init__(self,settings): pass
        def call(self,method,path,json=None):
            sent.update(json)
            return {'start':'2026-10-13T00:00:00+07:00','end':'2026-10-20T00:00:00+07:00','as_of':None,'pm25':[],'weather':[],
                    'hotspots':[],'hour_histogram':[0]*24,'checked_at':'2026-10-20T00:00:00Z','total':0}
    monkeypatch.setattr('app.archive_history.CommunityStore',Store)
    r=read_history(Settings(cache_dir='.'),7,district=' ฝาง ')
    assert sent['p_district']=='ฝาง' and r.district=='ฝาง'
    sent.clear(); r=read_history(Settings(cache_dir='.'),7)
    assert 'p_district' not in sent and r.district is None
