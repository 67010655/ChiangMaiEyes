import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/spread-optimization-20261017'
def read(path):return json.loads(path.read_text(encoding='utf8'))
fire=read(OUT/'quality-filtered/summary.json');pm=read(OUT/'pm-optimization.json');wind=read(OUT/'wind-optimization.json')
def interval(rows):
    values=np.array([r['gain'] for r in rows if r['status']=='scored']);rng=np.random.default_rng(20261017)
    return np.percentile([np.mean(rng.choice(values,len(values),replace=True)) for _ in range(2000)],[2.5,97.5]).tolist()
report={'schema':'cme-optimization-v1','fire':{'protocol':fire['protocol'],'selection':fire['selection'],
    'test_selected':fire['test_selected'],'test_current':fire['test_current'],
    'selected_gain_interval':interval(fire['test_selected_rows']),'current_gain_interval':interval(fire['test_current_rows']),
    'decision':'retain_current_experimental_parameters_no_validated_directional_skill'},
    'pm':{'by_lead':{h:{k:v for k,v in block.items() if k!='rows'} for h,block in pm['by_lead'].items()},'limits':pm['limits'],
          'decision':'experimental_station_only_forecast_separate_from_CAMS'},
    'wind':wind,'limits':['Point coverage, not burn perimeter accuracy. Equal-area comparison is a shape diagnostic, not an independently issued forecast.',
                         'Fixed daily 02:00 ICT and past-only centre selection. Low-confidence detections excluded. Cases without follow-up cannot establish absence of fire.',
                         'Previous-day GFS archive and acquisition-time availability proxy. Selected peak dates were previously inspected.',
                         'Best among these declared candidates and available observations; no claim of global optimum.']}
(ROOT/'backend/app/data/prediction-optimization.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
(OUT/'published-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'selected_gain_interval':report['fire']['selected_gain_interval'],'current_gain_interval':report['fire']['current_gain_interval']}))
