"""Bounded second-family comparison, identical frozen3-input features and split."""
import hashlib,json,warnings
from pathlib import Path
import joblib,numpy as np
from lightgbm import LGBMClassifier
import joint_fire_experiment as j

ROOTOUT=j.OUT;OUT=ROOTOUT/'lightgbm-comparison';OUT.mkdir(parents=True,exist_ok=True)
CONFIGS={'compact':{'n_estimators':100,'num_leaves':15},'medium':{'n_estimators':150,'num_leaves':31},'wide':{'n_estimators':200,'num_leaves':63}}
warnings.filterwarnings('ignore',message='X does not have valid feature names.*')
def main():
    protocol={'family':'LightGBM4.6.0','train':2024,'selection_year':2025,'test':2026,'configs':CONFIGS,
      'features':'Identical53features from joint-input-ablation-v1, all3input groups; identical training rows, common evaluation dates and area budgets.',
      'selection':'Highest2025pooled coverage at250km2, including frozen HGB primary as competing option; save before scoring2026.',
      'production_changed':False}
    j.write(OUT/'protocol.json',protocol)
    grid=j.build_grid();saved=np.load(ROOTOUT/'training2024.npz');X,y=saved['X'],saved['y'];models={}
    for label,config in CONFIGS.items():
        name='hotspot_wind_pm__lgb_'+label;path=OUT/(name+'.joblib')
        if path.exists():model=joblib.load(path)
        else:
            model=LGBMClassifier(**config,learning_rate=.05,max_depth=-1,min_child_samples=30,reg_lambda=10,
              random_state=20261017,n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True)
            model.fit(X,y);joblib.dump(model,path)
        models[name]=model;print('fit',name,flush=True)
    # Cache source arrays before redirecting output paths to this experiment.
    j.load(2025,grid);j.load(2026,grid);j.OUT=OUT
    validation=j.evaluate(2025,grid,models);s=validation['summary']
    best=max(models,key=lambda n:s['scores'][n]['250.0']['hits'])
    hgb_selection=j.read(ROOTOUT/'selection.json');hgb_name=hgb_selection['selected_primary'];hgb_val=j.read(ROOTOUT/'results-2025.json')['summary']
    assert hgb_val['target_cells']==s['target_cells'] and hgb_val['issues']==s['issues']
    overall=best if s['scores'][best]['250.0']['hits']>hgb_val['scores'][hgb_name]['250.0']['hits'] else hgb_name
    selection={'best_lightgbm':best,'best_hgb':hgb_name,'selected_overall_on2025':overall,'lightgbm_hits2025':s['scores'][best]['250.0']['hits'],
      'hgb_hits2025':hgb_val['scores'][hgb_name]['250.0']['hits'],'selection_year':2025}
    j.write(OUT/'selection.json',selection);print('FAMILY SELECTION',json.dumps(selection),flush=True)
    test=j.evaluate(2026,grid,{best:models[best]})
    report={'protocol':protocol,'selection':selection,'validation':s,'test':test['summary'],
      'gain_pp_vs_previous_95pct':j.uncertainties(test['rows'],list(test['summary']['scores'])),'production_changed':False}
    j.write(OUT/'summary.json',report);print('LIGHTGBM RESULT',json.dumps(report),flush=True)
if __name__=='__main__':main()
