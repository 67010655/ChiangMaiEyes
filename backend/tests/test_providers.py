from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.providers.weather_provider import fetch_live_weather, get_wind_direction_text
from app.providers.pm25_provider import fetch_live_pm25, get_pm25_category_and_color
from app.providers.hotspot_provider import fetch_live_hotspots, estimate_district

def test_wind_direction_translation():
    assert get_wind_direction_text(0) == "เหนือ"
    assert get_wind_direction_text(225) == "ตะวันตกเฉียงใต้"
    assert get_wind_direction_text(270) == "ตะวันตก"
    assert get_wind_direction_text(359) == "เหนือ"

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
    assert estimate_district(18.9, 99.0) == "แม่ริม"
    assert estimate_district(18.7, 99.0) == "หางดง"
    assert estimate_district(18.2, 99.0) == "จอมทอง"

@patch("httpx.get")
def test_fetch_live_weather_success(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "current": {
            "temperature_2m": 31.5,
            "relative_humidity_2m": 60,
            "wind_speed_10m": 12.5,
            "wind_direction_10m": 225
        }
    }
    mock_get.return_value = mock_response

    weather = fetch_live_weather()
    
    assert weather.temperature_c == 31.5
    assert weather.humidity_percent == 60
    assert weather.wind_speed_kmh == 12.5
    assert weather.wind_direction_deg == 225
    assert weather.wind_direction_text == "ตะวันตกเฉียงใต้"
    assert weather.source == "Open-Meteo Live API"

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
    # Setup mock to fail GISTDA and succeed NASA
    mock_gistda_resp = MagicMock()
    mock_gistda_resp.raise_for_status.side_effect = Exception("GISTDA API Error")
    
    mock_nasa_resp = MagicMock()
    mock_nasa_resp.content = b"latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight\n18.916,98.939,320.5,1.0,1.0,2026-05-31,0645,N,V,n,1.0,300.0,10.0,D"
    
    mock_get.side_effect = [mock_gistda_resp, mock_nasa_resp]

    response = fetch_live_hotspots(gistda_key="gistda_key", nasa_key="nasa_key")
    
    assert response.count == 1
    assert response.source == "NASA FIRMS Live API"
    assert response.items[0].latitude == 18.916
    assert response.items[0].longitude == 98.939
    assert response.items[0].district == "แม่ริม"
    assert response.items[0].confidence == 75

@patch("httpx.get")
def test_fetch_live_hotspots_gistda_success(mock_get):
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
    mock_get.return_value = mock_response

    response = fetch_live_hotspots(gistda_key="gistda_key")
    
    assert response.count == 1
    assert response.source == "GISTDA API Gateway VIIRS 1-day"
    assert response.items[0].latitude == 18.916
    assert response.items[0].longitude == 98.939
    assert response.items[0].district == "แม่ริม"
    assert response.items[0].confidence == 90
    assert response.items[0].detected_at == "2026-05-31T14:30:00+07:00"
