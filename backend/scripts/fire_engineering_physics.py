"""Spatial numeric wind and seasonal-fuel sensitivity in the existing graph.

Not a new full fire simulator: same 100m8-neighbour graph/surface equations,
no crown/spotting/suppression. Spectral dryness is an explicit hypothesis.
"""
import argparse,math,hashlib,json
from datetime import datetime
from functools import lru_cache
import numpy as np
from scipy.spatial import cKDTree
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
from probe_native_weather_grid import fetch_historical_case_grid,sample_wind
from run_fire_engineering_loop import metas,pooled

OUT=c.OUT/'physics'
CONFIGS=[{'name':f'{mode}_active{hours}','family':'pyre_graph','fuel':'mapped8','moisture':'dynamic',
    'seed':'point','scale':.25,'wind_factor':.2,'active_hours':hours,'spatial':mode!='point','seasonal':mode=='spatial_seasonal'}
    for mode in ('point','spatial','spatial_seasonal') for hours in (6,24)]


class GridRates(physics.Rates):
    @lru_cache(maxsize=100000)
    def peak(self,row,col,hour):
        cover=int(self.arrays['landcover'][row,col]);fuel={10:8,20:5}.get(cover,1)
        record=self.records[hour]
        wind,direction=record['wind'],record['from']
        if self.config.get('spatial'):
            u,v=record['u_grid'][row,col],record['v_grid'][row,col]
            wind=float(np.hypot(u,v));direction=float((270-np.degrees(np.arctan2(v,u)))%360)
        value=physics.sf.calc_surface_fire_behavior_max(self.base(hour,fuel),wind*self.config['wind_factor']*60,direction,
            float(self.arrays['slope'][row,col]),float(self.arrays['aspect'][row,col]))
        # Fixed before scoring; a vegetation proxy, never a measured fuel load.
        phenology=float(self.arrays['dryness_proxy'][row,col]) if self.config.get('seasonal') else 1.
        return value.max_spread_rate*phenology,value.eccentricity,value.max_spread_direction


def forcing(meta):
    folder=c.OUT/'cases'/meta['id'];records,horizon=physics.weather_for(folder,meta)
    grid=fetch_historical_case_grid(meta,folder);west,south,east,north=meta['bounds_utm47'];rr,cc=np.indices((100,100))
    xy=np.column_stack([(west+(cc+.5)*100).ravel(),(north-(rr+.5)*100).ravel()])
    source=np.column_stack(b.PROJECT.transform(grid['longitude'],grid['latitude']));_,index=cKDTree(source).query(xy)
    times={datetime.fromisoformat(str(t)):i for i,t in enumerate(grid['valid_time_utc'])};origin=datetime.fromisoformat(meta['initial_acquisition']).replace(tzinfo=None)
    from datetime import timedelta
    for record in records:
        when=origin+timedelta(minutes=record['start']);i=times[when.replace(second=0,microsecond=0)]
        record['u_grid']=grid['u10_m_s'][i,index].reshape(100,100);record['v_grid']=grid['v10_m_s'][i,index].reshape(100,100)
        assert np.isfinite(record['u_grid']).all() and np.isfinite(record['v_grid']).all()
    return records,horizon


def predict(meta,initial,config):
    records,horizon=forcing(meta)
    a=dict(initial);swir,nir,red=a['initial_falsecolor'];ndvi=(nir-red)/np.maximum(nir+red,1e-6)
    mean,_=ml.aggregate_initial(ndvi,a['initial_valid20'])
    a['dryness_proxy']=np.clip(1.5-np.nan_to_num(mean,nan=.5),.5,1.5)
    return np.isfinite(physics.simulate(a,records,horizon,config,rates_class=GridRates))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('selection','test'),required=True);parser.add_argument('--warmup-only',action='store_true');args=parser.parse_args();OUT.mkdir(exist_ok=True)
    c.write(OUT/'protocol.json',{'configs':CONFIGS,'train':'No learned parameters. Fixed hypotheses before2025scoring.',
      'selection':'2025pooledDice; tie smaller predicted area then name. Freeze before2026.',
      'wind':'Nearest actual returned4corner IFS model nodes, same initialization/validhours, m/s east/north to meteorological FROM.',
      'seasonal':'Multiply Rothermel head rate by clip(1.5-initial100mmeanNDVI,.5,1.5). Explicit empirical sensitivity, not validated fuel load.',
      'active_hours':'Total elapsed spread cap6/24h, not a daily suppression cycle. Image horizons longer; limited-growth hypothesis.',
      'boundary':'No crown/spotting/suppression/subgrid wind. Current native GRIB only numerical integration smoke, not substituted for historical wind.'})
    if args.phase=='test':assert c.sha(OUT/'selection.json')==c.read(OUT/'frozen-selection.json')['selection_sha256']
    configs=CONFIGS if args.phase=='selection' else [config for config in CONFIGS if config['name']==c.read(OUT/'selection.json')['selected']]
    rows=[]
    for meta in metas():
        if (meta['engineering_split']=='validation2025')!=(args.phase=='selection') or meta['engineering_split']=='train2024':continue
        folder=c.OUT/'cases'/meta['id']
        with np.load(folder/'model-arrays.npz') as archive:
            known={k:archive[k] for k in ('slope','aspect','landcover','burnable','seeds_point','elevation_m','initial_falsecolor','initial_valid20')}
            arrays={k:archive[k] for k in ('target_fraction','growth_support_fraction','initial_scar20','valid20')}
        scores={}
        for config in configs:
            cache=folder/(config['name']+'-field-prediction.npz')
            digest=hashlib.sha256(json.dumps({'config':config,'initial':meta['initial_acquisition'],'requested_until':meta['final_acquisition'],
              'weather':c.sha(folder/'single-run-weather.json'),'grid':c.sha(folder/'corner-weather.npz'),
              'code':c.sha(__file__)},sort_keys=True).encode())
            for name,value in sorted(known.items()):digest.update(name.encode()+value.tobytes())
            fingerprint=digest.hexdigest();mask=None
            if cache.exists():
                with np.load(cache) as saved:
                    if 'known_input_sha256' in saved.files and saved['known_input_sha256'].item()==fingerprint:mask=saved['predicted']
            if mask is None:
                mask=predict(meta,known,config);np.savez_compressed(cache,predicted=mask,known_input_sha256=fingerprint)
            scores[config['name']]=physics.metrics(mask,arrays)
            print('PHYSICS',args.phase,meta['id'],config['name'],scores[config['name']]['dice'],flush=True)
        rows.append({'id':meta['id'],'split':meta['engineering_split'],'scores':scores});c.write(OUT/(args.phase+'-progress.json'),{'rows':rows})
    if args.warmup_only:
        print('PHYSICS_CACHE_WARMED_NO_SELECTION',len(rows),flush=True);return
    summary={name:pooled(rows,name) for name in rows[0]['scores']};result={'rows':rows,'summary':summary}
    if args.phase=='selection':
        ranking=sorted(summary,key=lambda n:(-summary[n]['pooled_dice'],summary[n]['predicted_growth_km2'],n));result.update(selected=ranking[0],ranking=ranking)
        c.write(OUT/'selection.json',result);c.write(OUT/'frozen-selection.json',{'selection_sha256':c.sha(OUT/'selection.json')})
    else:
        result['selected_on2025']=configs[0]['name'];result['by_split']={split:{name:pooled([r for r in rows if r['split']==split],name) for name in summary} for split in sorted({r['split'] for r in rows})}
        c.write(OUT/'test-results.json',result)


if __name__=='__main__':main()
