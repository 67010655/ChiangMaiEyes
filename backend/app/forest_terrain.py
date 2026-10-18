"""Preprocessed public DSM summaries. No terrain downloads in API requests."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix='/api/forest-terrain', tags=['Public terrain'])
DATA = Path(__file__).parent/'data/forest-terrain-copernicus.json'
BOUNDARIES = Path(__file__).parent/'data/community-forests-chiangmai.geojson'


@lru_cache(maxsize=1)
def dataset():
    try:
        body = json.loads(DATA.read_text(encoding='utf8'))
        if body['boundary_sha256'] != hashlib.sha256(BOUNDARIES.read_bytes()).hexdigest():
            raise ValueError('Terrain boundary version mismatch')
        rows = {row['forest_id']:row for row in body['forests']}
        if len(rows)!=677 or body['forest_count']!=677:
            raise ValueError('Incomplete forest terrain dataset')
        return {k:v for k,v in body.items() if k!='forests'}, rows
    except (OSError,ValueError,KeyError,TypeError):
        raise HTTPException(503,'ข้อมูลภูมิประเทศยังไม่พร้อมหรือขอบเขตเปลี่ยน ยังไม่ใช้ค่าคงที่แทน') from None


@router.get('')
def read_terrain(response:Response,forest_id:str|None=Query(None,max_length=100)):
    metadata,rows = dataset()
    if forest_id is not None and forest_id not in rows:
        raise HTTPException(404,'ไม่พบป่าชุมชนในชุดขอบเขต')
    response.headers['Cache-Control']='public, max-age=0, s-maxage=3600'
    return {'metadata':metadata,'forest':rows[forest_id]} if forest_id else {'metadata':metadata,'forests':list(rows.values())}
