"""Small prior-run weather input, no hindsight ERA5 in the new experiment."""
import hashlib,json,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/priority-forecast-20261017';OUT.mkdir(parents=True,exist_ok=True)
FIELDS=('temperature_2m','relative_humidity_2m','precipitation','wind_speed_10m','wind_direction_10m','shortwave_radiation')
for year in (2024,2025,2026):
    path=OUT/f'gfs-weather-{year}.json'
    if path.exists():print('cached',year,flush=True);continue
    params={'latitude':18.79,'longitude':98.99,'start_date':f'{year}-01-01','end_date':f'{year}-04-30',
       'hourly':','.join(f+'_previous_day1' for f in FIELDS),'wind_speed_unit':'ms','timezone':'UTC','models':'gfs_seamless'}
    for attempt in range(3):
        try:
            r=httpx.get('https://previous-runs-api.open-meteo.com/v1/forecast',params=params,timeout=60);r.raise_for_status();body=r.json()
            if 'hourly' not in body:raise ValueError('Hourly data missing')
            path.write_bytes(r.content)
            path.with_suffix('.receipt.json').write_text(json.dumps({'source':'https://open-meteo.com/en/docs/previous-runs-api','params':params,
                'sha256':hashlib.sha256(r.content).hexdigest(),'meaning':'Province reference-point stitched previous-day1 forecast, not a local terrain wind field or single issued run.'},indent=2))
            print('downloaded',year,'hours',len(body['hourly']['time']),'nonmissing',{k:sum(v is not None for v in body['hourly'][k+'_previous_day1']) for k in FIELDS},flush=True);break
        except (httpx.HTTPError,ValueError):
            if attempt==2:raise RuntimeError(f'Weather download failed for {year}') from None
            time.sleep(5)
