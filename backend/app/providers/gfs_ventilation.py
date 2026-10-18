"""NOAA GFS 0.25-degree PBL fields, decoded from the publisher's GRIB2.

Native VRATE is retained; 10-m wind is never substituted for PBL wind.
No risk category, fire perimeter, or outdoor-safety decision is derived here.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from threading import Lock
from time import monotonic
import hashlib
import base64
import logging
import math
import re
import httpx
from app.providers.hotspot_provider import province_bbox

CATALOG='https://nomads.ncep.noaa.gov/gribfilter.php?ds=gfs_0p25'
FILTER='https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl'
FILE_LIST='https://nomads.ncep.noaa.gov/find_subdirs_files.php'
UNIT_TABLE='https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-3.shtml'
INVENTORY='https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f000.shtml'
_lock=Lock()
_cache:dict[int,tuple[float,dict]]={}
logger=logging.getLogger(__name__)

def model_bbox()->str:
    west,south,east,north=map(float,province_bbox().split(','))
    # Model-cell centres must include the cells at the province edges too.
    # FIRMS' point-detection bbox cannot simply be reused without padding.
    values=(math.floor(west*4)/4,math.floor(south*4)/4,math.ceil(east*4)/4,math.ceil(north*4)/4)
    return ','.join(f'{v:.4f}' for v in values)

class CatalogParser(HTMLParser):
    def __init__(self):
        super().__init__();self.directory=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='input' and a.get('name')=='dir':self.directory=a.get('value')

def catalog_cycle(html:str,now:datetime)->tuple[str,datetime]:
    parser=CatalogParser();parser.feed(html)
    match=re.fullmatch(r'/gfs\.(\d{8})/(00|06|12|18)/atmos',parser.directory or '')
    if not match:raise ValueError('NOAA cycle metadata unavailable')
    run=datetime.strptime(match[1]+match[2],'%Y%m%d%H').replace(tzinfo=timezone.utc)
    if not timedelta(0)<=now-run<=timedelta(hours=24):raise ValueError('NOAA cycle is old or future')
    return parser.directory,run

def decode_subset(data:bytes,run:datetime,step:int,bbox:str)->dict:
    import eccodes
    if not data.startswith(b'GRIB') or len(data)>2_000_000:raise ValueError('Invalid GRIB subset')
    west,south,east,north=map(float,bbox.split(','))
    expected_time=run+timedelta(hours=step)
    fields={};metadata=[];position=0
    while position<len(data):
        if len(metadata)>=4 or data[position:position+4]!=b'GRIB':raise ValueError('Unexpected GRIB messages')
        size=int.from_bytes(data[position+8:position+16],'big')
        if size<20 or position+size>len(data) or data[position+size-4:position+size]!=b'7777':raise ValueError('Truncated GRIB')
        msg=eccodes.codes_new_from_message(data[position:position+size]);position+=size
        try:
            m={key:eccodes.codes_get(msg,key) for key in ['centre','subCentre','edition','discipline','parameterCategory','parameterNumber','typeOfLevel','units','dataDate','dataTime','validityDate','validityTime','gridType','iDirectionIncrementInDegrees','jDirectionIncrementInDegrees']}
            if m['centre']!='kwbc' or m['edition']!=2 or m['discipline']!=0 or m['subCentre']!=0:raise ValueError('Unexpected GRIB origin')
            if m['gridType']!='regular_ll' or any(abs(m[k]-.25)>1e-6 for k in ['iDirectionIncrementInDegrees','jDirectionIncrementInDegrees']):raise ValueError('Unexpected GFS grid')
            model_time=datetime.strptime(str(m['dataDate'])+str(m['dataTime']).zfill(4),'%Y%m%d%H%M').replace(tzinfo=timezone.utc)
            valid_time=datetime.strptime(str(m['validityDate'])+str(m['validityTime']).zfill(4),'%Y%m%d%H%M').replace(tzinfo=timezone.utc)
            if model_time!=run or valid_time!=expected_time:raise ValueError('GRIB run/valid time mismatch')
            code=(m['parameterCategory'],m['parameterNumber'],m['typeOfLevel'])
            mapping={(2,2,'planetaryBoundaryLayer'):('u_pbl_m_s','m s**-1'),
                     (2,3,'planetaryBoundaryLayer'):('v_pbl_m_s','m s**-1'),
                     (2,224,'planetaryBoundaryLayer'):('ventilation_rate_m2_s','m**2 s**-1'),
                     (3,196,'surface'):('pbl_height_m','m'),(3,18,'surface'):('pbl_height_m','m')}
            if code not in mapping:raise ValueError('Unexpected GFS parameter/level')
            name,unit=mapping[code]
            # NCEP's local HPBL 0.3.196 is defined in metres by its published
            # table, even when ecCodes cannot name that local parameter.
            if m['units']!=unit and not (code==(3,196,'surface') and m['units']=='unknown'):raise ValueError('Unexpected GRIB unit')
            if name in fields:raise ValueError('Duplicate GFS field')
            missing=eccodes.codes_get(msg,'missingValue');values={}
            for row in eccodes.codes_grib_get_data(msg):
                lat,lon,value=float(row['lat']),float(row['lon']),float(row['value'])
                if not (west-1e-6<=lon<=east+1e-6 and south-1e-6<=lat<=north+1e-6):raise ValueError('Grid outside requested bbox')
                point=(round(lat,6),round(lon,6))
                if point in values:raise ValueError('Duplicate GFS coordinate')
                values[point]=value if math.isfinite(value) and value!=missing and (name not in ('pbl_height_m','ventilation_rate_m2_s') or value>=0) else None
            fields[name]=values;metadata.append({**m,'field':name,'normalized_unit':unit,'unit_source':UNIT_TABLE if name=='pbl_height_m' else INVENTORY})
        finally:eccodes.codes_release(msg)
    if len(fields)!=4 or not fields:raise ValueError('Incomplete GFS product')
    points=set(next(iter(fields.values())))
    if not points or any(set(v)!=points for v in fields.values()):raise ValueError('GFS field grids are not aligned')
    cells=[]
    for lat,lon in sorted(points):
        cell={'latitude':lat,'longitude':lon,**{k:v[(lat,lon)] for k,v in fields.items()}}
        u,v=cell['u_pbl_m_s'],cell['v_pbl_m_s']
        cell['wind_pbl_m_s']=math.hypot(u,v) if u is not None and v is not None else None
        to=(math.degrees(math.atan2(u,v))+360)%360 if cell['wind_pbl_m_s'] else None
        cell.update(wind_to_deg=to,wind_from_deg=(to+180)%360 if to is not None else None)
        cells.append(cell)
    reference=min(cells,key=lambda c:(c['latitude']-18.79)**2+(c['longitude']-98.98)**2)
    return {'cells':cells,'reference_cell':reference,'run_at':run.isoformat(),'valid_at':expected_time.isoformat(),
            'forecast_hour':step,'bbox':bbox,'grid_degrees':.25,'field_metadata':metadata,
            'missing_cells':sum(any(c[k] is None for k in fields) for c in cells)}

def fetch_product(lead_hours:int=0,*,now:datetime|None=None,get=httpx.get)->dict:
    if lead_hours not in (0,24,48):raise ValueError('Unsupported forecast lead')
    now=now or datetime.now(timezone.utc)
    catalog=get(CATALOG,timeout=8);catalog.raise_for_status()
    if len(catalog.content)>1_000_000:raise ValueError('Catalog too large')
    newest_directory,newest_run=catalog_cycle(catalog.text,now)
    cycles=re.findall(r"click_subdir\(1,\s*'(00|06|12|18)'",catalog.text)
    candidates=[newest_run]+[newest_run.replace(hour=int(c)) for c in cycles if int(c)<newest_run.hour]
    directory=None
    for run in sorted(set(candidates),reverse=True)[:2]:
        listing=get(FILE_LIST,params={'ds':'gfs_0p25','path':f'/gfs.{run:%Y%m%d}',
                       'subdir_num':'1','subdir_name':f'{run:%H}'},timeout=6)
        listing.raise_for_status()
        if len(listing.content)>1_000_000:raise ValueError('File list too large')
        available=set(re.findall(rf'gfs\.t{run:%H}z\.pgrb2\.0p25\.f(\d{{3}})',listing.text))
        step=int((now-run).total_seconds()//3600)+lead_hours
        if f'{step:03d}' in available:
            directory=f'/gfs.{run:%Y%m%d}/{run:%H}/atmos';break
    if directory is None:raise ValueError('Requested forecast file has not been published')
    bbox=model_bbox();west,south,east,north=bbox.split(',')
    params={'file':f'gfs.t{run:%H}z.pgrb2.0p25.f{step:03d}','dir':directory,
      'var_HPBL':'on','var_UGRD':'on','var_VGRD':'on','var_VRATE':'on',
      'lev_surface':'on','lev_planetary_boundary_layer':'on','subregion':'',
      'leftlon':west,'rightlon':east,'bottomlat':south,'toplat':north}
    response=get(FILTER,params=params,timeout=20);response.raise_for_status()
    decoded=decode_subset(response.content,run,step,bbox)
    return {**decoded,'status':'partial' if decoded['missing_cells'] else 'available','measurement_kind':'model',
      'publisher':'NOAA NCEP','product':'GFS 0.25° PBL','lead_hours':lead_hours,
      'retrieved_at':datetime.now(timezone.utc).isoformat(),'source_url':str(response.url),
      'latest_directory':newest_directory,'cycle_fallback':run!=newest_run,'province_bbox':province_bbox(),
      'sha256':hashlib.sha256(response.content).hexdigest(),'source_documentation':[INVENTORY,UNIT_TABLE],
      '_archive_grib_base64':base64.b64encode(response.content).decode('ascii'),
      'notes':['ลมนี้เป็นลมในชั้น PBL คนละระดับกับลมสถานีและลม 10 เมตร',
               'VRATE เป็นค่าจาก NOAA โดยตรง หน่วย m²/s ไม่แทนด้วย PBL × ลม 10 เมตร',
               'ค่ากริดระดับภูมิภาค ไม่ใช่ค่าที่ตรวจวัดในป่าชุมชน และยังไม่มีการสอบเทียบภาคสนามของระบบนี้']}

def ventilation(lead_hours:int=0)->dict:
    # Shared in-process cache and CDN cache protect the publisher. A missing
    # response is cached briefly, never filled with zero or fabricated data.
    with _lock:
        found=_cache.get(lead_hours)
        if found and found[0]>monotonic():return found[1]
        try:result=fetch_product(lead_hours)
        except Exception as error:
            logger.warning('NOAA GFS PBL unavailable (%s): %s',type(error).__name__,str(error)[:180])
            result={'status':'unavailable','measurement_kind':'model','publisher':'NOAA NCEP','lead_hours':lead_hours,
                    'cells':[],'reference_cell':None,'notes':['ยังไม่ได้รับชุด GFS PBL ที่ตรวจเวลา หน่วย และกริดครบ ไม่คำนวณแทนจากลมสถานี']}
        _cache[lead_hours]=(monotonic()+(600 if result['status']!='unavailable' else 60),result)
        return result
