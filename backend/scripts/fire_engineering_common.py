"""Isolated output paths and helpers for the 2026-10-18 offline engineering loop."""
from pathlib import Path
import hashlib,json
import uuid
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/fire-engineering-20261018'
OLD=ROOT/'output/fire-perimeter-loop-20261017'

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.'+uuid.uuid4().hex+'.writing')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    temporary.replace(path)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def array_content_sha(path):
    import numpy as np
    digest=hashlib.sha256()
    with np.load(path,allow_pickle=False) as archive:
        for name in sorted(archive.files):
            value=archive[name]
            digest.update(name.encode());digest.update(value.dtype.str.encode());digest.update(str(value.shape).encode());digest.update(value.tobytes())
    return digest.hexdigest()
def configure():
    import build_timed_fire_cases as fetch
    import prepare_timed_fire_arrays as arrays
    import timed_fire_spread_benchmark as physics
    import timed_fire_growth_ml as ml
    fetch.OUT=arrays.OUT=physics.OUT=ml.OUT=OUT
    ml.FOLDER=OUT/'growth-ml'
    return fetch,arrays,physics,ml
