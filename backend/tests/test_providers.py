from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.providers.weather_provider import fetch_live_weather, get_wind_direction_text
from app.providers.pm25_provider import fetch_live_pm25, get_pm25_category_and_color
from app.providers.hotspot_provider import (
    fetch_live_hotspots,
    estimate_district,
    fetch_forest_firemap_hotspots,
    reconcile_hotspots,
)
from app.models import Hotspot


def _hs(lat, lon, source, conf=80, day="2026-06-02", **extra):
    return Hotspot(
        id=f"X-{lat}-{lon}",
        latitude=lat,
        longitude=lon,
        district=extra.get("district", "เชียงดาว"),
        confidence=conf,
        source=source,
        detected_at=f"{day}T02:00:00+07:00",
        **{k: v for k, v in extra.items() if k != "district"},
    )


RFD = "Royal Forest Department Firemap"
NASA = "NASA FIRMS"


def test_reconcile_merges_nearby_cross_source_detections():
    # Same fire seen by RFD and NASA ~200 m apart → one reconciled hotspot.
    rfd = [_hs(19.7023, 98.9434, RFD, conf=90, district="เชียงดาว", subdistrict="แม่นะ")]
    nasa = [_hs(19.7039, 98.9430, NASA, conf=75)]
    out = reconcile_hotspots([rfd, nasa])
    assert len(out) == 1
    assert out[0].source_count == 2
    assert set(out[0].sources) == {RFD, NASA}
    assert out[0].confidence == 90  # highest of the two
    assert out[0].source == RFD  # richest record kept as representative
    assert out[0].subdistrict == "แม่นะ"


def test_reconcile_keeps_distinct_fires_apart():
    # Two fires ~3 km apart stay separate even if both come from one source.
    a = [_hs(19.70, 98.94, RFD)]
    b = [_hs(19.73, 98.94, RFD)]
    out = reconcile_hotspots([a, b])
    assert len(out) == 2
    assert all(h.source_count == 1 for h in out)


def test_reconcile_does_not_collapse_same_source_points():
    # Two RFD detections 200 m apart stay distinct — we respect RFD's own count.
    rfd = [_hs(19.7023, 98.9434, RFD), _hs(19.7039, 98.9430, RFD)]
    out = reconcile_hotspots([rfd])
    assert len(out) == 2


def test_reconcile_does_not_merge_across_days():
    today = [_hs(19.70, 98.94, RFD, day="2026-06-02")]
    yesterday = [_hs(19.70, 98.94, NASA, day="2026-06-01")]
    out = reconcile_hotspots([today, yesterday])
    assert len(out) == 2

def test_wind_direction_translation():
    assert get_wind_direction_text(0) == "ทิศเหนือ"
    assert get_wind_direction_text(225) == "ทิศตะวันตกเฉียงใต้"
    assert get_wind_direction_text(245) == "ทิศตะวันตกค่อนไปทางใต้"
    assert get_wind_direction_text(270) == "ทิศตะวันตก"
    assert get_wind_direction_text(359) == "ทิศเหนือ"

def test_pm25_category_mapping():
    assert get_pm25_category_and_color(10.0) == ("ดีมาก", "green")
    assert get_pm25_category_and_color(22.0) == ("ดี", "green")
    assert get_pm25_category_and_color(30.0) == ("ปานกลาง", "yellow")
    assert get_pm25_category_and_color(50.0) == ("เริ่มมีผลกระทบต่อสุขภาพ", "orange")
    assert get_pm25_category_and_color(90.0) == ("มีผลกระทบต่อสุขภาพ", "red")
    assert get_pm25_category_and_color(150.0) == ("อันตราย", "purple")

def test_district_estimation():
    assert estimate_district(19.8, 99.0) == "ฝาง"
    assert estimate_district(19.3, 99.0) == "เชียงดาว"
    assert estimate_district(18.9, 99.0) == "สันทราย"
    assert estimate_district(18.7, 99.0) == "สันกำแพง"
    assert estimate_district(18.2, 99.0) == "เมืองเชียงใหม่"

@patch("httpx.get")
def test_fetch_live_weather_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "success": True,
        "data": [
            {
                "stationId": 1,
                "stationNameTh": "สถานีอุตุนิยมวิทยาเชียงใหม่ (ศูนย์อุตุนิยมวิทยาเชียงใหม่)",
                "stationLat": 18.7711,
                "stationLon": 98.9692,
                "temperature": 34.5,
                "temperatureMinToday": 26.6,
                "temperatureMaxToday": 35.1,
                "humidity": 56,
                "windDirection": 245,
                "windSpeed": 2.2,
                "precip15Mins": 0,
                "precip1Hr": 0,
                "precipToday": 0,
                "pressure": 967.9,
                "dateTimeUtc7": "2026-06-04T11:46:00.000+0700",
            }
        ],
    }
    mock_get.return_value = mock_response

    weather = fetch_live_weather()
    
    assert weather.temperature_c == 34.5
    assert weather.humidity_percent == 56
    assert weather.wind_speed_kmh == 2.2
    assert weather.wind_direction_deg == 245
    assert weather.wind_direction_text == "ทิศตะวันตกค่อนไปทางใต้"
    assert weather.pressure_hpa == 967.9
    assert weather.rain_15m_mm == 0
    assert weather.latest_update == "2026-06-04T11:46:00+07:00"
    assert weather.source == "Thai Meteorological Department AWS"

