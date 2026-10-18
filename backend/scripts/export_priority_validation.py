"""Export reproducible historical examples and community-neighbourhood subgroup.

No live forecast is generated here. Fixed examples are calendar snapshots,
not selected by model gain. Community zones are polygon buffers of1000m.
"""
import hashlib,json,math,os
from datetime import datetime,timedelta
import joblib,numpy as np
from shapely import make_valid,contains_xy
from shapely.geometry import shape,Point,Polygon,mapping
from shapely.ops import transform,unary_union
from priority_forecast_experiment import OUT,ROOT,ICT,RES,build_grid,load_year,issues,features,labels,projection,inverse,write,read

EXAMPLES=('2026-03-15T08:00:00+07:00','2026-04-15T08:00:00+07:00','2026-04-30T08:00:00+07:00')
def collection(grid,indices):
    full=sorted(int(i) for i in grid['fullindex'][indices]);width=int(grid['width']);runs=[]
    for i in full:
        row,col=divmod(i,width)
        if runs and runs[-1][0]==row and runs[-1][2]+1==col:runs[-1][2]=col
        else:runs.append([row,col,col])
    features_=[]
    for row,left,right in runs:
        west=float(grid['west'])+left*RES;east=float(grid['west'])+(right+1)*RES
        north=float(grid['north'])-row*RES;south=north-RES
        ring=[list(inverse.transform(x,y)) for x,y in [(west,north),(east,north),(east,south),(west,south),(west,north)]]
        features_.append({'type':'Feature','properties':{},'geometry':{'type':'Polygon','coordinates':[ring]}})
    return {'type':'FeatureCollection','features':features_}
def order(values):return np.lexsort((np.arange(len(values)),-values))[:1000]
def main():
    grid=build_grid();data=load_year(2026);summary=read(OUT/'summary.json');selected=summary['selected'];assert selected=='boost15'
    model=joblib.load(OUT/(selected+'.joblib'));source=ROOT/'backend/app/data/community-forests-chiangmai.geojson'
    forests=read(source)['features'];assert len(forests)==677
    polygons=[make_valid(transform(projection.transform,shape(f['geometry']))) for f in forests]
    neighbourhood=unary_union([p.buffer(1000) for p in polygons]);mask=contains_xy(neighbourhood,*grid['xy'].T)
    records=[];examples=[]
    for n,origin in enumerate(issues(2026)):
        X,bases=features(data,origin,grid)
        if X is None:continue
        y,meta=labels(data,origin,grid);ml=order(model.predict_proba(X)[:,1]);base=order(bases['day'])
        record={'issued_at':origin.isoformat(),'target_cells_near_forests':int(y[mask].sum()),
                'ml_hits_near_forests':int(y[ml][mask[ml]].sum()),'baseline_hits_near_forests':int(y[base][mask[base]].sum()),
                'ml_alert_cells_near_forests':int(mask[ml].sum()),'baseline_alert_cells_near_forests':int(mask[base].sum())}
        records.append(record)
        if origin.isoformat() in EXAMPLES:
            geometry=collection(grid,ml);baseline=collection(grid,base);area=unary_union([shape(f['geometry']) for f in geometry['features']])
            area=transform(projection.transform,area);ranking=[]
            for f,polygon in zip(forests,polygons):
                nearby=area.intersection(polygon.buffer(1000)).area/1e6
                if nearby>0:ranking.append({'id':f['properties']['id'],'name':f['properties']['name'],'plot_no':f['properties'].get('plotNo'),'amphoe':f['properties'].get('amphoe'),
                    'selected_area_within1km_km2':round(nearby,3),'geometry':f['geometry']})
            ranking.sort(key=lambda f:(-f['selected_area_within1km_km2'],f['id']))
            positive=np.flatnonzero(y);examples.append({'issued_at':origin.isoformat(),'valid_until':(origin+timedelta(hours=12)).isoformat(),
                **meta,'ml_hits':int(y[ml].sum()),'baseline_hits':int(y[base].sum()),'selected_area_km2':250,
                'ml_geometry':geometry,'baseline_geometry':baseline,
                'later_cell_centres':[[round(float(grid['lat'][i]),6),round(float(grid['lon'][i]),6)] for i in positive],
                'community_watchlist':ranking[:10]})
        if n%60==0:print('export',n,flush=True)
    subgroup={'definition':'500m-cell centre inside1km buffer of any of677verified community-forest polygons; not verified fire inside forest.',
       'community_forests':677,'candidate_cells_in_zone':int(mask.sum()),'zone_grid_area_km2':float(mask.sum()*.25),'rows':records,
       **{k:sum(r[k] for r in records) for k in records[0] if k!='issued_at'}}
    write(OUT/'community-subgroup.json',subgroup);write(OUT/'examples.json',examples)
    print('community',json.dumps({k:v for k,v in subgroup.items() if k!='rows'}),flush=True)
    assert len(examples)==len(EXAMPLES)
if __name__=='__main__':main()
