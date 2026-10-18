"""Experimental arrival-time propagation over observed terrain/land-cover grids.

Fuel remains an explicit reference assumption. Time-dependent graph travel
integrates the hourly wind intervals; unavailable cells never become flat land.
"""
from __future__ import annotations
import bisect,gzip,hashlib,heapq,json,math,time
from functools import lru_cache
from pathlib import Path
from threading import Lock
from fastapi import APIRouter,BackgroundTasks,Depends
from app.config import Settings,get_settings
from app.forecast_terrain import dataset as terrain_dataset
from app.live_spread import FUEL,WIND_FACTOR,stamp,live
from app.spread_scenario import Fuel,Wind,rate_of_spread

VERSION='cme-grid-hourly-terrain-landcover-v1'
router=APIRouter(prefix='/api/spread',tags=['Experimental grid spread'])
_lock=Lock();_cache=None
NEIGHBOURS=tuple((dr,dc) for dr in (-1,0,1) for dc in (-1,0,1) if dr or dc)

@lru_cache(maxsize=1)
def landcover_dataset():
    root=Path(__file__).parent/'data';meta=json.loads((root/'spread-landcover.json').read_text(encoding='utf8'))
    data=gzip.decompress((root/'spread-landcover.bin.gz').read_bytes());terrain,_=terrain_dataset()
    if len(data)!=meta['height']*meta['width'] or hashlib.sha256(data).hexdigest()!=meta['sha256']:
        raise ValueError('Land-cover checksum mismatch')
    if any(meta[k]!=terrain[k] for k in ('west','north','step_degrees','width','height')):raise ValueError('Raster grids do not align')
    return meta,data

def rectangles(cells,meta):
    """Exact run-length rectangles, no convex hull or extra smoothing."""
    rows={}
    for row,col in cells:rows.setdefault(row,[]).append(col)
    result=[];active={};previous=None
    for row,cols in sorted(rows.items()):
        if previous is None or row!=previous+1:
            result.extend(active.values());active={}
        runs=[];first=last=None
        for col in sorted(cols):
            if last is None:first=last=col
            elif col==last+1:last=col
            else:runs.append((first,last));first=last=col
        if last is not None:runs.append((first,last))
        next_active={}
        for run in runs:
            next_active[run]=(*active[run][:2],row,run[1]) if run in active else (row,run[0],row,run[1])
        result.extend(v for k,v in active.items() if k not in next_active);active=next_active;previous=row
    result.extend(active.values());features=[];step=meta['step_degrees']
    for r0,c0,r1,c1 in result:
        west=meta['west']+c0*step;east=meta['west']+(c1+1)*step
        north=meta['north']-r0*step;south=meta['north']-(r1+1)*step
        features.append({'type':'Feature','properties':{},'geometry':{'type':'Polygon','coordinates':[[[west,north],[east,north],[east,south],[west,south],[west,north]]]}})
    return {'type':'FeatureCollection','features':features}

def travel(arrival,distance,boundaries,speeds,limit):
    """FIFO traversal: integrate remaining edge distance across wind changes."""
    cursor=arrival;remaining=distance
    while cursor<limit:
        index=bisect.bisect_right(boundaries,cursor)
        if index>=len(speeds):return math.inf
        stop=min(boundaries[index],limit);speed=speeds[index]
        if speed>0:
            capacity=(stop-cursor)*speed
            if capacity>=remaining:return cursor+remaining/speed
            remaining-=capacity
        cursor=stop
    return math.inf

