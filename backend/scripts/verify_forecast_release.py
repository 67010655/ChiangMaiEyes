import json
import re
import sys
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.config import get_settings

out=ROOT/'output/live-spread-backtest-20261017'
base='https://chiangmaieyes.vercel.app'
with httpx.Client(timeout=60) as client:
    for name,path in [('live','/api/spread/live'),('primary','/api/fire-predictions'),('archive','/api/forecast/archive')]:
        response=client.get(base+path);response.raise_for_status();data=response.json()
        (out/f'production-{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
        print(name,{k:data[k] for k in ('status','used_points','provider_status') if k in data})
    archive=data
    print('archive_runs',len(archive['runs']))
    old=client.get(base+'/').text;new=(ROOT/'frontend/index.html').read_text(encoding='utf8')
    ids=lambda text:set(re.findall(r'\bid="([^"]+)"',text))
    print('removed_static_ids',sorted(ids(old)-ids(new)))
    settings=get_settings()
    path=archive['runs'][0]['path']
    response=client.get(settings.supabase_url+'/storage/v1/object/public/cme-forecast-evidence/'+path)
    print('anonymous_bucket_status',response.status_code)
    assert response.status_code>=400
