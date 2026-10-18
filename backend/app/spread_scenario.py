"""Conditional surface-fire scenarios, never operational warnings.

Single fine dead-fuel class: Rothermel with the Albini1976 reaction-velocity
exponent used by firelab/behave. Empirical equations run in native imperial
units; API values are SI. Static homogeneous conditions and a focal ellipse.
This is not a spatial fuel raster solver, ignition model or probability model.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

router = APIRouter(prefix='/api/spread', tags=['Experimental fire scenarios'])
VERSION = 'cme-single-dead-albini1976-ellipse-v1'
SOURCE_COMMIT = 'd4acc8a074646c754673b6725234fdf3a1e9c053'
SOURCE = f'https://github.com/firelab/behave/tree/{SOURCE_COMMIT}/src/behave'
FT = .3048
LB = .45359237
BTU_KJ = 1.05505585262
EARTH_M = 6371008.8
MATERIAL_DEFAULTS = {'particle_density_kg_m3':32*LB/FT**3, 'heat_kj_kg':8000*BTU_KJ/LB,
                     'total_mineral_pct':5.55, 'effective_mineral_pct':1.0}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Evidence(Strict):
    basis: Literal['measured', 'assumed', 'reference']
    source: str = Field(min_length=5, max_length=1000)
    observed_at: datetime

    @field_validator('observed_at')
    @classmethod
    def time_zone(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('ระบุเขตเวลาในวันเวลาข้อมูล')
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('วันเวลาของข้อมูลต้องไม่อยู่ในอนาคต')
        return value


class Fuel(Strict):
    load_kg_m2: float = Field(ge=.0001, le=10)
    depth_m: float = Field(ge=.001, le=3)
    savr_per_m: float = Field(ge=200, le=40000)
    moisture_pct: float = Field(ge=0, le=300)
    extinction_moisture_pct: float = Field(gt=0, le=100)
    # Material constants from Behave, explicitly returned with the inputs.
    # They are not claimed to have been measured in a Chiang Mai forest.
    particle_density_kg_m3: float = Field(default=32*LB/FT**3, ge=100, le=1500)
    heat_kj_kg: float = Field(default=8000*BTU_KJ/LB, ge=1000, le=30000)
    total_mineral_pct: float = Field(default=5.55, ge=.0001, lt=100)
    effective_mineral_pct: float = Field(default=1, ge=.0001, lt=100)
    material_basis: Literal['behave_reference','user_specified'] = 'behave_reference'
    material_source: str | None = Field(default=None,min_length=5,max_length=1000)
    evidence: Evidence

    @model_validator(mode='after')
    def packing(self):
        if self.load_kg_m2/self.depth_m >= self.particle_density_kg_m3:
            raise ValueError('ความหนาแน่นชั้นเชื้อเพลิงต้องต่ำกว่าความหนาแน่นเนื้อเชื้อเพลิง')
        if self.effective_mineral_pct > self.total_mineral_pct:
            raise ValueError('สัดส่วนแร่ที่มีผลต้องไม่เกินสัดส่วนแร่ทั้งหมด')
        if self.material_basis == 'behave_reference':
            if any(not math.isclose(getattr(self,k),v,rel_tol=1e-10) for k,v in MATERIAL_DEFAULTS.items()) or self.material_source is not None:
                raise ValueError('ค่าคุณสมบัติวัสดุเปลี่ยนจากมาตรฐาน ต้องเลือกระบุเองและให้ที่มาแยก')
        elif not self.material_source:
            raise ValueError('ระบุที่มาความหนาแน่น ค่าความร้อน และแร่ธาตุที่กรอกเอง')
        return self


class Wind(Strict):
    midflame_mps: float = Field(ge=0, le=20)
    from_deg: float = Field(ge=0, lt=360)
    evidence: Evidence


class Terrain(Strict):
    mode: Literal['copernicus_forest_point', 'manual']
    slope_deg: float | None = Field(default=None, ge=0, le=60)
    upslope_to_deg: float | None = Field(default=None, ge=0, lt=360)
    evidence: Evidence | None = None


class Scenario(Strict):
    forest_id: str | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=17, le=21)
    longitude: float | None = Field(default=None, ge=98, le=100)
    start_at: datetime
    duration_minutes: int = Field(default=180, ge=30, le=360)
    fuel: Fuel
    wind: Wind
    terrain: Terrain
    moisture_range_pct: tuple[float, float] | None = None
    apply_legacy_wind_limit: bool = False

    @model_validator(mode='after')
    def check(self):
        if self.start_at.tzinfo is None or self.start_at.utcoffset() is None:
            raise ValueError('เวลาเริ่มต้องระบุเขตเวลา')
        if self.start_at.year < 2000 or self.start_at > datetime.now(timezone.utc) + timedelta(days=2):
            raise ValueError('ใช้เวลาเริ่มตั้งแต่ปี 2000 ถึงไม่เกิน 48 ชั่วโมงข้างหน้า')
        t = self.terrain
        if t.mode == 'copernicus_forest_point':
            if not self.forest_id:
                raise ValueError('เลือกป่าเพื่ออ่านจุดตัวอย่างภูมิประเทศ')
            if any(x is not None for x in (self.latitude, self.longitude, t.slope_deg, t.upslope_to_deg, t.evidence)):
                raise ValueError('โหมด DSM ใช้พิกัดและความชันจากชุดข้อมูลเท่านั้น')
        elif any(x is None for x in (self.latitude, self.longitude, t.slope_deg, t.upslope_to_deg, t.evidence)):
            raise ValueError('กรอกพิกัด ความชัน ทิศขึ้นเขา และที่มาภูมิประเทศให้ครบ')
        if self.moisture_range_pct is not None:
            lo, hi = self.moisture_range_pct
            if not all(math.isfinite(v) for v in (lo,hi)) or not 0 <= lo <= self.fuel.moisture_pct <= hi <= 300 or lo == hi:
                raise ValueError('ช่วงความชื้นต้องครอบค่าหลักและอยู่ในช่วง 0–300%')
        return self


@lru_cache(maxsize=1)
def point_dataset():
    try:
        root = Path(__file__).parent/'data'
        data = json.loads((root/'forest-terrain-points.json').read_text(encoding='utf8'))
        if data['boundary_sha256'] != hashlib.sha256((root/'community-forests-chiangmai.geojson').read_bytes()).hexdigest():
            raise ValueError('Boundary version mismatch')
        if len(data['points']) != 677:
            raise ValueError('Incomplete terrain point dataset')
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'จุดภูมิประเทศยังไม่พร้อม ไม่เติมความชันสมมติแทน') from None


@router.get('/terrain-point')
def terrain_point(forest_id: str = Query(max_length=100)):
    data = point_dataset()
    row = data['points'].get(forest_id)
    if row is None:
        raise HTTPException(404, 'ไม่พบรหัสป่า')
    if row['status'] != 'available':
        raise HTTPException(422, 'ขอบเขตหรือจุดภูมิประเทศนี้ต้องตรวจสอบก่อน ยังใช้จำลองไม่ได้')
    return {'point': row, 'metadata': data['metadata']}


def resolve_terrain(req: Scenario):
    if req.terrain.mode == 'copernicus_forest_point':
        doc = terrain_point(req.forest_id)
        row = doc['point']
        return row['latitude'], row['longitude'], {
            'slope_deg': row['slope_deg'], 'upslope_to_deg': row['upslope_to_deg'],
            'elevation_m': row['elevation_m'], 'mode': req.terrain.mode,
            'source': doc['metadata'], 'sample_sha256': row['sample_sha256'],
        }
    return req.latitude, req.longitude, req.terrain.model_dump(mode='json')


def rate_of_spread(fuel: Fuel, wind: Wind, slope_deg: float, upslope_deg: float, *, cap=False):
    """Published single-dead equations, Albini1976 exponent; SI output.

    No live fuels, dynamic herbaceous transfer, spotting, crown fires, barriers
    or suppression. Wind is measured/declared at midflame, never raw 10 m.
    """
    w = fuel.load_kg_m2*FT**2/LB
    depth = fuel.depth_m/FT
    sigma = fuel.savr_per_m*FT
    density = fuel.particle_density_kg_m3*FT**3/LB
    heat = fuel.heat_kj_kg*LB/BTU_KJ
    moisture = fuel.moisture_pct/100
    ratio = fuel.moisture_pct/fuel.extinction_moisture_pct
    bulk = w/depth
    beta = bulk/density
    beta_opt = 3.348*sigma**(-.8189)
    a = 133*sigma**(-.7913)
    gamma_max = sigma**1.5/(495+.0594*sigma**1.5)
    gamma = gamma_max*(beta/beta_opt)**a*math.exp(a*(1-beta/beta_opt))
    eta_m = max(0, 1-2.59*ratio+5.11*ratio**2-3.52*ratio**3) if ratio < 1 else 0
    eta_s = min(1, .174*(fuel.effective_mineral_pct/100)**(-.19))
    reaction = gamma*w*(1-fuel.total_mineral_pct/100)*heat*eta_m*eta_s
    flux = math.exp((.792+.681*math.sqrt(sigma))*(beta+.1))/(192+.2595*sigma)
    heat_sink = bulk*math.exp(-138/sigma)*(250+1116*moisture)
    base = reaction*flux/heat_sink
    c = 7.47*math.exp(-.133*sigma**.55)
    b = .02526*sigma**.54
    e = .715*math.exp(-.000359*sigma)
    wind_ft_min = wind.midflame_mps*60/FT
    phi_w = c*wind_ft_min**b*(beta/beta_opt)**(-e)
    phi_s = 5.275*beta**(-.3)*math.tan(math.radians(slope_deg))**2
    delta = math.radians((wind.from_deg+180-upslope_deg) % 360)
    x, y = phi_s+phi_w*math.cos(delta), phi_w*math.sin(delta)
    phi = math.hypot(x,y)
    if phi < 1e-12:
        phi, heading = 0.0, None
    else:
        heading = (upslope_deg+math.degrees(math.atan2(y,x))) % 360
    effective = (phi*(beta/beta_opt)**e/c)**(1/b) if phi else 0
    exceeded = effective > .9*reaction
    uncapped = base*(1+phi)*FT
    if cap and exceeded:
        effective = .9*reaction
        phi = c*effective**b*(beta/beta_opt)**(-e)
    head = base*(1+phi)*FT
    mph = effective/88
    # The Behave Anderson length/width relation is capped at 8; avoid exp
    # overflow for extreme unsupported inputs before evaluating the relation.
    lw = min(8, max(1, .936*math.exp(.1147*min(mph,50))+.461*math.exp(-.0692*min(mph,50))-.397))
    ecc = math.sqrt(lw*lw-1)/lw
    backing = head*(1-ecc)/(1+ecc)
    if head == 0:
        heading = None
    return {'head_m_min': head, 'backing_m_min': backing, 'base_m_min': base*FT,
            'heading_to_deg': heading, 'length_width_ratio': lw, 'eccentricity': ecc,
            'effective_midflame_mps': effective*FT/60,
            'effective_wind_exceeds_legacy_limit': exceeded,
            'legacy_wind_limit_applied': bool(cap and exceeded), 'uncapped_head_m_min': uncapped,
            'phi_wind': phi_w, 'phi_slope': phi_s,
            'legacy_slope_clamp_omitted':bool(reaction>0 and phi_s>.9*reaction)}


def destination(lat, lon, east, north):
    dist = math.hypot(east,north)/EARTH_M
    bearing = math.atan2(east,north)
    p, l = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p)*math.cos(dist)+math.cos(p)*math.sin(dist)*math.cos(bearing))
    l2 = l+math.atan2(math.sin(bearing)*math.sin(dist)*math.cos(p),math.cos(dist)-math.sin(p)*math.sin(p2))
    return [round(math.degrees(l2),8),round(math.degrees(p2),8)]


def frame(lat, lon, rates, minutes):
    a = (rates['head_m_min']+rates['backing_m_min'])*minutes/2
    b = a/rates['length_width_ratio']
    shift = a-rates['backing_m_min']*minutes
    heading = math.radians(rates['heading_to_deg'] or 0)
    ring = []
    if a > 0:
        for i in range(72):
            theta = 2*math.pi*i/72
            along, across = shift+a*math.cos(theta), b*math.sin(theta)
            ring.append(destination(lat,lon,along*math.sin(heading)+across*math.cos(heading),
                                    along*math.cos(heading)-across*math.sin(heading)))
        ring.append(ring[0])
    return {'minutes': minutes, 'head_distance_m': rates['head_m_min']*minutes,
            'scenario_area_ha': math.pi*a*b/10000,
            'geometry': {'type':'Polygon','coordinates':[ring]} if ring else None}


def run_scenario(req: Scenario):
    lat, lon, terrain = resolve_terrain(req)
    case_fuels = [('central',req.fuel)]
    if req.moisture_range_pct:
        case_fuels.extend((name,req.fuel.model_copy(update={'moisture_pct':value}))
                          for name,value in zip(('drier','wetter'),req.moisture_range_pct))
    times = sorted(set([*range(30,req.duration_minutes+1,30),req.duration_minutes]))
    cases = []
    for name,fuel in case_fuels:
        rate = rate_of_spread(fuel,req.wind,terrain['slope_deg'],terrain['upslope_to_deg'],cap=req.apply_legacy_wind_limit)
        cases.append({'name':name,'moisture_pct':fuel.moisture_pct,'rates':rate,
                      'frames':[frame(lat,lon,rate,t) for t in times]})
    base = cases[0]['rates']['base_m_min']
    baseline = {'head_m_min':base,'backing_m_min':base,'length_width_ratio':1,'heading_to_deg':None}
    inputs = {'request':req.model_dump(mode='json'), 'ignition':{'latitude':lat,'longitude':lon},'terrain':terrain,
              'fuel_material_provenance':{'basis':req.fuel.material_basis,
                  'source':SOURCE if req.fuel.material_basis=='behave_reference' else req.fuel.material_source,
                  'fields':list(MATERIAL_DEFAULTS), 'locally_measured_status':'not_independently_verified'},
              'model_version':VERSION,'source_commit':SOURCE_COMMIT}
    inputs['slope_factor_variant'] = 'published_rothermel_unclipped_not_legacy_behave_slope_clamp'
    digest = hashlib.sha256(json.dumps(inputs,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
    warnings = [
        'สมมติว่ามีไฟเริ่มแล้ว ไม่ได้คำนวณโอกาสเกิดไฟ',
        'ใช้เชื้อเพลิงแห้งชนิดเดียว ลมและความชันคงที่ทั้งพื้นที่และช่วงเวลา ไม่ได้จำลองความชันทุกพิกเซล',
        'กรอบรูปวงรีเป็นพื้นที่ตามเงื่อนไขจำลอง ไม่ใช่รอยไหม้จริง เขตปลอดภัย หรือคำสั่งส่งกำลัง',
        'ไม่รวมไฟเรือนยอด สะเก็ดไฟ แนวกันไฟ ถนน การดับไฟ และลมที่เปลี่ยนตามภูเขา',
        'ยังไม่สอบเทียบกับไฟจริงในเชียงใหม่ ช่วงความชื้นเป็นการลองเปลี่ยนค่า ไม่ใช่ช่วงความเชื่อมั่น',
    ]
    if any(c['rates']['effective_wind_exceeds_legacy_limit'] for c in cases):
        warnings.append('ลมมีผลเกินเกณฑ์ลมเดิมของ Rothermel ต้องตรวจความเหมาะสมของเชื้อเพลิงและผลลัพธ์ เกณฑ์นี้ไม่ใช่ใบรับรองความแม่นยำ')
    if any(c['rates']['legacy_slope_clamp_omitted'] for c in cases):
        warnings.append('กรณีนี้ผลของทางลาดสูงเมื่อเทียบกับเชื้อเพลิง รุ่นนี้ใช้สมการความชันตีพิมพ์โดยไม่ตัดตามสาขาเก่าใน Behave จึงไม่อ้างว่าตรง Behave ทุกเงื่อนไข ต้องตรวจความเหมาะสมก่อนใช้ผล')
    return {'status':'experimental_scenario','issued_at':datetime.now(timezone.utc).isoformat(),
            'model_version':VERSION,'input_sha256':digest,'inputs':inputs,'cases':cases,
            'baseline':{'name':'same_fuel_no_wind_flat','frames':[frame(lat,lon,baseline,t) for t in times]},
            'references':[SOURCE, 'https://research.fs.usda.gov/treesearch/32533',
                          'https://research.fs.usda.gov/treesearch/44352'],
            'limitations':warnings,'operational_alerts_enabled':False}


@router.post('/simulate')
def simulate(req: Scenario):
    return run_scenario(req)


class Observation(Strict):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    observed_at: datetime
    kind: Literal['firms_detection','field_arrival']
    source: str = Field(min_length=5,max_length=1000)
    position_uncertainty_m: float | None = Field(default=None,ge=0,le=2000)

    @field_validator('observed_at')
    @classmethod
    def check_time(cls,value):
        return Evidence.time_zone(value)


class Evaluation(Strict):
    scenario: Scenario
    observations: list[Observation] = Field(min_length=1,max_length=500)

    @model_validator(mode='after')
    def after_start(self):
        for row in self.observations:
            elapsed = (row.observed_at-self.scenario.start_at).total_seconds()/60
            if not 0 < elapsed <= self.scenario.duration_minutes:
                raise ValueError('จุดเทียบต้องอยู่หลังเวลาเริ่มและภายในช่วงจำลอง')
        return self


def distance_bearing(lat,lon,lat2,lon2):
    p,q = math.radians(lat),math.radians(lat2)
    dl = math.radians(lon2-lon)
    h = math.sin((q-p)/2)**2+math.cos(p)*math.cos(q)*math.sin(dl/2)**2
    distance = 2*EARTH_M*math.asin(math.sqrt(min(1,h)))
    bearing = math.degrees(math.atan2(math.sin(dl)*math.cos(q),math.cos(p)*math.sin(q)-math.sin(p)*math.cos(q)*math.cos(dl))) % 360
    return distance,bearing


@router.post('/evaluate')
def evaluate(req: Evaluation):
    result = run_scenario(req.scenario)
    return evaluate_result(req, result, basis='recomputed_current_inputs')


class SnapshotEvaluation(Strict):
    snapshot: dict
    observations: list[Observation] = Field(min_length=1, max_length=500)

    @field_validator('snapshot')
    @classmethod
    def bounded_snapshot(cls, value):
        if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 350_000:
            raise ValueError('ผลจำลองมีขนาดเกินกำหนด')
        return value


@router.post('/evaluate-snapshot')
def evaluate_snapshot(req: SnapshotEvaluation):
    """Evaluate the displayed artifact, never resolve today's DSM for an old run.

    Check its numerical consistency with the supported equation version. This
    is not a signature or proof that the supplied artifact predates the event.
    JSON round trips change number spellings, so the old input hash is an
    identifier only; it is deliberately not advertised as authentication.
    """
    result = req.snapshot
    try:
        inputs = result['inputs']
        if (result['model_version'] != VERSION or inputs['model_version'] != VERSION
                or inputs['source_commit'] != SOURCE_COMMIT
                or inputs['slope_factor_variant'] != 'published_rothermel_unclipped_not_legacy_behave_slope_clamp'):
            raise ValueError('รุ่นของผลจำลองยังไม่รองรับการเทียบนี้')
        digest = result['input_sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('รหัสผลจำลองไม่ถูกต้อง')
        if not isinstance(result['issued_at'], str):
            raise ValueError('วันเวลาผลจำลองไม่ถูกต้อง')
        Evidence.time_zone(datetime.fromisoformat(result['issued_at'].replace('Z', '+00:00')))
        scenario = Scenario.model_validate(inputs['request'])
        t, origin = inputs['terrain'], inputs['ignition']
        lat, lon = float(origin['latitude']), float(origin['longitude'])
        slope, upslope = float(t['slope_deg']), float(t['upslope_to_deg'])
        if not (17 <= lat <= 21 and 98 <= lon <= 100 and 0 <= slope <= 60 and 0 <= upslope < 360):
            raise ValueError('พิกัดหรือทางลาดในผลเดิมไม่ถูกต้อง')
        if t['mode'] != scenario.terrain.mode:
            raise ValueError('ชนิดภูมิประเทศในผลเดิมไม่ตรงข้อมูลนำเข้า')
        if t['mode'] == 'manual' and (lat, lon, slope, upslope) != (
                scenario.latitude, scenario.longitude, scenario.terrain.slope_deg, scenario.terrain.upslope_to_deg):
            raise ValueError('ภูมิประเทศที่ระบุเองไม่ตรงข้อมูลนำเข้า')
        central = result['cases'][0]
        if central['name'] != 'central':
            raise ValueError('ไม่พบผลกรณีหลัก')
        expected = rate_of_spread(scenario.fuel, scenario.wind, slope, upslope, cap=scenario.apply_legacy_wind_limit)
        for key in ('head_m_min', 'base_m_min', 'eccentricity', 'heading_to_deg'):
            actual, target = central['rates'][key], expected[key]
            if target is None:
                valid = actual is None
            else:
                valid = type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, target, rel_tol=1e-10, abs_tol=1e-10)
            if not valid:
                raise ValueError('ค่าลามในผลเดิมไม่สอดคล้องกับข้อมูลและสมการรุ่นนี้')
        evaluation = Evaluation(scenario=scenario, observations=req.observations)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        raise HTTPException(422, 'อ่านผลเดิมเพื่อเทียบไม่ได้: ' + str(exc)) from None
    return evaluate_result(evaluation, result, basis='submitted_snapshot_equations_checked')


def evaluate_result(req: Evaluation, result: dict, *, basis: str):
    origin = result['inputs']['ignition']
    rate = result['cases'][0]['rates']
    unique = {(o.latitude,o.longitude,o.observed_at.astimezone(timezone.utc),o.kind):o for o in req.observations}
    rows, arrival_errors, baseline_errors = [], [], []
    for o in unique.values():
        elapsed = (o.observed_at-req.scenario.start_at).total_seconds()/60
        distance, bearing = distance_bearing(origin['latitude'],origin['longitude'],o.latitude,o.longitude)
        ecc = rate['eccentricity']
        theta = math.radians(bearing-(rate['heading_to_deg'] or 0))
        directional = rate['head_m_min']*(1-ecc)/(1-ecc*math.cos(theta))
        arrival = distance/directional if directional>0 else 0.0 if distance==0 else None
        base_arrival = distance/rate['base_m_min'] if rate['base_m_min']>0 else 0.0 if distance==0 else None
        if o.kind == 'field_arrival' and arrival is not None:
            arrival_errors.append(abs(arrival-elapsed))
        if o.kind == 'field_arrival' and base_arrival is not None:
            baseline_errors.append(abs(base_arrival-elapsed))
        rows.append({'kind':o.kind,'source':o.source,'observed_at':o.observed_at.isoformat(),
                     'latitude':o.latitude,'longitude':o.longitude,
                     'elapsed_minutes':elapsed,'nominal_point_inside':bool(arrival is not None and arrival<=elapsed),
                     'baseline_point_inside':bool(base_arrival is not None and base_arrival<=elapsed),
                     'model_arrival_minutes':arrival,'baseline_arrival_minutes':base_arrival,
                     'model_arrival_within_horizon':arrival is not None and arrival<=req.scenario.duration_minutes,
                     'baseline_arrival_within_horizon':base_arrival is not None and base_arrival<=req.scenario.duration_minutes,
                     'arrival_error_minutes':arrival-elapsed if o.kind=='field_arrival' and arrival is not None else None,
                     'position_uncertainty_m':o.position_uncertainty_m})
    return {'status':'retrospective_diagnostic_not_blind_validation', 'input_sha256':result['input_sha256'],
            'evaluation_version':'cme-point-diagnostic-v2','evaluation_basis':basis,
            'evaluated_at':datetime.now(timezone.utc).isoformat(),'scenario_issued_at':result['issued_at'],
            'model_version':result['model_version'],
            'unique_observation_count':len(rows),'duplicate_count':len(req.observations)-len(rows),
            'nominal_point_coverage_percent':100*sum(r['nominal_point_inside'] for r in rows)/len(rows),
            'baseline_point_coverage_percent':100*sum(r['baseline_point_inside'] for r in rows)/len(rows),
            'point_coverage_by_kind':{kind:{'count':len(group),
                'nominal_percent':100*sum(r['nominal_point_inside'] for r in group)/len(group) if group else None,
                'baseline_percent':100*sum(r['baseline_point_inside'] for r in group)/len(group) if group else None}
                for kind in ('firms_detection','field_arrival') for group in [[r for r in rows if r['kind']==kind]]},
            'field_arrival_observation_count':sum(o.kind=='field_arrival' for o in unique.values()),
            'field_arrival_sample_count':len(arrival_errors),
            'field_arrival_no_model_arrival_count':sum(r['kind']=='field_arrival' and r['model_arrival_minutes'] is None for r in rows),
            'mean_absolute_arrival_error_minutes':sum(arrival_errors)/len(arrival_errors) if arrival_errors else None,
            'baseline_mean_absolute_arrival_error_minutes':sum(baseline_errors)/len(baseline_errors) if baseline_errors else None,
            'median_absolute_arrival_error_minutes':median(arrival_errors) if arrival_errors else None,
            'baseline_median_absolute_arrival_error_minutes':median(baseline_errors) if baseline_errors else None,
            'observations':rows,'limitations':[
                'ผลเดิมตรวจความสอดคล้องของสมการได้ แต่รหัสข้อมูลและเวลาที่ผู้ใช้ส่งมาไม่ใช่ลายเซ็นรับรองหรือหลักฐานว่าบันทึกก่อนรู้เหตุ',
                'เวลาไฟมาถึงที่เกินช่วงจำลองเป็นการต่อสมการภายใต้เงื่อนไขคงที่ ไม่ใช่ผลพยากรณ์ภายในช่วงนั้น และยังรวมในค่าคลาดเคลื่อนเวลาที่แสดง',
                'เป็นการเทียบย้อนหลัง ไม่ใช่การพิสูจน์ว่าพยากรณ์ล่วงหน้าได้แม่น ต้องแช่แข็งข้อมูลและบันทึกผลก่อนรู้เหตุจริง',
                'FIRMS เป็นจุดตรวจพบความร้อน เวลา overpass ไม่ใช่เวลาไฟมาถึง และไม่มีจุดไม่ได้แปลว่าไม่มีไฟ',
                'สัดส่วนจุดที่อยู่ในวงรีไม่ใช่ accuracy/precision และไม่วัดพื้นที่เกินจริง ไม่มีข้อมูลกรอบไฟอิสระสำหรับ IoU',
                'ใช้ตำแหน่งกลางจุดตามรายงาน ยังไม่ชดเชยความคลาดเคลื่อนตำแหน่ง; ค่าคลาดเคลื่อนเวลาใช้เฉพาะเวลาที่ผู้ตรวจระบุว่าเห็นไฟมาถึงจริง',
            ]}