def run(inputs,*,as_of,max_minutes=360,max_cells=30000,use_landcover=True):
    meta,z=terrain_dataset();landmeta,classes=landcover_dataset();w=meta['width'];h=meta['height'];step=meta['step_degrees']
    blocked=set(landmeta['blocked_classes']);terrain_cache={};nearest_cache={};rate_cache={};excluded=[];seeds=[]
    def cell(point):return (math.floor((meta['north']-point['latitude'])/step),math.floor((point['longitude']-meta['west'])/step))
    def allowed(row,col):
        if not (1<=row<h-1 and 1<=col<w-1):return False
        index=row*w+col
        return z[index]!=meta['nodata'] and (not use_landcover or classes[index] not in blocked)
    def terrain(row,col):
        key=row,col
        if key not in terrain_cache:
            patch=[z[(row+dr)*w+col+dc] for dr in (-1,0,1) for dc in (-1,0,1)]
            if meta['nodata'] in patch:terrain_cache[key]=None
            else:
                lat=meta['north']-(row+.5)*step;dy=math.radians(step)*6371008.8;dx=dy*math.cos(math.radians(lat))
                a,b,c,d,e,f,g,h_,i=patch;east=(c+2*f+i-a-2*d-g)/(8*dx);north=(a+2*b+c-g-2*h_-i)/(8*dy)
                terrain_cache[key]=(math.degrees(math.atan(math.hypot(east,north))),math.degrees(math.atan2(east,north))%360,dx,dy)
        return terrain_cache[key]
    for n,item in enumerate(inputs):
        row,col=cell(item['point'])
        if not allowed(row,col):excluded.append({'origin_index':n,'reason':'outside_or_missing_or_landcover_blocked','landcover_class':classes[row*w+col] if 0<=row<h and 0<=col<w else None});continue
        if terrain(row,col) is None:excluded.append({'origin_index':n,'reason':'missing_terrain_neighbourhood'});continue
        seeds.append((row,col,n))
    evidence={'basis':'reference','source':'USFS FM1 reference; unmeasured local fuel','observed_at':as_of}
    fuel=Fuel(**FUEL,evidence=evidence)
    def rates(row,col):
        key=row,col
        if key not in nearest_cache:
            nearest_cache[key]=min(seeds,key=lambda s:(s[0]-row)**2+(s[1]-col)**2)[2]
        origin=nearest_cache[key];key2=(row,col,origin)
        if key2 not in rate_cache:
            slope,heading,dx,dy=terrain(row,col)
            if slope>60:return None
            values=[]
            for interval in inputs[origin]['steps']:
                wind=Wind(midflame_mps=interval['wind_10m_mps']*WIND_FACTOR,from_deg=interval['wind_from_deg']%360,evidence=evidence)
                values.append(rate_of_spread(fuel,wind,slope,heading))
            rate_cache[key2]=values
        return rate_cache[key2]
    arrival={(r,c):0. for r,c,_ in seeds};queue=[(0.,r,c) for r,c in arrival];heapq.heapify(queue);processed=0;truncated=False
    while queue:
        elapsed,row,col=heapq.heappop(queue)
        if elapsed!=arrival[(row,col)] or elapsed>max_minutes:continue
        if processed>=max_cells:truncated=True;break
        processed+=1;local=terrain(row,col)
        if local is None:continue
        values=rates(row,col)
        if values is None:continue
        origin=nearest_cache[(row,col)];boundaries=[s['to_minute'] for s in inputs[origin]['steps']]
        for dr,dc in NEIGHBOURS:
            nr,nc=row+dr,col+dc
            if not allowed(nr,nc) or terrain(nr,nc) is None:continue
            if dr and dc and (not allowed(row+dr,col) or not allowed(row,col+dc)):continue
            east=dc*local[2];north=-dr*local[3];angle=math.degrees(math.atan2(east,north))%360
            speeds=[]
            for rate in values:
                eccentricity=rate['eccentricity'];delta=math.radians(angle-(rate['heading_to_deg'] or 0))
                speeds.append(rate['head_m_min']*(1-eccentricity)/(1-eccentricity*math.cos(delta)))
            reached=travel(elapsed,math.hypot(east,north),boundaries,speeds,max_minutes)
            if reached<arrival.get((nr,nc),math.inf):arrival[(nr,nc)]=reached;heapq.heappush(queue,(reached,nr,nc))
    return {'arrival':arrival,'excluded':excluded,'processed_cells':processed,'truncated':truncated,
            'used_origins':len(seeds),'landcover_enabled':use_landcover,'grid':meta,'landcover':landmeta}

def response(base,result):
    from datetime import timedelta
    start=stamp(base['as_of']);frames=[]
    for hours in (3,6):
        cells=[cell for cell,minutes in result['arrival'].items() if minutes<=hours*60]
        frames.append({'hours':hours,'valid_at':(start+timedelta(hours=hours)).isoformat(),'cells':len(cells),'geometry':rectangles(cells,result['grid'])})
    return {'model_version':VERSION,'as_of':base['as_of'],'issued_at':base['issued_at'],'status':'no_usable_origins' if not result['used_origins'] else 'partial' if result['truncated'] or result['excluded'] else 'experimental',
            'source_mode':base['source_mode'],'source_retrieved_at':base['source_retrieved_at'],'used_origins':result['used_origins'],
            'excluded':result['excluded'],'processed_cells':result['processed_cells'],'truncated':result['truncated'],
            'inputs':base['inputs'],'frames':frames,'terrain_metadata':result['grid'],'landcover_metadata':result['landcover'],
            'fuel_assumption':FUEL,'wind_factor_assumption':WIND_FACTOR,'overall_accuracy_percent':None,
            'notes':['รุ่นทดลอง: ทางลาดเปลี่ยนทุกช่องประมาณ 110 เมตร ลมเปลี่ยนรายชั่วโมง ใช้เวลาเดินทางบนกราฟ 8 ทิศ',
                     'ใช้ WorldCover ปี 2021 กั้นช่องน้ำ สิ่งปลูกสร้าง พื้นโล่ง/หิมะและข้อมูลขาด ไม่เห็นแนวถนนหรือการเปลี่ยนที่ดินปี 2026 ครบ',
                     'ชนิดสิ่งปกคลุมดินไม่ใช่มวลหรือความชื้นเชื้อเพลิง ยังใช้ FM1 ความชื้น 8% และลม ×0.2 เป็นเงื่อนไขทดลอง',
                     'ตำแหน่งเริ่มถูกแทนด้วยช่องกริด อาจคลาดถึงประมาณ 80 เมตรและการเดิน 8 ทิศมีความคลาดเชิงตัวเลข',
                     'ยังไม่ยืนยันว่าจุดดาวเทียมทุกจุดยังไหม้ และไม่รวมสะเก็ดไฟหรือการดับไฟ',
                     'รอยเผาอ้างอิงรายสัปดาห์ใช้ตรวจความสอดคล้องเชิงพื้นที่ ไม่ยืนยันเวลาไฟมาถึงระดับ 6 ชั่วโมง']}

@router.get('/grid')
def current_grid(background_tasks:BackgroundTasks,settings:Settings=Depends(get_settings)):
    global _cache
    with _lock:
        base=live(settings)
        if _cache and _cache[0]==base['as_of']:result=_cache[1]
        else:
            result=response(base,run(base['inputs'],as_of=base['as_of']));_cache=(base['as_of'],result)
    from app.forecast_archive import collect_background
    background_tasks.add_task(collect_background,settings,result,'grid')
    return result
