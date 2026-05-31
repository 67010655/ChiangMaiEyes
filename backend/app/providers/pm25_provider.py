import datetime
import logging
import httpx
from app.models import Pm25Response, Pm25Station

logger = logging.getLogger(__name__)

def get_pm25_category_and_color(pm25: float) -> tuple[str, str]:
    if pm25 <= 15.0:
        return "ดีมาก", "green"
    elif pm25 <= 25.0:
        return "ดี", "green"
    elif pm25 <= 37.5:
        return "ปานกลาง", "yellow"
    elif pm25 <= 75.0:
        return "เริ่มมีผลกระทบต่อสุขภาพ", "orange"
    elif pm25 <= 120.0:
        return "มีผลกระทบต่อสุขภาพ", "red"
    else:
        return "อันตราย", "purple"

def fetch_live_pm25() -> Pm25Response:
    url = "http://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
    logger.info(f"Fetching live PM2.5 from Air4Thai: {url}")
    
    try:
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()
        
        # Parse response as JSON (it uses UTF-8 encoding)
        data = response.json()
        raw_stations = data.get("stations", [])
        
        stations: list[Pm25Station] = []
        total_pm25 = 0.0
        valid_station_count = 0
        latest_time = None
        
        for s in raw_stations:
            area_th = s.get("areaTH", "")
            area_en = s.get("areaEN", "")
            
            # Filter for stations in Chiang Mai
            if "เชียงใหม่" in area_th or "Chiang Mai" in area_en or "Chiangmai" in area_en:
                aqi_last = s.get("AQILast", {})
                pm25_data = aqi_last.get("PM25", {})
                
                # Check for valid PM2.5 value
                pm25_val_str = pm25_data.get("value")
                if pm25_val_str is None:
                    continue
                    
                try:
                    pm25_val = float(pm25_val_str)
                    if pm25_val < 0: # Skip negative/invalid placeholder values
                        continue
                except ValueError:
                    continue
                
                # Format update time
                date_str = aqi_last.get("date", "")
                time_str = aqi_last.get("time", "")
                iso_time = f"{date_str}T{time_str}:00+07:00" if date_str and time_str else datetime.datetime.now().isoformat()
                
                if latest_time is None or iso_time > latest_time:
                    latest_time = iso_time
                
                district = s.get("areaEN", "").split(",")[-2].strip() if "," in s.get("areaEN", "") else "เมืองเชียงใหม่"
                if "District" in district:
                    district = district.replace("District", "").strip()
                
                station = Pm25Station(
                    id=f"CM-{s.get('stationID').upper()}",
                    name=s.get("nameTH", s.get("nameEN", "สถานีวัดคุณภาพอากาศ")),
                    district=district,
                    latitude=float(s.get("lat", 0.0)),
                    longitude=float(s.get("long", 0.0)),
                    pm25=pm25_val,
                    trend="stable",
                    updated_at=iso_time
                )
                stations.append(station)
                total_pm25 += pm25_val
                valid_station_count += 1
        
        if valid_station_count == 0:
            raise Exception("No active Chiang Mai PM2.5 stations found in Air4Thai feed")
            
        avg_pm25 = round(total_pm25 / valid_station_count, 1)
        category, color = get_pm25_category_and_color(avg_pm25)
        
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
        latest_update = latest_time if latest_time else now.isoformat()
        
        return Pm25Response(
            current_pm25=avg_pm25,
            category=category,
            color=color,
            trend="stable",
            latest_update=latest_update,
            source="Air4Thai Live API",
            stations=stations
        )
    except Exception as e:
        logger.error(f"Error fetching live PM2.5: {e}")
        raise e
