"""Offline inputs for hotspot/wind/PM ablation. Never writes app or web data."""
import hashlib,json,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx,openpyxl
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/joint-fire-model-20261017';OUT.mkdir(parents=True,exist_ok=True)
FIELDS=('wind_speed_10m','wind_direction_10m','temperature_2m','relative_humidity_2m','precipitation')
# 3 longitude bands x 4 latitude bands; nearest location supplies coarse GFS,
# not terrain-resolved local winds. Centres span the whole province.
POSITIONS=[(lat,lon) for lat in (17.5,18.25,19.,19.75) for lon in (98.25,98.85,99.45)]
def write(p,b):p.write_text(json.dumps(b,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def pm_source(year):
    if year in (2025,2026):return ROOT/f'output/decision-validation-20261017/pm25/daily-{year}.xlsx'
    path=OUT/f'air4thai-daily-{year}.xlsx'
    if path.exists():return path
    urls=[f'https://{host}/daily_download/PM2.5/{year}.xlsx' for host in ('air4thai.net','air4thai.com','air4thai.pcd.go.th')]
    def probe(url):
        try:
            response=httpx.get(url,timeout=30,follow_redirects=True)
            if response.status_code==200 and response.content[:2]==b'PK':return url,response.content
            print('pm source',year,response.status_code,url.split('/')[2],flush=True)
        except httpx.HTTPError as e:print('pm source',year,type(e).__name__,url.split('/')[2],flush=True)
        return None
    with ThreadPoolExecutor(3) as pool:
        result=next((r for r in pool.map(probe,urls) if r is not None),None)
    if not result:raise RuntimeError(f'No usable official PM workbook for{year}; do not fabricate values.')
    url,raw=result;path.write_bytes(raw);write(path.with_suffix('.receipt.json'),{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)});return path
def extract_pm(year):
    source=pm_source(year);workbook=openpyxl.load_workbook(source,read_only=True,data_only=True)
    data_name=next(name for name in workbook.sheetnames if name.lower()=='data')
    sheet=workbook[data_name];rows=sheet.iter_rows(values_only=True);header=next(rows);indices={s:header.index(s) for s in ('35T','36T') if s in header}
    if len(indices)!=2:raise ValueError('Expected two Chiang Mai station columns not found')
    dates={}
    for row in rows:
        date=row[0]
        if not isinstance(date,datetime) or not datetime(year,1,1)<=date<datetime(year,5,1):continue
        dates[str(date.date())]={s:float(row[i]) if isinstance(row[i],(int,float)) and row[i]>=0 else None for s,i in indices.items()}
    workbook.close();report={'source_file':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
      'stations':list(indices),'unit':'ug/m3','dates':dates,'averaging':'official daily24h; exact window and as-published release times unverified',
      'availability_rule':'For issue local date D use only dates<=D-2; conservative24h delay after assumed calendar-day end, not verified issue archive.'}
    write(OUT/f'pm-{year}.json',report);print('PM',year,len(dates),{s:sum(d[s] is not None for d in dates.values()) for s in indices},flush=True)
def wind(year):
    path=OUT/f'gfs-spatial-{year}.json'
    if path.exists():print('wind cached',year,flush=True);return
    params={'latitude':','.join(str(p[0]) for p in POSITIONS),'longitude':','.join(str(p[1]) for p in POSITIONS),
      'hourly':','.join(f+'_previous_day1' for f in FIELDS),'start_date':f'{year}-01-01','end_date':f'{year}-04-30',
      'timezone':'UTC','models':'gfs_seamless','wind_speed_unit':'ms'}
    for attempt in range(3):
        try:
            response=httpx.get('https://previous-runs-api.open-meteo.com/v1/forecast',params=params,timeout=90);response.raise_for_status();body=response.json()
            assert isinstance(body,list) and len(body)==len(POSITIONS) and all('hourly' in r for r in body)
            path.write_bytes(response.content);write(path.with_suffix('.receipt.json'),{'params':params,'sha256':hashlib.sha256(response.content).hexdigest(),'source':'https://open-meteo.com/en/docs/previous-runs-api','requested_positions':POSITIONS})
            print('wind',year,len(body),'hours',len(body[0]['hourly']['time']),flush=True);return
        except (httpx.HTTPError,AssertionError):
            if attempt==2:raise RuntimeError(f'Spatial GFS download failed for{year}') from None
            print('wind retry',year,attempt+1,flush=True);time.sleep(5)
def main():
    for year in (2024,2025,2026):wind(year)
    for year in (2024,2025,2026):extract_pm(year)
if __name__=='__main__':main()
