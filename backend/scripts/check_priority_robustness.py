"""Stronger tuned nearest-neighbour baseline; select2025 before scoring2026."""
import json,math
import numpy as np
from scipy.spatial import cKDTree
from priority_forecast_experiment import OUT,build_grid,load_year,issues,labels,write,read

CONFIGS=[{'range_m':r,'age_hours':h,'frp_weight':f} for r in (500,1500,3000) for h in (6,12,24) for f in (False,True)]
def scores(data,origin,grid,configs):
    cutoff=origin.timestamp()-3*3600;a=np.searchsorted(data['times'],cutoff-24*3600);b=np.searchsorted(data['times'],cutoff,side='right')
    if b==a:return {str(i):np.zeros(len(grid['xy'])) for i in configs}
    distance,index=cKDTree(data['xy'][a:b]).query(grid['xy'],k=min(8,b-a),workers=1)
    if distance.ndim==1:distance=distance[:,None];index=index[:,None]
    age=(origin.timestamp()-data['times'][a:b][index])/3600;power=1+np.log1p(data['frp'][a:b][index])
    return {str(i):np.max(np.exp(-distance/CONFIGS[i]['range_m']-age/CONFIGS[i]['age_hours'])*(power if CONFIGS[i]['frp_weight'] else 1),axis=1) for i in configs}
def evaluate(year,grid,indices):
    data=load_year(year);rows=[]
    for n,origin in enumerate(issues(year)):
        y,meta=labels(data,origin,grid);result={}
        for name,values in scores(data,origin,grid,indices).items():
            top=np.lexsort((np.arange(len(values)),-values))[:2000]
            result[name]={str(b):int(y[top[:round(b/.25)]].sum()) for b in (125.,250.,500.)}
        rows.append({'issued_at':origin.isoformat(),**meta,'hits':result})
        if n%60==0:print('baseline',year,n,flush=True)
    return {'year':year,'rows':rows,'summary':{'issues':len(rows),'target_cells_all':sum(r['target_cells_all'] for r in rows),
        'hits':{str(i):{str(b):sum(r['hits'][str(i)][str(b)] for r in rows) for b in (125.,250.,500.)} for i in indices}}}
def bootstrap(rows,baseline_rows):
    byday={};other={r['issued_at']:r for r in baseline_rows}
    for r in rows:
        v=byday.setdefault(r['issued_at'][:10],np.zeros(4));v+=np.array([r['target_cells_all'],r['hits']['boost15']['250.0'],r['hits']['day']['250.0'],other[r['issued_at']]['hits'][next(iter(other[r['issued_at']]['hits']))]['250.0']])
    matrix=np.array(list(byday.values()));rng=np.random.default_rng(20261017)
    draws=np.array([matrix[rng.integers(0,len(matrix),len(matrix))].sum(axis=0) for _ in range(5000)])
    blockdraws=[]
    for _ in range(5000):
        starts=rng.integers(0,len(matrix),math.ceil(len(matrix)/7))
        indices=np.concatenate([(s+np.arange(7))%len(matrix) for s in starts])[:len(matrix)]
        blockdraws.append(matrix[indices].sum(axis=0))
    blocks=np.array(blockdraws)
    return {'unit':'ICT issue calendar day, paired resampling; seven-day circular moving blocks additionally account for short-range dependence.','replicates':5000,
      'coverage_gain_pp_vs_frozen_day_95pct':list(np.percentile(100*(draws[:,1]-draws[:,2])/draws[:,0],[2.5,97.5])),
      'coverage_gain_pp_vs_tuned_kernel_95pct':list(np.percentile(100*(draws[:,1]-draws[:,3])/draws[:,0],[2.5,97.5])),
      'moving_block7day_gain_pp_vs_tuned_kernel_95pct':list(np.percentile(100*(blocks[:,1]-blocks[:,3])/blocks[:,0],[2.5,97.5]))}
def main():
    grid=build_grid();path=OUT/'kernel-validation2025.json'
    val=read(path) if path.exists() else evaluate(2025,grid,list(range(len(CONFIGS))));write(path,val)
    chosen=max(range(len(CONFIGS)),key=lambda i:val['summary']['hits'][str(i)]['250.0'])
    write(OUT/'kernel-selection.json',{'chosen_index':chosen,'config':CONFIGS[chosen],'configs':CONFIGS,'selection':'Highest pooled250km2 coverage on2025 only; max of8nearest prior24h points;3h latency.'})
    test=evaluate(2026,grid,[chosen]);write(OUT/'kernel-test2026.json',test)
    main_test=read(OUT/'test2026.json');report={'baseline_config':CONFIGS[chosen],'validation':val['summary'],'test':test['summary'],'paired_day_bootstrap':bootstrap(main_test['rows'],test['rows'])}
    write(OUT/'robustness.json',report);print('RESULT',json.dumps(report),flush=True)
if __name__=='__main__':main()
