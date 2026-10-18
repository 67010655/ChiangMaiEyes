"""Historical land context and cited fire-ecology reference, never a fuel model."""
from __future__ import annotations
import gzip
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
import re

from fastapi import APIRouter, Query

DATA = Path(__file__).parent / 'data'
router = APIRouter(prefix='/api/land-context', tags=['Land context'])
QUALIFIER = 'ประเมินจากแผนที่ ไม่ใช่การสำรวจในพื้นที่'
LDD_URL = 'https://service.ldd.go.th/lpd/node_modules/img/Landusedistrict/2567/r04_ssk_11.pdf'
WORLD_URL = 'https://esa-worldcover.org/en/data-access'
LABELS = {
    'deciduous': 'ป่าผลัดใบ (เช่น เต็งรัง/เบญจพรรณ)',
    'evergreen': 'ป่าไม่ผลัดใบ', 'dipterocarp': 'ป่าเต็งรัง', 'mixed_deciduous': 'ป่าเบญจพรรณ',
    'unknown_forest': 'พื้นที่ป่า/ต้นไม้ (จุดนี้ยังระบุชนิดป่าไม่ได้)',
    'plantation': 'ป่าปลูก', 'shrub': 'ไม้พุ่ม', 'grass': 'ทุ่งหญ้า',
    'crop': 'พื้นที่เกษตร', 'built': 'ชุมชนและสิ่งปลูกสร้าง', 'bare': 'พื้นที่โล่งหรือพืชเบาบาง',
    'water': 'แหล่งน้ำ', 'wetland': 'พื้นที่ชุ่มน้ำ', 'unknown': 'ยังระบุชนิดพื้นที่ไม่ได้',
}
WORLD_CLASSES = {10:'unknown_forest',20:'shrub',30:'grass',40:'crop',50:'built',60:'bare',80:'water',90:'wetland',95:'unknown_forest'}


@lru_cache(maxsize=1)
def raster(name):
    if name != 'spread-landcover':
        raise ValueError('Only ESA WorldCover is enabled for point land context')
    meta = json.loads((DATA / f'{name}.json').read_text(encoding='utf-8'))
    raw = gzip.decompress((DATA / f'{name}.bin.gz').read_bytes())
    if len(raw) != meta['width'] * meta['height'] or hashlib.sha256(raw).hexdigest() != meta['sha256']:
        raise ValueError('Land-context raster checksum/shape mismatch')
    return meta, raw


def sample(name, lat, lon):
    try:
        meta, raw = raster(name)
        row = math.floor((meta['north'] - lat) / meta['step_degrees'])
        col = math.floor((lon - meta['west']) / meta['step_degrees'])
        if not (0 <= row < meta['height'] and 0 <= col < meta['width']):
            return None
        code = raw[row * meta['width'] + col]
        return None if code in (meta['nodata'], meta.get('unknown', -1)) else code
    except (OSError, ValueError, KeyError, gzip.BadGzipFile):
        return None


def ldd_context(code, name):
    code, name = (code or '').strip().upper(), (name or '').strip()
    # Only one unambiguous land-use code, not a mixed map unit or jurisdiction
    # code such as NRF/CONSERVATION. F201 alone must never mean a forest subtype.
    named_forest = code in ('','OTHER','O000') and any(word in name for word in ('เต็งรัง','เบญจพรรณ','ผสมผลัดใบ','ผลัดใบ','ป่าดิบ','ป่าปลูก'))
    if not re.fullmatch(r'[AFUW]\d{3}', code) and not named_forest:
        return None
    if code.startswith('A'):
        # Aquaculture is agricultural land use, but is not evidence of crop fire.
        if code.startswith('A9'):
            return 'water', 'พื้นที่เพาะเลี้ยงสัตว์น้ำ'
        return 'crop', 'พื้นที่เกษตร' + (' (นาข้าว)' if code == 'A101' else f' ({name})' if name and not re.search(r'[A-Za-z<>]', name) else '')
    if code.startswith('F') or named_forest:
        # Use an explicit upstream Thai subtype label, never an ambiguous code
        # from a different LDD edition. Preserve only supported canonical labels.
        dipterocarp = 'เต็งรัง' in name
        mixed = 'เบญจพรรณ' in name or 'ผสมผลัดใบ' in name
        evergreen = 'ไม่ผลัดใบ' in name or 'ป่าดิบ' in name
        if evergreen and (dipterocarp or mixed):
            return 'unknown_forest', LABELS['unknown_forest']
        if dipterocarp and mixed:
            return 'deciduous', LABELS['deciduous']
        if dipterocarp:
            return 'dipterocarp', LABELS['dipterocarp']
        if mixed:
            return 'mixed_deciduous', LABELS['mixed_deciduous']
        if evergreen:
            return 'evergreen', LABELS['evergreen']
        if 'ผลัดใบ' in name or code in ('F200', 'F201'):
            return 'deciduous', LABELS['deciduous']
        if code in ('F100', 'F101'):
            return 'evergreen', LABELS['evergreen']
        if code.startswith('F5') or 'ป่าปลูก' in name:
            return 'plantation', LABELS['plantation']
        return 'unknown_forest', LABELS['unknown_forest']
    if code.startswith('U'):
        return 'built', LABELS['built']
    return 'water', LABELS['water']


@lru_cache(maxsize=1)
def reference():
    return json.loads((DATA / 'land-context-reference.json').read_text(encoding='utf-8'))


def resolve(lat, lon, code=None, name=None):
    direct = ldd_context(code, name)
    world = sample('spread-landcover', lat, lon) if not direct else None
    sources = []
    if direct:
        kind, label = direct
        sources.append({'name':'GISTDA · การใช้ที่ดินกรมพัฒนาที่ดิน', 'url':LDD_URL,
                        'year':None, 'note':'ใช้รหัส/ชื่อที่มากับจุดความร้อน; ต้นทางไม่ระบุปีสำรวจการใช้ที่ดิน'})
    elif world in WORLD_CLASSES:
        kind = WORLD_CLASSES[world]
        label = LABELS[kind]
        sources.append({'name':'ESA WorldCover', 'url':WORLD_URL, 'year':2021,
                        'note':'ข้อมูลต้นฉบับ 10 ม. ชุดใน repo สุ่มใกล้สุดลงกริดประมาณ 100 ม.; ไม่ใช่ภาพปัจจุบัน'})
    else:
        kind, label = 'unknown', LABELS['unknown']
    headline = label + (' · น่าจะเป็นการเผาในแปลง ไม่ใช่ไฟป่า' if kind == 'crop' else '')
    return {'kind':kind, 'label':label, 'headline':headline, 'qualifier':QUALIFIER,
            'status':'available' if kind != 'unknown' else 'unavailable', 'sources':sources,
            'note':'จุดความร้อนไม่ยืนยันชนิดไฟหรือสาเหตุ; ไฟในแปลงอาจลามเข้าป่าได้',
            'reference':reference()['profiles'].get(kind, reference()['profiles']['unknown']),
            'province_context':reference().get('province_context') if kind == 'unknown_forest' else None,
            'reference_sources':reference()['sources'], 'map_years':[s['year'] for s in sources if s['year']]}


@router.get('')
def read_context(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                 landuse_type: str = Query(default='', max_length=100), landuse_name: str = Query(default='', max_length=200)):
    return resolve(latitude, longitude, landuse_type, landuse_name)
