"""Past-only supplemental features; public archives, explicit availability assumptions.

No target/final imagery is read here. A missing/empty Himawari detection layer
is not a cloud-free negative. ESA 2023 is a fixed coarse seasonal prior, never
the target-year burned area. These are retrospective experiments.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,time
import httpx
import numpy as np
from scipy.spatial import cKDTree
import fire_engineering_common as c
import probe_himawari_fire_sources as h
b,prep,physics,ml=c.configure()


def get(url):
    for attempt in range(4):
        try:
            response=httpx.get(url,timeout=60,follow_redirects=True);response.raise_for_status();return response
        except httpx.HTTPError:
            if attempt==3:raise
            time.sleep(attempt+1)


def esa_prior(month):
    folder=c.OUT/'esa-prior';folder.mkdir(exist_ok=True)
    listing=folder/'catalog-2023.json'
    if not listing.exists():
        url='https://data.ceda.ac.uk/neodc/esacci/fire/data/burned_area/Sentinel3_SYN/grid/v1.1/2023?json'
        c.write(listing,dict(get(url).json(),source_url=url))
    entry=next(item for item in c.read(listing)['items'] if item['name'].startswith('2023'+month+'01'))
    path=folder/entry['name']
    if not path.exists():
        payload=get(entry['download']).content
        assert len(payload)==entry['size'] and hashlib.md5(payload).hexdigest()==entry['md5']
        path.write_bytes(payload)
    return path


def initial_features(meta):
    folder=c.OUT/'cases'/meta['id'];path=folder/'initial-supplement.npz';receipt_path=folder/'initial-supplement.json'
    if path.exists() and receipt_path.exists():
        receipt=c.read(receipt_path)
        if receipt.get('version')==1:return dict(np.load(path)),receipt
    origin=datetime.fromisoformat(meta['initial_acquisition']);end=(origin-timedelta(hours=3)).replace(minute=0,second=0,microsecond=0)
    times=[end-timedelta(hours=3*i) for i in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        frames=list(pool.map(lambda stamp:h.fetch_frame(stamp,c.OUT/'himawari-bank'),times))
    events=[e for _,rows in frames for e in rows if e['quality_eligible']]
    assert all(datetime.fromisoformat(e['observation_time_utc'])<=origin-timedelta(hours=3) for e in events)
    west,south,east,north=meta['bounds_utm47'];rr,cc=np.indices((100,100));xx=west+(cc+.5)*100;yy=north-(rr+.5)*100
    xy=np.column_stack([xx.ravel(),yy.ravel()])
    extras=[];names=[]
    def add(name,values):
        a=np.broadcast_to(values,(100,100)).astype('float32');extras.append(a);names.append(name)
    if events:
        pos=np.column_stack(b.PROJECT.transform([e['longitude'] for e in events],[e['latitude'] for e in events]))
        distance,index=cKDTree(pos).query(xy)
        ages=np.array([(origin-datetime.fromisoformat(e['observation_time_utc'])).total_seconds()/3600 for e in events])
        add('hima_log_distance',np.log1p(distance).reshape(100,100))
        add('hima_nearest_age_days',(ages[index]/24).reshape(100,100))
        add('hima_nearest_reliability',np.array([e['reliability'] for e in events])[index].reshape(100,100))
        add('hima_log_detections_4km',np.log1p(cKDTree(pos).query_ball_point(xy,4000,return_length=True)).reshape(100,100))
    else:
        for name in ('hima_log_distance','hima_nearest_age_days','hima_nearest_reliability','hima_log_detections_4km'):add(name,np.nan)
    add('hima_frame_retrieval_fraction',sum(r['status']=='ok' for r,_ in frames)/len(frames))
    # Two images already acquired at initialization; no after image in these deltas.
    initial=dict(np.load(folder/(meta['initial_scene']+'.npz')))
    before=dict(np.load(folder/(meta['baseline_scene']+'.npz')))
    valid=initial['valid']&before['valid']
    for name,image in [('past_ndvi_change',initial['ndvi']-before['ndvi']),('past_nbr_change',initial['nbr']-before['nbr'])]:
        mean,_=ml.aggregate_initial(image,valid);add(name,mean)
    add('season_sin',np.sin(2*np.pi*origin.timetuple().tm_yday/365.25))
    add('season_cos',np.cos(2*np.pi*origin.timetuple().tm_yday/365.25))
    source=esa_prior(f'{origin.month:02d}')
    import rasterio
    lon,lat=b.INVERSE.transform(xx,yy)
    for variable in ('burned_area','fraction_of_observed_area'):
        with rasterio.open(f'NETCDF:"{source}":{variable}') as dataset:
            values=np.array(list(dataset.sample(np.column_stack([lon.ravel(),lat.ravel()]))))[:,0]
            values[values==dataset.nodata]=np.nan
            if variable=='burned_area':values=np.log1p(values/1e6)
            add('esa2023_'+variable,values.reshape(100,100))
    result={'coarse':np.stack(extras),'feature_names':np.array(names),
            'past_clear20':valid,'past_ndvi_change20':np.where(valid,initial['ndvi']-before['ndvi'],np.nan),
            'past_nbr_change20':np.where(valid,initial['nbr']-before['nbr'],np.nan)}
    np.savez_compressed(path,**result)
    receipt={'version':1,'initial_acquisition':origin.isoformat(),'himawari_delay_assumption_hours':3,'himawari_cadence_hours':3,
      'himawari_frames':[{k:v for k,v in r.items() if k!='error'} for r,_ in frames],'quality_eligible_events':len(events),
      'himawari_missing_or_empty':'Unknown activity, not no-fire; no cloud-observation mask. FRP excluded because web units unverified.',
      'esa_prior_year':2023,'esa_month':origin.month,'esa_sha256':c.sha(source),'esa_resolution_degrees':.25,
      'esa_interpretation':'Fixed previous-year seasonal burned-area context; monthly cells not 20m fire boundaries. Product release not simulated as-issued.',
      'spectral_deltas':'baseline-to-initial only; no final image or reference mask read','names':names,'npz_sha256':c.sha(path)}
    c.write(receipt_path,receipt);print('SUPPLEMENT_READY',meta['id'],len(events),'hima events',flush=True)
    return result,receipt


if __name__=='__main__':
    for path in sorted((c.OUT/'cases').glob('*/case.json')):initial_features(c.read(path))
