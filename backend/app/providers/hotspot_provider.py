import csv
import datetime
import logging
import httpx
from app.models import Hotspot, HotspotResponse

logger = logging.getLogger(__name__)
GISTDA_VIIRS_SOURCE = "GISTDA API Gateway VIIRS 1-day"

def estimate_district(lat: float, lon: float) -> str:
    # Simple and fast district approximation based on coordinates in Chiang Mai
    if lat > 19.6:
        return "ฝาง"
    elif lat > 19.1:
        return "เชียงดาว"
    elif lat > 18.85:
        return "แม่ริม"
    elif lat < 18.5:
        return "จอมทอง"
    else:
        return "หางดง"

def fetch_gistda_hotspots(api_key: str) -> list[Hotspot]:
    # GISTDA API Gateway daily VIIRS hotspots GeoJSON
    url = "https://api-gateway.gistda.or.th/api/2.0/resources/features/viirs/1day"
    logger.info(f"Attempting to fetch hotspots from GISTDA API Gateway: {url}")
    
    response = httpx.get(url, params={"api_key": api_key}, timeout=15.0, verify=False)
    response.raise_for_status()
    data = response.json()
    
    features = data.get("features", [])
    hotspots: list[Hotspot] = []
    
    idx = 1
    for f in features:
        try:
            properties = f.get("properties", {})
            # Filter specifically for Chiang Mai province
            if properties.get("pv_tn") == "เชียงใหม่":
                geometry = f.get("geometry", {})
                coords = geometry.get("coordinates", [])
                if len(coords) < 2:
                    continue
                lon = float(coords[0])
                lat = float(coords[1])
                
                # Confidence mapping
                conf_raw = str(properties.get("confidence", "nominal")).lower()
                if conf_raw == "high" or conf_raw == "h":
                    confidence = 90
                elif conf_raw == "low" or conf_raw == "l":
                    confidence = 50
                else:
                    confidence = 75
                
                # Format update date/time from Thai date/time
                th_date = properties.get("th_date", "")
                th_time = properties.get("th_time", "0000")
                if th_date and len(th_time) == 4:
                    detected_at = f"{th_date[:10]}T{th_time[:2]}:{th_time[2:]}:00+07:00"
                else:
                    detected_at = datetime.datetime.now().isoformat()
                
                hotspots.append(Hotspot(
                    id=f"HS-GISTDA-{idx:03d}",
                    latitude=lat,
                    longitude=lon,
                    district=properties.get("ap_tn") or estimate_district(lat, lon),
                    confidence=confidence,
                    source=GISTDA_VIIRS_SOURCE,
                    detected_at=detected_at
                ))
                idx += 1
        except Exception as ex:
            logger.warning(f"Error parsing GISTDA API Gateway hotspot feature: {ex}")
            continue
            
    return hotspots

def fetch_nasa_firms_hotspots(map_key: str) -> list[Hotspot]:
    # NASA FIRMS Area API bounding box for Chiang Mai
    # Format: west, south, east, north
    bbox = "97.25,17.35,99.68,20.28"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_NRT/{bbox}/1"
    logger.info(f"Attempting to fetch NASA FIRMS hotspots: {url}")
    
    response = httpx.get(url, timeout=15.0)
    response.raise_for_status()
    
    # NASA FIRMS returns CSV data
    decoded_content = response.content.decode("utf-8")
    lines = decoded_content.splitlines()
    reader = csv.DictReader(lines)
    
    hotspots: list[Hotspot] = []
    for idx, row in enumerate(reader):
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            
            # Map VIIRS confidence (usually 'n' for nominal, 'h' for high, 'l' for low)
            conf_raw = row.get("confidence", "n").lower()
            if conf_raw == "h":
                confidence = 90
            elif conf_raw == "n":
                confidence = 75
            else:
                confidence = 50
                
            # Formatting acquisition time acq_time is e.g. "0645"
            acq_date = row.get("acq_date", datetime.date.today().isoformat())
            acq_time = row.get("acq_time", "0000")
            if len(acq_time) == 4:
                time_str = f"{acq_time[:2]}:{acq_time[2:]}:00+07:00"
            else:
                time_str = "00:00:00+07:00"
            detected_at = f"{acq_date}T{time_str}"
            
            hotspots.append(Hotspot(
                id=f"HS-NASA-{idx + 1:03d}",
                latitude=lat,
                longitude=lon,
                district=estimate_district(lat, lon),
                confidence=confidence,
                source="NASA FIRMS",
                detected_at=detected_at
            ))
        except Exception as ex:
            logger.warning(f"Error parsing NASA FIRMS hotspot row: {ex}")
            continue
            
    return hotspots

def fetch_live_hotspots(gistda_key: str | None = None, nasa_key: str | None = None) -> HotspotResponse:
    hotspots: list[Hotspot] = []
    source = "Unknown"
    fetched_successfully = False
    
    # Try GISTDA API Gateway VIIRS first
    if gistda_key:
        try:
            hotspots = fetch_gistda_hotspots(gistda_key)
            source = GISTDA_VIIRS_SOURCE
            fetched_successfully = True
            logger.info(f"Loaded {len(hotspots)} hotspots from GISTDA API Gateway VIIRS")
        except Exception as e:
            logger.error(f"GISTDA API Gateway VIIRS fetch failed, attempting NASA backup: {e}")
            
    # Try NASA FIRMS backup if GISTDA failed or had no key
    if not fetched_successfully and nasa_key:
        try:
            hotspots = fetch_nasa_firms_hotspots(nasa_key)
            source = "NASA FIRMS Live API"
            fetched_successfully = True
            logger.info(f"Loaded {len(hotspots)} hotspots from NASA FIRMS")
        except Exception as e:
            logger.error(f"NASA FIRMS fetch failed: {e}")
            
    if not fetched_successfully:
        raise Exception("Failed to fetch live hotspots from both GISTDA and NASA")
        
    count = len(hotspots)
    # Area of Chiang Mai is approximately 20,107 km2
    density = round((count / 20107.0) * 100.0, 2)
    
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    latest_update = now.isoformat()
    
    return HotspotResponse(
        count=count,
        density_per_100_km2=density,
        latest_update=latest_update,
        source=source,
        items=hotspots
    )