@patch("httpx.get")
def test_fetch_live_pm25_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "stations": [
            {
                "stationID": "35t",
                "nameTH": "ศาลากลางจังหวัดเชียงใหม่",
                "nameEN": "City Hall, Chiangmai",
                "areaTH": "ต.ช้างเผือก อ.เมือง, เชียงใหม่",
                "areaEN": "Chang Phueak, Meuang, Chiang Mai",
                "lat": "18.840732",
                "long": "98.96978",
                "AQILast": {
                    "date": "2026-05-31",
                    "time": "14:00",
                    "PM25": {
                        "value": "24.5"
                    }
                }
            },
            {
                "stationID": "12t",
                "nameTH": "สถานีกรุงเทพ",
                "nameEN": "Bangkok Station",
                "areaTH": "เขตพญาไท, กรุงเทพฯ",
                "areaEN": "Phaya Thai, Bangkok",
                "lat": "13.78",
                "long": "100.54",
                "AQILast": {
                    "date": "2026-05-31",
                    "time": "14:00",
                    "PM25": {
                        "value": "15.0"
                    }
                }
            }
        ]
    }
    mock_get.return_value = mock_response

    pm25 = fetch_live_pm25()
    
    assert pm25.current_pm25 == 24.5
    assert pm25.category == "ดี"
    assert len(pm25.stations) == 1
    assert pm25.stations[0].id == "CM-35T"
    assert pm25.stations[0].pm25 == 24.5
    assert pm25.stations[0].district == "Meuang"
    assert pm25.source == "Air4Thai Live API"

@patch("httpx.get")
def test_fetch_live_hotspots_nasa_fallback(mock_get):
    # Setup mock to fail Forest + GISTDA and succeed NASA
    mock_forest_resp = MagicMock()
    mock_forest_resp.raise_for_status.side_effect = Exception("Forest API Error")

    mock_gistda_resp = MagicMock()
    mock_gistda_resp.raise_for_status.side_effect = Exception("GISTDA API Error")
    
    mock_nasa_resp = MagicMock()
    mock_nasa_resp.content = b"latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n18.916,98.939,320.5,1.0,1.0,2026-05-31,0645,N,V,n,1.0,300.0,10.0,D"
    
    mock_get.side_effect = [mock_forest_resp, mock_gistda_resp, mock_nasa_resp]

    response = fetch_live_hotspots(gistda_key="gistda_key", nasa_key="nasa_key")

    assert response.count == 1
    assert response.source == "NASA FIRMS"
    assert response.items[0].latitude == 18.916
    assert response.items[0].longitude == 98.939
    assert response.items[0].district == "แม่ริม"
    assert response.items[0].confidence == 75

@patch("httpx.get")
def test_fetch_forest_firemap_hotspots_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "hotspot": [
            {
                "LAT": "18.90714000",
                "LONG": "98.20298000",
                "YYMMDD": "2026-06-01",
                "TIME": "242",
                "TUMBON": "แม่นาจร",
                "AUMPER": "แม่แจ่ม",
                "PROVINCE": "เชียงใหม่",
                "TYPE": "NRF",
                "NAME": "ป่าแม่แจ่ม",
            }
        ]
    }
    mock_get.return_value = mock_response

    hotspots = fetch_forest_firemap_hotspots()

    assert len(hotspots) == 1
    assert hotspots[0].id == "HS-RFD-001"
    assert hotspots[0].latitude == 18.90714
    assert hotspots[0].longitude == 98.20298
    assert hotspots[0].district == "แม่แจ่ม"
    assert hotspots[0].subdistrict == "แม่นาจร"
    assert hotspots[0].landuse_type == "NRF"
    assert hotspots[0].landuse_name == "ป่าแม่แจ่ม"
    assert hotspots[0].satellite == "SNPP/NOAA-20/NOAA-21 VIIRS"
    assert hotspots[0].confidence == 90
    assert hotspots[0].detected_at == "2026-06-01T02:42:00+07:00"

@patch("httpx.get")
def test_fetch_live_hotspots_gistda_success(mock_get):
    mock_forest_resp = MagicMock()
    mock_forest_resp.raise_for_status.side_effect = Exception("Forest API Error")

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [98.939, 18.916]
                },
                "properties": {
                    "pv_tn": "เชียงใหม่",
                    "ap_tn": "แม่ริม",
                    "confidence": "high",
                    "th_date": "2026-05-31T00:00:00",
                    "th_time": "1430"
                }
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [100.54, 13.78]
                },
                "properties": {
                    "pv_tn": "กรุงเทพมหานคร",
                    "ap_tn": "พญาไท",
                    "confidence": "nominal",
                    "th_date": "2026-05-31T00:00:00",
                    "th_time": "1430"
                }
            }
        ]
    }
    mock_get.side_effect = [mock_forest_resp, mock_response]

    response = fetch_live_hotspots(gistda_key="gistda_key")
    
    assert response.count == 1
    assert response.source == "GISTDA API Gateway VIIRS 1-day"
    assert response.items[0].latitude == 18.916
    assert response.items[0].longitude == 98.939
    assert response.items[0].district == "แม่ริม"
    assert response.items[0].confidence == 90
    assert response.items[0].detected_at == "2026-05-31T14:30:00+07:00"

@patch("httpx.get")
def test_fetch_live_hotspots_raises_when_forest_blocked_and_backups_empty(mock_get):
    mock_forest_resp = MagicMock()
    mock_forest_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403 Forbidden",
        request=MagicMock(),
        response=MagicMock(status_code=403),
    )

    mock_gistda_resp = MagicMock()
    mock_gistda_resp.json.return_value = {"features": []}
    mock_get.side_effect = [mock_forest_resp, mock_gistda_resp]

    with pytest.raises(Exception, match="Royal Forest Department Firemap unavailable"):
        fetch_live_hotspots(gistda_key="gistda_key")
