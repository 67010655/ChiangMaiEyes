"""Offline spatial PM context, lagged calendar days only; no future PM input."""
import hashlib,json,time
import httpx
from download_joint_fire_inputs import OUT,POSITIONS,write
for year in (2024,2025,2026):
    path=OUT/f'cams-spatial-{year}.json'
    if path.exists():print('CAMS cached',year,flush=True);continue
    params={'latitude':','.join(str(p[0]) for p in POSITIONS),'longitude':','.join(str(p[1]) for p in POSITIONS),
      'start_date':f'{year}-01-01','end_date':f'{year}-04-30','timezone':'Asia/Bangkok','hourly':'pm2_5','domains':'cams_global'}
    for attempt in range(3):
        try:
            r=httpx.get('https://air-quality-api.open-meteo.com/v1/air-quality',params=params,timeout=60);r.raise_for_status();rows=r.json()
            assert isinstance(rows,list) and len(rows)==len(POSITIONS) and all('pm2_5' in row['hourly'] for row in rows)
            path.write_bytes(r.content);write(path.with_suffix('.receipt.json'),{'params':params,'sha256':hashlib.sha256(r.content).hexdigest(),
              'source':'https://open-meteo.com/en/docs/air-quality-api','use':'PastD-2 daily means only; archive does not establish exact historical issue/publication time. Not measured pollution.'})
            print('CAMS',year,len(rows),'timestamps',len(rows[0]['hourly']['time']),flush=True);break
        except (httpx.HTTPError,AssertionError):
            if attempt==2:raise RuntimeError(f'CAMS spatial download failed{year}') from None
            print('CAMS retry',year,attempt+1,flush=True);time.sleep(5)
