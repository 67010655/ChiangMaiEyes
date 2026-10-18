"""Second, resolution-focused engineering iteration: initial-only 20m growth ML.

Designed after inspecting round1 2026 errors/grid ceiling; 2026 is therefore
reused retrospective evaluation, not a fresh independent test. All fitting and
threshold choice still use disjoint 2025 cases only; source cohort unchanged.
"""
import argparse
import hashlib
import json
import joblib
import numpy as np
from scipy.ndimage import distance_transform_edt, uniform_filter, label, binary_erosion
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits
import timed_fire_growth_ml as ml
import timed_fire_spread_benchmark as b

OUT=b.OUT/'growth-20m'
THRESHOLDS=(.001,.003,.01,.03,.10,.30)
CONFIGS={'dense_small':(60,15),'dense_large':(120,31)}
KNOWN=('initial_nbr','initial_falsecolor','initial_valid20','initial_scar_fraction','initial_scar20',
       'elevation_m','slope','aspect','landcover','burnable')


def features(meta,initial,include_pm=True):
    base,names,_=ml.make_features(meta,initial,include_pm=include_pm)
    X=np.repeat(np.repeat(base.reshape(100,100,-1),5,axis=0),5,axis=1).reshape(250000,-1)
    swir,nir,red=initial['initial_falsecolor']
    ndvi=(nir-red)/np.maximum(nir+red,1e-6)
    nbr=initial['initial_nbr']
    clear=initial['initial_valid20']
    distance=distance_transform_edt(~initial['initial_scar20'])*20 if initial['initial_scar20'].any() else np.full((500,500),20000.)
    extras=[nbr,ndvi,swir,nir,red,np.log1p(distance)]
    extras_names=['pixel_nbr','pixel_ndvi','pixel_swir','pixel_nir','pixel_red','log_pixel_distance_scar']
    count=uniform_filter(clear.astype(float),size=5,mode='nearest')
    for name,image in [('nbr',nbr),('ndvi',ndvi)]:
        mean=uniform_filter(np.where(clear,image,0),size=5,mode='nearest')/np.maximum(count,1e-6)
        extras.append(mean);extras_names.append('local100m_'+name)
    X=np.column_stack([X,*[np.where(clear,a,np.nan).ravel() for a in extras]]).astype('float32')
    eligible=clear & (ndvi>=.30) & ~initial['initial_scar20'] & np.repeat(np.repeat(initial['burnable'],5,axis=0),5,axis=1)
    return X,names+extras_names,eligible


def load(meta):
    folder=b.OUT/'cases'/meta['id']
    with np.load(folder/'model-arrays.npz') as archive:
        initial={name:archive[name] for name in KNOWN}
        arrays={name:archive[name] for name in ('valid20','initial_scar20','target20','target_low_fraction','target_high_fraction','connected_target20')}
        # Sensitivity labels are reconstructed from existing frozen per-scene
        # reference algorithm, not re-thresholded to optimize a model score.
    import prepare_timed_fire_arrays as prep
    before=dict(np.load(folder/(meta['initial_scene']+'.npz')))
    after=dict(np.load(folder/(meta['final_scene']+'.npz')))
    arrays['low20']=prep.changed(before,after,.10)&arrays['valid20']&~arrays['initial_scar20']
    arrays['high20']=prep.changed(before,after,.27)&arrays['valid20']&~arrays['initial_scar20']
    X,names,eligible=features(meta,initial)
    train_valid=eligible & arrays['valid20']
    return {'meta':meta,'initial':initial,'arrays':arrays,'X':X,'names':names,'eligible':eligible,'valid':train_valid.ravel(),'y':arrays['target20'].ravel().astype('uint8')}


def metrics(mask,arrays,key='target20'):
    support=arrays['valid20']&~arrays['initial_scar20']
    target=arrays[key]
    p=float((mask&support).sum()*.0004);r=float(target.sum()*.0004);i=float((mask&target).sum()*.0004)
    known=float((arrays['initial_scar20']&arrays['valid20']).sum()*.0004)
    result={'predicted_growth_km2':p,'reference_growth_km2':r,'intersection_km2':i,'dice':2*i/(p+r) if p+r else 1.,
            'iou':i/(p+r-i) if p+r-i else 1.,'cumulative_dice_including_initial':2*(known+i)/(2*known+p+r) if 2*known+p+r else 1.,
            'reference_coverage':i/r if r else None,'unmatched_prediction_km2':p-i,'missed_reference_km2':r-i}
    return result


def clean(mask):
    groups,_=label(mask,structure=np.ones((3,3)))
    keep=np.bincount(groups.ravel())>=5;keep[0]=False
    return keep[groups]


def fit(cases,name):
    rng=np.random.default_rng(20261018)
    xs=[];ys=[];weights=[]
    for case in cases:
        positive=np.flatnonzero(case['valid'] & (case['y']>0))
        negative=np.flatnonzero(case['valid'] & (case['y']==0))
        sample=rng.choice(negative,min(20000,len(negative)),replace=False)
        indices=np.r_[positive,sample]
        xs.append(case['X'][indices]);ys.append(case['y'][indices])
        weights.append(np.r_[np.ones(len(positive)),np.full(len(sample),len(negative)/max(1,len(sample)))])
    iterations,leaves=CONFIGS[name]
    model=HistGradientBoostingClassifier(max_iter=iterations,max_leaf_nodes=leaves,min_samples_leaf=50,l2_regularization=2,early_stopping=False,random_state=20261018)
    return model.fit(np.vstack(xs),np.concatenate(ys),sample_weight=np.concatenate(weights))


