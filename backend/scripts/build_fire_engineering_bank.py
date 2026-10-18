"""Expand exact-acquisition cases without selecting by future burn/model scores.

One known-case regression cohort is preserved. New proposals use initial-image
metadata and past thermal acquisitions only. QC exclusions are retained.
"""
import argparse
import shutil
import time
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timedelta
import httpx
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import shape
from shapely.ops import transform
from shapely import contains_xy
import fire_engineering_common as c
b,prep,physics,ml=c.configure()


def copy_existing():
    for source in sorted((c.OLD/'cases').glob('*/case.json')):
        meta=c.read(source);folder=c.OUT/'cases'/meta['id'];folder.mkdir(parents=True,exist_ok=True)
        names=['case.json','single-run-weather.json']
        for key in ('baseline_scene','initial_scene','final_scene'):names += [meta[key]+'.npz',meta[key]+'.json']
        for name in set(names):
            destination=folder/name
            if not destination.exists():shutil.copy2(source.parent/name,destination)
        meta=c.read(folder/'case.json');meta['engineering_cohort']='previously_inspected_regression'
        meta['engineering_split']='validation2025' if meta['split']=='selection2025' else 'regression2026'
        c.write(folder/'case.json',meta)


def catalog_year(year):
    path=c.OUT/'catalogs'/f'bank-{year}.json'
    if path.exists():return c.read(path)['features']
    params={'collections':'sentinel-2-c1-l2a','bbox':'98.0,17.25,99.65,20.16',
            'datetime':f'{year}-01-01T00:00:00Z/{year}-05-01T00:00:00Z','limit':100}
    url='https://earth-search.aws.element84.com/v1/search';features={};pages=0;visited=set()
    while url:
        for attempt in range(5):
            try:
                r=httpx.get(url,params=params,timeout=90);r.raise_for_status();body=r.json();break
            except (httpx.HTTPError,ValueError):
                if attempt==4:raise
                time.sleep(2**attempt)
        pages+=1
        features.update({f['id']:f for f in body.get('features',[])})
        link=next((v for v in body.get('links',[]) if v.get('rel')=='next'),None)
        url=link['href'] if body.get('features') and link else None;params=None
        if url:
            assert url not in visited and pages<150;visited.add(url)
    c.write(path,{'features':list(features.values()),'pages':pages,'selection':'All Jan-Apr C1 imagery in fixed ChiangMai research bounding box, then initial-only thermal selection.'})
    print('CATALOG_READY',year,len(features),pages,flush=True)
    return list(features.values())


def proposals(year):
    points,times,xy=b.source_points(year);result=[]
    for scene in catalog_year(year):
        if scene['properties'].get('eo:cloud_cover',100)>90 or not all(k in scene['assets'] for k in b.ASSETS):continue
        when=b.stamp(scene['properties']['datetime']);asset=scene['assets']['nir08']
        # IFS single-run archive begins 2024-03-14. Do not download three
        # optical scenes for a case whose forecast initialization cannot exist.
        if when.isoformat()<'2024-03-15':continue
        affine,dimensions=asset.get('proj:transform'),asset.get('proj:shape')
        if not affine or not dimensions or asset.get('proj:code','EPSG:32647')!='EPSG:32647':continue
        west,north=affine[2],affine[5];east=west+dimensions[1]*affine[0];south=north+dimensions[0]*affine[4]
        valid=(times<=when.timestamp()-3*3600)&(times>when.timestamp()-27*3600)
        valid&=(xy[:,0]>west+6000)&(xy[:,0]<east-6000)&(xy[:,1]>south+6000)&(xy[:,1]<north-6000)
        indices=np.flatnonzero(valid)
        if len(indices)<3:continue
        footprint=transform(b.PROJECT.transform,shape(scene['geometry'])).buffer(-6000)
        indices=indices[contains_xy(footprint,xy[indices,0],xy[indices,1])]
        if len(indices)<3:continue
        counts=cKDTree(xy[indices]).query_ball_point(xy[indices],1500,return_length=True)
        index=int(np.argmax(counts));point=points[indices[index]];position=xy[indices[index]]
        tile=scene['id'].split('_')[1];case_id=f'{when.date()}-{tile}-{int(position[0]//100)}-{int(position[1]//100)}-bank'
        result.append({'id':case_id,'date':str(when.date()),'year':year,'latitude':point['latitude'],'longitude':point['longitude'],
                       'weather_run_interval_hours':12 if year==2024 else 6,
                       'initial_neighbour_count':int(counts[index]),'forced_initial_scene':scene['id'],'catalog_source':f'catalogs/bank-{year}.json',
                       'cohort':'initial_image_past_hotspot_bank','initial_acquisition':when.isoformat()})
    # Round-robin months prevents selecting only the hottest late-season days.
    grouped={month:sorted([r for r in result if r['date'][5:7]==month],key=lambda r:(-r['initial_neighbour_count'],r['id'])) for month in ('01','02','03','04')}
    interleaved=[]
    for i in range(max([len(v) for v in grouped.values()] or [0])):
        interleaved += [grouped[m][i] for m in grouped if i<len(grouped[m])]
    c.write(c.OUT/f'proposals-{year}.json',{'criterion':'RoundrobinJan-Apr, withinmonth past24hcluster count; no future labels/model scores. Separation>=12km OR>=14days within a source year.', 'candidates':interleaved})
    return interleaved


