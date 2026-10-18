"""Pin the upstream pure-Python reference path for an offline benchmark.

The C extension needs MSVC on Windows. Upstream explicitly includes a
cython.compiled=False path, so no compiler installation or source patch is used.
"""
import hashlib,json
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/reference-tools/pyretechnics';OUT.mkdir(parents=True,exist_ok=True)
c=httpx.Client(timeout=30)
sha='a811ae508a5d7eeebb808b156e0e2066d4445602'
listing=c.get('https://api.github.com/repos/pyregence/pyretechnics/contents/src/pyretechnics',params={'ref':sha}).raise_for_status().json()
files=[]
for entry in listing:
    if not entry['name'].endswith('.py'):continue
    raw=c.get(entry['download_url']).raise_for_status().content;target=OUT/'pyretechnics'/entry['name'];target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
    files.append({'name':entry['name'],'sha256':hashlib.sha256(raw).hexdigest()})
license_data=c.get('https://api.github.com/repos/pyregence/pyretechnics/license',params={'ref':sha}).raise_for_status().json()
(OUT/'LICENSE').write_bytes(c.get(license_data['download_url']).raise_for_status().content)
(OUT/'SOURCE.json').write_text(json.dumps({'source':'https://github.com/pyregence/pyretechnics','commit':sha,'mode':'upstream pure Python fallback; unmodified',
     'license':license_data['license']['spdx_id'],'files':files},indent=2))
print('pinned',sha,'python_files',len(files),'license',license_data['license']['spdx_id'])

# MIT-licensed WRFx reference; only its moisture class is executed in the pilot.
wrfsha='5f30f37fd33796cad272602e36b645fd67f8e592'
url=f'https://raw.githubusercontent.com/openwfm/wrfxpy/{wrfsha}/src/fmda/fuel_moisture_model.py'
raw=c.get(url).raise_for_status().content
folder=ROOT/'output/reference-tools/wrfxpy';folder.mkdir(parents=True,exist_ok=True)
path=folder/'fuel_moisture_model.py'
if not path.exists():path.write_bytes(raw)
assert path.read_text(encoding='utf8')==raw.decode('utf8').replace('\r\n','\n')
(folder/'SOURCE.json').write_text(json.dumps({'commit':wrfsha,'url':url,'upstream_sha256':hashlib.sha256(raw).hexdigest(),
   'stored_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'license':'MIT permission notice retained in source'},indent=2))
print('WRFx pinned',wrfsha)
