"""Read-only, explicitly retrospective experiment; separate from live archives."""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix='/api/hindcast', tags=['Retrospective diagnostics'])

PRIORITY_ARTIFACT = Path(__file__).parent/'data/priority-validation.json'

@router.get('/2026/priority-validation')
def priority_validation():
    try:
        report=json.loads(PRIORITY_ARTIFACT.read_text(encoding='utf8'))
        if report.get('schema')!='cme-priority-validation-v1':
            raise ValueError('Unsupported priority validation artifact')
        return report
    except (OSError,ValueError):
        raise HTTPException(503,'ผลทดสอบพื้นที่เฝ้าระวังยังไม่พร้อม') from None

@router.get('/2026/grid-validation')
def grid_validation():
    try:
        return json.loads((Path(__file__).parent/'data/grid-spread-validation.json').read_text(encoding='utf8'))
    except (OSError,ValueError):
        raise HTTPException(503,'ผลตรวจรุ่นกริดยังไม่พร้อม') from None

@router.get('/2026/optimization')
def optimization():
    try:
        return json.loads((Path(__file__).parent/'data/prediction-optimization.json').read_text(encoding='utf8'))
    except (OSError,ValueError):
        raise HTTPException(503,'ผลค้นหาค่าพยากรณ์ยังไม่พร้อม') from None
ARTIFACT = Path(__file__).parent / 'data' / 'season-hindcast-2026.json'
VALIDATION_ARTIFACT = Path(__file__).parent / 'data' / 'dashboard-validation-2026.json'


@router.get('/2026')
def season_2026():
    try:
        report = json.loads(ARTIFACT.read_text(encoding='utf8'))
        if report.get('schema') != 'cme-season-hindcast-v1':
            raise ValueError('Unsupported experiment artifact')
        return report
    except (OSError, ValueError):
        raise HTTPException(503, 'ชุดทดลองย้อนหลังยังไม่พร้อม รันงานนำเข้าข้อมูลก่อน') from None


@router.get('/2026/validation')
def decision_validation(include_rows: bool = False):
    try:
        report=json.loads(VALIDATION_ARTIFACT.read_text(encoding='utf8'))
        if report.get('schema')!='cme-dashboard-validation-v1':
            raise ValueError('Unsupported validation artifact')
    except (OSError,ValueError):
        raise HTTPException(503,'ผลประเมินยังไม่พร้อม ไม่แทนข้อมูลที่ขาดด้วยคะแนนศูนย์') from None
    # Tables and maps load cheaply; exact paired rows remain public on request.
    if not include_rows:
        for section in (report.get('wind_station',{}),report.get('pm25_recent',{})):
            for values in section.get('by_lead',{}).values():values.pop('rows',None)
    return report
