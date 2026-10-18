"""Round2: use more past events, date-blocked2025CV, then refit past-only.

Designed after round1 2026 results;2026 is explicitly reused retrospective
evaluation. No2026labels/score select configurations or thresholds here.
Original round1 choices/weights/data remain frozen and unchanged.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse,gc,hashlib
from collections import defaultdict
import numpy as np,joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits
from scipy.ndimage import binary_erosion,distance_transform_edt
import fire_engineering_common as c
import run_fire_engineering_loop as loop
import timed_fire_growth_dense as dense

OUT=c.OUT/'refit-loop'
CONFIGS={'point_no_pm_small':('point_no_pm',60,15),'point_no_pm_large':('point_no_pm',120,31),
         'point_pm_small':('point_pm',60,15),'all_small':('all',60,15)}
THRESHOLDS=(.003,.01,.03,.10,.30)


def contract():
    return {'round':2,'reason':'Round1traininghad8casesfrom4dates. Testwhethermoreindependentpast-eventdatahelpsbeforeaddinganotherdatasource.',
      'designed_after_round1_2026_inspection':True,'test_status':'All2026casesreusedretrospectiveevaluation, nofreshunseenholdoutclaim.',
      'selection':'2025dateblocked3foldCV; everyfold includesall2024casesplusother2025dategroups. Same11held2025cases/labelsasparentselection. Noheldevent/datepixelsinfitting.',
      'grouping':'All2025caseswithsameactualinitialUTCdateareheldtogether; newcasecentre>=12kmOR>=14days, remainingcrossdateeventcorrelationpossible.',
      'train_final':'Fitselectedarchitectureonall2024+2025casesafterthreshold/configchoice; no2026fitting.',
      'configs':CONFIGS,'thresholds':THRESHOLDS,'parent':'Previouslyfrozen2024-trainedpoint_no_pm__0.03; eligibletooutscoreCVcandidates.',
      'criterion':'2025poolednewgrowthDice; tieslesspredictedarea thenname. Freezechoiceandfinalweightsbeforeanyround2_2026score.',
      'sampling':'Allpositivepixels+up15000negativespercase; inverse-selectionweights. Same deterministic sampledrowsforallcandidatesandfolds.',
      'stop':'Exactly4configurationsx5thresholdsplusparent, thentest/causalreplay/report. Noadditional2026-drivenretuninginthisround.',
      'scope':'Offlineonly, noapp/UI/deploy.'}


def prepare_samples(metas):
    folder=OUT/'samples';folder.mkdir(exist_ok=True);result={};rng=np.random.default_rng(20261018)
    for meta in metas:
        case=loop.load(meta);pos=np.flatnonzero(case['valid']&(case['y']>0));neg=np.flatnonzero(case['valid']&(case['y']==0));sample=rng.choice(neg,min(15000,len(neg)),replace=False);ix=np.r_[pos,sample]
        data={'X':case['X'][ix],'y':case['y'][ix],'w':np.r_[np.ones(len(pos)),np.full(len(sample),len(neg)/max(1,len(sample)))]}
        np.savez_compressed(folder/(meta['id']+'.npz'),**data);result[meta['id']]=data
        del case;gc.collect();print('REFIT_SAMPLE',meta['id'],len(pos),'positive',flush=True)
    return result


def fit(metas,samples,config):
    group,iterations,leaves=CONFIGS[config];spec=c.read(loop.MODEL_DIR/'feature-contract.json');columns=spec['groups'][group]
    X=np.vstack([samples[m['id']]['X'][:,columns] for m in metas]);y=np.concatenate([samples[m['id']]['y'] for m in metas]);w=np.concatenate([samples[m['id']]['w'] for m in metas])
    model=HistGradientBoostingClassifier(max_iter=iterations,max_leaf_nodes=leaves,min_samples_leaf=75,l2_regularization=2,early_stopping=False,random_state=20261018)
    return model.fit(X,y,sample_weight=w)


def predict(meta,initial,choice=None):
    choice=choice or c.read(OUT/'selection.json')
    if choice['selected']=='parent':return loop.predict(meta,initial)
    name,threshold=choice['selected'].rsplit('__',1);group=CONFIGS[name][0];spec=c.read(loop.MODEL_DIR/'feature-contract.json')
    if group in ('point_no_pm','point_pm'):X,names,eligible=dense.features(meta,initial,include_pm=group=='point_pm')
    else:X,names,eligible,_=loop.features(meta,initial)
    columns=spec['groups'][group];assert [names[i] for i in columns]==[spec['names'][i] for i in columns]
    model=joblib.load(OUT/'model.joblib')
    return dense.clean(eligible&(model.predict_proba(X[:,columns])[:,1].reshape(500,500)>=float(threshold)))


def select():
    OUT.mkdir(exist_ok=True);c.write(OUT/'protocol.json',contract())
    metas=loop.metas();training=[m for m in metas if m['engineering_split']=='train2024'];validation=[m for m in metas if m['engineering_split']=='validation2025'];past=training+validation
    samples=prepare_samples(past);dates=[m['initial_acquisition'][:10] for m in validation];splitter=GroupKFold(n_splits=3);rows=[];folds=[]
    spec=c.read(loop.MODEL_DIR/'feature-contract.json');parent=c.read(loop.MODEL_DIR/'selection.json');parent_rows={r['id']:r['scores'][parent['selected']] for r in parent['rows']}
    for fold,(included,held) in enumerate(splitter.split(np.arange(len(validation)),groups=dates)):
        fitting=training+[validation[i] for i in included];testing=[validation[i] for i in held]
        assert not ({m['initial_acquisition'][:10] for m in fitting if m['engineering_split']=='validation2025'}&{m['initial_acquisition'][:10] for m in testing})
        models={}
        for config in CONFIGS:models[config]=fit(fitting,samples,config);print('REFIT_FOLD_FIT',fold,config,flush=True)
        folds.append({'fold':fold,'fit_ids':[m['id'] for m in fitting],'held_ids':[m['id'] for m in testing],'held_dates':sorted({m['initial_acquisition'][:10] for m in testing})})
        for meta in testing:
            case=loop.load(meta);scores={'parent':parent_rows[meta['id']]}
            for name,model in models.items():
                columns=spec['groups'][CONFIGS[name][0]];prob=model.predict_proba(case['X'][:,columns])[:,1].reshape(500,500)
                for threshold in THRESHOLDS:scores[name+'__'+str(threshold)]=dense.metrics(dense.clean(case['eligible']&(prob>=threshold)),case['arrays'])
            rows.append({'id':meta['id'],'fold':fold,'scores':scores});print('REFIT_HELD',meta['id'],flush=True);del case;gc.collect()
        c.write(OUT/'selection-progress.json',{'rows':rows,'folds':folds})
    summary={name:loop.pooled(rows,name) for name in rows[0]['scores']};ranking=sorted(summary,key=lambda name:(-summary[name]['pooled_dice'],summary[name]['predicted_growth_km2'],name))
    selection={'selected':ranking[0],'ranking':ranking,'summary':summary,'rows':rows,'folds':folds,'2026_used_for_hyperparameter_or_threshold_selection':False,
      'validation_comparison_note':'RefitcandidateCVseesother2025dates, parent sees2024only. Moretrainingdataintervention, notanidenticaltrainingbudget/yearholdoutcomparison.'}
    c.write(OUT/'selection.json',selection)
    if ranking[0]!='parent':
        name=ranking[0].rsplit('__',1)[0];model=fit(past,samples,name);joblib.dump(model,OUT/'model.joblib')
    files=['protocol.json','selection.json']+(['model.joblib'] if ranking[0]!='parent' else [])
    c.write(OUT/'frozen-selection.json',{'files':{name:c.sha(OUT/name) for name in files},'final_train_case_ids':[m['id'] for m in past],
      'source_array_content_sha256':{m['id']:c.array_content_sha(c.OUT/'cases'/m['id']/'model-arrays.npz') for m in past}})
    print('REFIT_SELECTED',ranking[0],summary[ranking[0]],flush=True)


def test():
    frozen=c.read(OUT/'frozen-selection.json')
    for name,digest in frozen['files'].items():assert c.sha(OUT/name)==digest
    choice=c.read(OUT/'selection.json');rows=[];forest_rows=[]
    for meta in loop.metas():
        if meta['engineering_split'] not in ('regression2026','test2026_new_cases'):continue
        case=loop.load(meta);mask=predict(meta,case['initial'],choice);score=dense.metrics(mask,case['arrays']);visible=mask&case['arrays']['valid20']&~case['arrays']['initial_scar20']
        folder=c.OUT/'cases'/meta['id'];np.savez_compressed(OUT/(meta['id']+'-prediction.npz'),predicted=mask)
        with np.load(folder/'community-forest-masks.npz') as masks:
            for forest_id in masks.files:
                fm=masks[forest_id];p=int((fm&visible).sum());r=int((fm&case['arrays']['target20']).sum());forest_rows.append({'id':forest_id,'case':meta['id'],'split':meta['engineering_split'],'predicted_pixels':p,'reference_pixels':r})
        rows.append({'id':meta['id'],'split':meta['engineering_split'],'scores':{'selected':score}});print('REFIT_TEST',meta['id'],score['dice'],flush=True);del case;gc.collect()
    summary={split:loop.pooled([r for r in rows if r['split']==split],'selected') for split in sorted({r['split'] for r in rows})}
    community={}
    for split in summary:
        portions=[r for r in forest_rows if r['split']==split];positive=[r for r in portions if r['reference_pixels']>=25]
        community[split]={'portion_periods':len(portions),'positive_periods_ge1ha':len(positive),'warned_positive_periods':sum(r['predicted_pixels']>=25 for r in positive),
          'missed_positive_periods':sum(r['predicted_pixels']<25 for r in positive),'warned_without_reference_ge1ha':sum(r['predicted_pixels']>=25 and r['reference_pixels']<25 for r in portions)}
    c.write(OUT/'test-results.json',{'selected_on_2025_date_cv':choice['selected'],'by_split':summary,'rows':rows,'community':community,'test_status':'Reused2026retrospectiveafterround1. No pristineholdoutclaim.'})
    print('REFIT_FINAL',summary,community,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('selection','test'),required=True);args=parser.parse_args()
    select() if args.phase=='selection' else test()


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
