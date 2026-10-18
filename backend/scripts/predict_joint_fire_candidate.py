"""Run the frozen offline candidate without fitting or reading target labels."""
import argparse,hashlib,json
from datetime import datetime,timedelta
import joblib,numpy as np
from joint_fire_experiment import ROOT,OUT,ICT,ALL_NAMES,build_grid,load,prepare,read,write

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--as-of',required=True);parser.add_argument('--area-km2',type=float,default=250);args=parser.parse_args()
    origin=datetime.fromisoformat(args.as_of)
    if origin.tzinfo is None:raise ValueError('as-of must include timezone, e.g.2026-04-15T08:00:00+07:00')
    origin=origin.astimezone(ICT)
    if origin.hour not in (8,20) or origin.minute or origin.second or origin.microsecond:
        raise ValueError('This experiment was evaluated only at08:00/20:00ICT.')
    if args.area_km2 not in (125.,250.,500.):raise ValueError('Evaluated area budgets are125,250or500km2.')
    folder=OUT/('final-candidate' if (OUT/'final-candidate/feature-contract.json').exists() else 'candidate')
    spec=read(folder/'feature-contract.json');model_path=folder/'model.joblib'
    assert hashlib.sha256(model_path.read_bytes()).hexdigest()==spec['model_sha256']
    grid=build_grid();data=load(origin.year,grid);prepared,reason=prepare(data,origin,grid)
    if prepared is None:raise ValueError('Required historical inputs unavailable: '+reason)
    X,_,_=prepared
    # Whole-pipeline leakage check: delete every acquisition/PM row that would
    # not be available yet. Features must be bit-for-bit unchanged (NaNs equal).
    eligible=data['times']<=origin.timestamp()-3*3600;pm_cutoff=str(origin.date()-timedelta(days=2))
    truncated={**data,**{k:data[k][eligible] for k in ('times','xy','frp')},'pm':{d:v for d,v in data['pm'].items() if d<=pm_cutoff}}
    again,reason=prepare(truncated,origin,grid)
    assert again is not None,reason
    np.testing.assert_array_equal(X,again[0])
    if spec.get('feature_pipeline')=='joint59_cams':
        from joint_spatial_pm_experiment import load_cams,spatial_pm_features,CAMSNAMES
        cams=load_cams(origin.year,grid);extra=spatial_pm_features(data,origin,grid,cams)
        if extra is None:raise ValueError('Required earlier spatial PM unavailable')
        cams_truncated={**cams,'dates':{d:v for d,v in cams['dates'].items() if d<=pm_cutoff}}
        extra_check=spatial_pm_features(truncated,origin,grid,cams_truncated)
        np.testing.assert_array_equal(extra,extra_check)
        X=np.column_stack([X,extra]);assert spec['full_feature_order']==ALL_NAMES+CAMSNAMES
    else:assert spec['full_feature_order']==ALL_NAMES
    model=joblib.load(model_path);values=model.predict_proba(X[:,spec['feature_columns']])[:,1]
    count=min(len(values),round(args.area_km2/.25));order=np.lexsort((np.arange(len(values)),-values))[:count]
    result={'mode':'offline_historical_candidate','as_of':origin.isoformat(),'valid_until':(origin+timedelta(hours=12)).isoformat(),
       'model':spec['model_selected_on2025'],'model_sha256':spec['model_sha256'],'forecast_target':spec['target'],
       'selected_area_km2':count*.25,'hotspot_last_eligible_acquisition':(origin-timedelta(hours=3)).isoformat(),
       'pm_latest_eligible_date':str(origin.date()-timedelta(days=2)),'score_meaning':'Ranking only; not a calibrated fire probability.',
       'cells':[{'rank':rank+1,'latitude':float(grid['lat'][i]),'longitude':float(grid['lon'][i]),'rank_score':float(values[i])} for rank,i in enumerate(order)],
       'labels_read_for_prediction':False,'future_input_truncation_check':'exact feature equality passed',
       'unavailable_hotspot_rows_removed_for_check':int((~eligible).sum()),'production_changed':False}
    output=folder/('forecast-'+origin.strftime('%Y%m%dT%H%M')+'.json');write(output,result)
    print(json.dumps({'file':str(output),'selected_cells':count,'area_km2':count*.25,'model':result['model']}))
if __name__=='__main__':main()
