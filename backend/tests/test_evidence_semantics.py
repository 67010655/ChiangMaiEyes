import httpx
import pytest
from app.evidence import detection_identity, native_confidence, wind_to_text
from app.environment_archive import observation
from app.providers.pm25_provider import fetch_live_pm25, fetch_aqicn_stations
from app.providers.hotspot_provider import fetch_nasa_firms_hotspots
from app.providers.osm_structures_provider import fetch_osm_structures
from app.providers.community_forest_provider import _load_official
from app.models import HotspotResponse, WeatherResponse
from app.providers.pm25_provider import _build_pm25_response_from_aqicn
from app.services import calculate_risk, deterministic_hourly_summary, _build_data_quality


def test_live_backfill_and_reordered_window_share_identity_without_collapsing_passes():
    lat,lon=19.41368,99.02454
    live=observation('hotspot','NASA FIRMS','2026-10-10T13:44:00+07:00',
        {'id':'HS-018','satellite':'N21'},'2026-10-10T15:00:00+07:00','HS-018',lat,lon)
    backfill=observation('hotspot','VIIRS_NOAA21_SP','2026-10-10T06:44:00Z',
        {'native_id':'backfill','satellite':'NOAA-21'},'2026-10-10T16:00:00+07:00','backfill',lat,lon)
    assert live['observation_key']==backfill['observation_key']
    assert live['id']!=backfill['id']  # Keep both source records.
    key=detection_identity({'satellite':'N21'},'NASA FIRMS',lat,lon,'2026-10-10T06:44:00Z')
    assert key!=detection_identity({'satellite':'N20'},'NASA FIRMS',lat,lon,'2026-10-10T06:44:00Z')
    assert key!=detection_identity({'satellite':'N21'},'NASA FIRMS',lat,lon,'2026-10-10T06:45:00Z')


def test_nominal_is_not_high_and_numeric_without_a_scheme_is_unknown():
    assert native_confidence('n')['confidence_level']=='nominal'
    assert native_confidence('h')['confidence_level']=='high'
    assert native_confidence('75')['confidence_level']=='unknown'
    assert native_confidence(None)['confidence_level']=='unknown'
    assert wind_to_text(205.5)=='ตะวันออกเฉียงเหนือ'


def test_missing_pm_does_not_crash_or_claim_measured_zero_or_fresh_observation():
    pm=_build_pm25_response_from_aqicn([])
    hs=HotspotResponse(count=0,density_per_100_km2=0,latest_update='2026-10-10T10:00:00Z',source='fixture',items=[])
    w=WeatherResponse(wind_speed_kmh=2,wind_direction_deg=205.5,wind_direction_text='ตะวันตกเฉียงใต้',
        temperature_c=28,humidity_percent=70,latest_update='2026-10-10T10:00:00Z',source='fixture')
    risk=calculate_risk(pm,hs,w)
    assert risk.category=='ข้อมูลไม่ครบ'
    summary=deterministic_hourly_summary(pm,hs,w,risk).text
    assert 'ยังไม่มีค่า PM2.5 ที่วัดได้' in summary
    assert '0 µg/m³' not in summary and 'พัดไปตะวันออกเฉียงเหนือ' in summary
    q=_build_data_quality(hs,pm,w)['pm25']
    assert q.source_mode=='UNAVAILABLE' and q.latest_update is None and q.age_minutes is None


def test_degenerate_component_is_flagged_without_dropping_official_forest():
    forests=_load_official()
    assert len(forests)==677
    flagged=[f for f in forests if f.boundary_quality=='needs_review']
    assert [f.forest_id for f in flagged]==['cmf-th-3192']
    assert flagged[0].boundary and flagged[0].boundary_note


def test_aqi_only_never_becomes_pm25_or_uses_retrieval_as_observation_time(monkeypatch):
    monkeypatch.setattr('app.providers.pm25_provider._is_in_cm',lambda *a:True)
    def get(url,**kwargs):
        if 'air4thai' in url: raise httpx.ConnectError('offline')
        return httpx.Response(200,json={'status':'ok','data':[{'uid':1,'lat':18.8,'lon':99,'aqi':'50',
            'station':{'name':'Fixture','time':'2026-10-10 19:00:00'}}]},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.providers.pm25_provider.httpx.get',get)
    result=fetch_live_pm25('dummy-only')
    assert result.current_pm25 is None and result.stations==[]
    assert result.aqi_stations[0].aqi==50
    assert result.aqi_stations[0].updated_at is None
    assert result.aqi_stations[0].retrieved_at
    assert result.measurement_kind=='unavailable'


@pytest.mark.parametrize('provider',['aqi','nasa'])
def test_http_error_logs_never_include_credential_or_request_url(monkeypatch,caplog,provider):
    def fail(url,**kwargs):
        r=httpx.Response(403,request=httpx.Request('GET',url))
        r.raise_for_status()
    monkeypatch.setattr('app.providers.pm25_provider.httpx.get',fail)
    (fetch_aqicn_stations if provider=='aqi' else fetch_nasa_firms_hotspots)('dummy-secret-never-log')
    assert 'dummy-secret-never-log' not in caplog.text
    assert 'https://' not in caplog.text


@pytest.mark.parametrize('bounds',[(90,180,-90,-180),(18,99,float('nan'),99.1),(18,99,18,99.1)])
def test_invalid_bbox_never_reaches_upstream(monkeypatch,bounds):
    def forbidden(*a): raise AssertionError('invalid bbox reached transport')
    monkeypatch.setattr('app.providers.osm_structures_provider._fetch_overpass',forbidden)
    assert fetch_osm_structures(*bounds).buildings==[]