def masks(probability,eligible):
    return {name+'__threshold'+str(threshold):clean(eligible & (values.reshape(500,500)>=threshold))
            for name,values in probability.items() for threshold in THRESHOLDS}


def predict(meta,initial,selected=None):
    assert set(initial)==set(KNOWN)
    if selected is None:
        selected=b.read(OUT/'selection.json')['selected']
    name,threshold=selected.split('__threshold')
    X,names,eligible=features(meta,initial)
    model=joblib.load(OUT/(name+'.joblib'))
    values=model.predict_proba(X)[:,1].reshape(500,500)
    return clean(eligible & (values>=float(threshold)))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('selection','test'),required=True);args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    frozen=b.verify_frozen_inputs()
    metas=[b.read(b.OUT/'cases'/row['id']/'case.json') for row in frozen['cases']]
    protocol={'round':2,'designed_after_round1_test_inspection':True,'test_status':'Reused retrospective2026evaluation; not independent or prospective.',
       'reason':'100mfilled cells have a 48–67percent oracleDiceceilingon20mnew-scarlabels; try native20mpixelstate and initial-onlyvegetationeligibility.',
       'selection':'Samefour2025disjointcasefolds, meanDice; tie smaller predicted growth area then name. Never selectby2026score.',
       'configs':CONFIGS,'thresholds':THRESHOLDS,'postprocess':'Keep>=5connectedpredicted20mpixels, fixed before20mmodelscoring.',
       'negative_sampling':'Allpositives+up to20000negativespertraincase, inverse-selectionprobabilityweights preserveoriginalclassprior.',
       'features':'46initialcontextfeatures plus8native20mspectral/distance/localfeatures; no final imagery or future labels in inference.'}
    b.write(OUT/'protocol.json',protocol)
    if args.phase=='selection':
        training=[load(meta) for meta in metas if meta['split']=='selection2025']
        rows=[]
        for index,held in enumerate(training):
            others=[case for i,case in enumerate(training) if i!=index]
            probability={name:fit(others,name).predict_proba(held['X'])[:,1] for name in CONFIGS}
            scores={name:metrics(mask,held['arrays']) for name,mask in masks(probability,held['eligible']).items()}
            rows.append({'id':held['meta']['id'],'scores':scores});print('DENSE_FOLD',held['meta']['id'],flush=True)
        summary={name:{'macro_dice':float(np.mean([r['scores'][name]['dice'] for r in rows])),
                           'predicted_growth_km2':sum(r['scores'][name]['predicted_growth_km2'] for r in rows)} for name in rows[0]['scores']}
        ranking=sorted(summary,key=lambda name:(-summary[name]['macro_dice'],summary[name]['predicted_growth_km2'],name))
        b.write(OUT/'selection.json',{'selected':ranking[0],'ranking':ranking,'validation':summary,'folds':rows,'2026used_for_fitting_or_threshold_selection':False})
        for name in CONFIGS:
            joblib.dump(fit(training,name),OUT/(name+'.joblib'))
        b.write(OUT/'frozen-selection.json',{'selection_sha256':hashlib.sha256((OUT/'selection.json').read_bytes()).hexdigest(),
            'weights':{name:hashlib.sha256((OUT/(name+'.joblib')).read_bytes()).hexdigest() for name in CONFIGS}})
        print('DENSE_SELECTED',ranking[0],summary[ranking[0]],flush=True)
    else:
        receipt=b.read(OUT/'frozen-selection.json')
        assert receipt['selection_sha256']==hashlib.sha256((OUT/'selection.json').read_bytes()).hexdigest()
        for name,digest in receipt['weights'].items():
            assert digest==hashlib.sha256((OUT/(name+'.joblib')).read_bytes()).hexdigest()
        selected=b.read(OUT/'selection.json')['selected'];rows=[]
        for meta in metas:
            if meta['split']!='retrospective_test2026':continue
            case=load(meta)
            probability={name:joblib.load(OUT/(name+'.joblib')).predict_proba(case['X'])[:,1] for name in CONFIGS}
            predictions=masks(probability,case['eligible']);scores={}
            for name,mask in predictions.items():
                score=metrics(mask,case['arrays'])
                score['connected_growth']=metrics(mask,case['arrays'],'connected_target20')
                score['low_reference_threshold']=metrics(mask,case['arrays'],'low20')
                score['high_reference_threshold']=metrics(mask,case['arrays'],'high20')
                predicted=mask&case['arrays']['valid20']&~case['arrays']['initial_scar20'];reference=case['arrays']['target20']
                a=predicted&~binary_erosion(predicted);bb=reference&~binary_erosion(reference)
                if a.any() and bb.any():
                    distances=np.r_[distance_transform_edt(~a)[bb]*20,distance_transform_edt(~bb)[a]*20]
                    score.update(symmetric_boundary_mean_m=float(distances.mean()),symmetric_boundary_p95_m=float(np.percentile(distances,95)))
                else:score.update(symmetric_boundary_mean_m=None,symmetric_boundary_p95_m=None)
                scores[name]=score
            rows.append({'id':meta['id'],'scores':scores})
            np.savez_compressed(b.OUT/'cases'/meta['id']/'growth-20m-predictions.npz',**predictions)
            print('DENSE_TEST',meta['id'],round(scores[selected]['dice'],4),flush=True)
        b.write(OUT/'test-results.json',{'selected_on2025':selected,'rows':rows})


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