def compatible(candidate,others):
    position=np.array(b.PROJECT.transform(candidate['longitude'],candidate['latitude']))
    day=datetime.fromisoformat(candidate['date'])
    for other in others:
        if other['year']!=candidate['year']:continue
        other_date=datetime.fromisoformat(other.get('date',other['id'][:10]))
        distance=np.linalg.norm(position-np.array(b.PROJECT.transform(other['longitude'],other['latitude'])))
        if distance<12000 and abs((day-other_date).days)<14:return False
    return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--target-per-year',type=int,default=8);parser.add_argument('--max-attempts-per-year',type=int,default=24);args=parser.parse_args()
    c.OUT.mkdir(exist_ok=True);(c.OUT/'catalogs').mkdir(exist_ok=True);copy_existing()
    protocol={'target_new_ready_per_year':args.target_per_year,'max_quality_attempts_per_year':args.max_attempts_per_year,
       'roles':'2024train,2025validation;2026newcasesretrospectivegeneralizationandoldcasesregression. Previouslyinspectedyears,notprospective.',
       'selection':'Initialimage+pastVIIRSonly;allfutureQAexclusionsretained. No positive-burn-area cutoff.',
       'completion':'Expandbeyondold15cases,executeallproposedinputbranchesandfinitevalidationselectedcomparisons,verifyinitial-onlyreplayandproducefinaldecision. Noautomaticpromotion.'}
    c.write(c.OUT/'bank-protocol.json',protocol)
    source={year:proposals(year) for year in (2024,2025,2026)}
    for year in (2024,2025,2026):
        existing=[c.read(p) for p in (c.OUT/'cases').glob('*/case.json')]
        ready=[v['candidate'] for v in existing if v.get('engineering_cohort')=='expanded_bank' and v['candidate']['year']==year]
        prior=[v['candidate'] for v in existing];attempted=[]
        remaining=iter(source[year])
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending={};exhausted=False
            while pending or (len(ready)<args.target_per_year and len(attempted)<args.max_attempts_per_year and not exhausted):
                while len(pending)<3 and len(ready)+len(pending)<args.target_per_year and len(attempted)<args.max_attempts_per_year and not exhausted:
                    candidate=next(remaining,None)
                    if candidate is None:exhausted=True;break
                    folder=c.OUT/'cases'/candidate['id']
                    if (folder/'case.json').exists():continue
                    if (folder/'excluded.json').exists():
                        failed=c.read(folder/'excluded.json')
                        if candidate['year']==2024 and any('requested model run' in r.get('reason','') or 'HTTPStatusError' in r.get('reason','') for r in failed.get('excluded_triplets',[])):
                            c.write(folder/'excluded-first-weather-attempt.json',failed)
                        else:continue
                    if not compatible(candidate,prior+list(pending.values())):continue
                    attempted.append(candidate);pending[pool.submit(b.case,candidate)]=candidate
                if not pending:break
                done,_=wait(pending,return_when=FIRST_COMPLETED)
                for future in done:
                    candidate=pending.pop(future);result=future.result()
                    folder=c.OUT/'cases'/candidate['id']
                    if 'initial_scene' in result:
                        result['engineering_cohort']='expanded_bank';result['engineering_split']={2024:'train2024',2025:'validation2025',2026:'test2026_new_cases'}[year]
                        c.write(folder/'case.json',result);ready.append(candidate);prior.append(candidate)
                    c.write(c.OUT/f'bank-progress-{year}.json',{'ready':len(ready),'target':args.target_per_year,'attempts':attempted})
        print('YEAR_COMPLETE',year,len(ready),'new ready',len(attempted),'QC attempts',flush=True)
        c.write(c.OUT/f'bank-progress-{year}.json',{'ready':len(ready),'target':args.target_per_year,'attempts':attempted,'complete':True})
    quality=[];excluded=[]
    for path in sorted((c.OUT/'cases').glob('*/case.json')):
        meta=c.read(path)
        try:
            q=prep.prepare(meta);q['engineering_split']=meta['engineering_split'];q['engineering_cohort']=meta['engineering_cohort'];quality.append(q)
        except Exception as error:excluded.append({'id':meta['id'],'reason':str(error)})
    c.write(c.OUT/'array-manifest.json',{'ready':quality,'excluded':excluded})
    print('BANK_ARRAYS',len(quality),'ready',len(excluded),'excluded',flush=True)


if __name__=='__main__':main()
