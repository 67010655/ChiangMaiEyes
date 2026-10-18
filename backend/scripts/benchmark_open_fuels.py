"""Pinned Pyretechnics surface rates + weather-conditioned moisture pilot.

This reuses the previously inspected 66 cases. It is an ablation/pilot, not a
new independent fire-perimeter validation or a production parameter search.
"""
import ast, hashlib, json, logging, math, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'output/reference-tools/pyretechnics')]
from pyretechnics import fuel_models as fm, surface_fire as sf
from app import live_spread as engine
from app.grid_spread import landcover_dataset
from app.forecast_terrain import at as terrain_at
from optimize_spread import candidate_inputs

OUT=ROOT/'output/open-fuels-pilot-20261017';OUT.mkdir(parents=True,exist_ok=True)
SOURCE=ROOT/'output/spread-optimization-20261017/quality-filtered'
project=Transformer.from_crs(4326,32647,always_xy=True).transform
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,b):p.write_text(json.dumps(b,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def equilibria(temperature,rh):
    """Van Wagner/Viney equations as implemented by WRF-SFIRE (mass fraction)."""
    h=float(rh);t=float(temperature)
    d=.942*h**.679+.00004994*math.exp(.1*h)+.18*(21.1-t)*(1-math.exp(-.115*h))
    w=.618*h**.753+.00004540*math.exp(.1*h)+.18*(21.1-t)*(1-math.exp(-.115*h))
    return max(d,w,0)/100,max(min(d,w),0)/100

def advance(state,d,w,rain):
    """Scalar counterpart of wrfxpy FuelMoistureModel.advance_model, dt=1h."""
    out=[]
    for m,lag in zip(state,(1,10,100)):
        if rain>.05:target=2.5;change=(1-math.exp(-(rain-.05)/8))/14
        else:target=d if m>d else w if m<w else m;change=1/lag
        factor=1-math.exp(-change) if change>.01 else change*(1-.5*change)
        out.append(m+(target-m)*factor)
    return tuple(out)

def check_moisture_reference():
    """Execute original class in isolation; do not import its unrelated WRF IO."""
    path=ROOT/'output/reference-tools/wrfxpy/fuel_moisture_model.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='FuelMoistureModel')
    namespace={'np':np,'logging':logging,'inq':lambda v:str(np.shape(v))}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(path),'exec'),namespace)
    model=namespace['FuelMoistureModel'](np.array([[[.08,.10,.12]]]),P0=np.zeros((5,5)))
    state=(.08,.10,.12);difference=0.
    for t,rh,rain in [(35,20,0),(20,80,0),(25,90,2),(30,40,0)]*12:
        d,w=equilibria(t,rh);state=advance(state,d,w,rain)
        model.advance_model(np.array([[d]]),np.array([[w]]),np.array([[rain]]),3600,np.zeros((5,5)))
        difference=max(difference,float(np.max(np.abs(np.array(state)-model.get_state()[0,0,:3]))))
    assert difference<1e-12
    return {'steps':48,'max_absolute_moisture_difference':difference,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def moisture_series():
    weather=read(ROOT/'output/priority-forecast-20261017/gfs-weather-2026.json')['hourly']
    result={};state=(.08,.10,.12);contiguous=0
    for i,when in enumerate(weather['time']):
        vals=[weather[k+'_previous_day1'][i] for k in ('temperature_2m','relative_humidity_2m','precipitation')]
        if any(v is None for v in vals):contiguous=0;continue
        d,w=equilibria(*vals[:2]);state=advance(state,d,w,vals[2]);contiguous+=1
        if contiguous>=168:result[engine.stamp(when+'+00:00')]=state
    return result

def fuel_at(point):
    meta,classes=landcover_dataset();col=math.floor((point['longitude']-meta['west'])/meta['step_degrees']);row=math.floor((meta['north']-point['latitude'])/meta['step_degrees'])
    cover=classes[row*meta['width']+col]
    # Hypotheses, not a measured Thai fuel map. Unknown/wet classes keep FM1.
    return {10:9,20:5,30:1,40:1}.get(cover,1),cover

def rates(point,step,moisture,fuel_number):
    terrain=terrain_at(point['latitude'],point['longitude'])
    model=fm.moisturize(fm.get_fuel_model(fuel_number),(*moisture,0.,.5,.8))
    base=sf.calc_surface_fire_behavior_no_wind_no_slope(model)
    peak=sf.calc_surface_fire_behavior_max(base,step['wind_10m_mps']*.2*60,step['wind_from_deg'],
        math.tan(math.radians(terrain['slope_deg'])),(terrain['upslope_to_deg']+180)%360)
    x,y,_=peak.max_spread_direction;ecc=peak.eccentricity
    return {'head_m_min':peak.max_spread_rate,'backing_m_min':peak.max_spread_rate*(1-ecc)/(1+ecc),
            'length_width_ratio':peak.length_to_width_ratio,'heading_to_deg':math.degrees(math.atan2(x,y))%360}

def evaluate(case,series):
    current=[{'point':p,'steps':steps} for p,steps in candidate_inputs(case,{'moisture':8,'wind_factor':.2,'slope_factor':1})]
    start=engine.stamp(case['as_of']);inputs={'current':current};fuel_counts={}
    for name,dynamic,cover_fuel in [('pyre_fm1_fixed',False,False),('pyre_fm1_dynamic',True,False),('pyre_cover_fixed',False,True),('pyre_cover_dynamic',True,True)]:
        candidate=[]
        for item in current:
            point=item['point'];fuel,cover=fuel_at(point);fuel_counts[str(cover)]=fuel
            steps=[]
            for step in item['steps']:
                at=(start+timedelta(minutes=step['from_minute'])).replace(minute=0,second=0,microsecond=0)
                state=series.get(at)
                if state is None:return None
                m=state if dynamic else (.08,.08,.08)
                steps.append({**step,'rates':rates(point,step,m,fuel if cover_fuel else 1)})
            candidate.append({'point':point,'steps':steps})
        inputs[name]=candidate
    domain=Point(*project(case['centre']['longitude'],case['centre']['latitude'])).buffer(5000)
    origins=unary_union([Point(*project(i['point']['longitude'],i['point']['latitude'])) for i in current])
    rows={n:{'covered':0,'covered375':0,'equal_area_covered375':0,'areas_km2':[]} for n in inputs}
    bytime={}
    for p in case['later']:
        minutes=(engine.stamp(p['detected_at'])-start).total_seconds()/60
        bytime.setdefault(minutes,[]).append(Point(*project(p['longitude'],p['latitude'])))
    for minute,observed in bytime.items():
        for name,items in inputs.items():
            raw=unary_union([transform(project,shape(engine.footprint(i['point'],i['steps'],minute))) for i in items]).intersection(domain)
            expanded=raw.buffer(375).intersection(domain);low,high=0.,10000.
            for _ in range(15):
                mid=(low+high)/2
                if origins.buffer(mid).intersection(domain).area<expanded.area:low=mid
                else:high=mid
            equal=origins.buffer((low+high)/2).intersection(domain);row=rows[name]
            row['covered']+=sum(raw.covers(p) for p in observed);row['covered375']+=sum(expanded.covers(p) for p in observed)
            row['equal_area_covered375']+=sum(equal.covers(p) for p in observed);row['areas_km2'].append(expanded.area/1e6)
    for row in rows.values():row['mean_expanded_area_km2']=float(np.mean(row.pop('areas_km2')))
    return {'id':case['id'],'points':len(case['later']),'models':rows,'cover_to_fuel':fuel_counts}

def aggregate(rows):
    return {'cases':len(rows),'points':sum(r['points'] for r in rows),'models':{name:{
        **{k:sum(r['models'][name][k] for r in rows) for k in ('covered','covered375','equal_area_covered375')},
        'mean_expanded_area_km2':float(np.mean([r['models'][name]['mean_expanded_area_km2'] for r in rows]))} for name in rows[0]['models']}}

def main():
    protocol={'pinned_pyretechnics':read(ROOT/'output/reference-tools/pyretechnics/SOURCE.json'),
      'moisture_reference':'https://github.com/openwfm/wrfxpy/blob/master/src/fmda/fuel_moisture_model.py',
      'equilibria_reference':'https://github.com/openwfm/wrf-fire/blob/master/wrfv2_fire/phys/module_fr_sfire_phys.F',
      'reference_parity':check_moisture_reference(),'conditioning_hours':168,'weather':'GFS previous-day1 stitched forecasts, single province point18.79/98.99; no local moisture or solar correction',
      'candidates':'Four predeclared ablations, fixed 0.2 wind factor, no tuning or winner selection.',
      'limits':['Reuses inspected66cases;02:00 issue lacks3h latency and may include same-pass later points. Pilot only.',
        'Cover10->FM9,20->FM5,30/40->FM1 are uncalibrated fuel hypotheses; live moisture fixed50/80percent.',
        'Uses Pyretechnics multi-class surface rates and existing wavelet propagation, not its full level-set/crown/spotting solver.',
        'Weather-derived moisture is a WRFx time-lag estimate, not the Nelson model or a direct measurement.']}
    write(OUT/'protocol.json',protocol);series=moisture_series();rows=[];skipped=[]
    for case in read(SOURCE/'cases.json'):
        if not case['later']:continue
        path=OUT/(case['id']+'.json');row=read(path) if path.exists() else evaluate(case,series)
        if row is None:skipped.append(case['id']);continue
        write(path,row);rows.append(row);print(case['id'],{n:r['covered375'] for n,r in row['models'].items()},flush=True)
    report={'protocol':protocol,'skipped':skipped,'development':aggregate([r for r in rows if r['id']<='2026-03-22']),
      'test':aggregate([r for r in rows if r['id']>'2026-03-22']),'production_changed':False}
    write(OUT/'summary.json',report);print('RESULT',json.dumps({k:v for k,v in report.items() if k!='protocol'}),flush=True)

if __name__=='__main__':main()
