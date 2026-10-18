from datetime import datetime,timedelta
import pytest
from app.pm25_station_forecast import ICT,features,predict,build,artifact

ORIGIN=datetime(2026,10,17,0,tzinfo=ICT)
def series():return {ORIGIN-timedelta(hours=h):10+h/10 for h in range(60)}

def test_future_observations_cannot_change_inputs():
    old=series();new={**old,ORIGIN+timedelta(hours=1):99999}
    assert features(old,ORIGIN,24)==features(new,ORIGIN,24)
    with pytest.raises(ValueError):features(new,ORIGIN,48)

def test_missing_lag_is_not_imputed():
    observations=series();del observations[ORIGIN-timedelta(hours=48)]
    result=build('35T',observations,ORIGIN+timedelta(hours=1))
    assert result['status']=='unavailable'
    assert result['forecasts']==[]

def test_stale_data_not_presented_as_live():
    result=build('35T',series(),ORIGIN+timedelta(hours=7))
    assert result['reason']=='observations_older_than_6h'

def test_current_hour_is_excluded():
    observations={**series(),ORIGIN+timedelta(hours=1):999}
    result=build('35T',observations,ORIGIN+timedelta(hours=1,minutes=30))
    assert result['observation_at']==ORIGIN.isoformat()
    assert len(result['forecasts'])==3

def test_blend_and_ridge_are_numeric_and_nonnegative():
    assert predict({'type':'blend','weight_now':.5},[10,0,0,0,0,0,0,20,0,0])==15
    for model in artifact()['models']:
        assert predict(model['model'],features(series(),ORIGIN,model['lead_hours']))>=0
