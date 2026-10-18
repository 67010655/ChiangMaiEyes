"""Check deployed inference against every paired optimization test prediction."""
import csv,json,sys
from pathlib import Path
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app.pm25_station_forecast import artifact,features,predict
report=json.loads((ROOT/'output/spread-optimization-20261017/pm-optimization.json').read_text(encoding='utf8'))
maximum=0.;count=0
for spec in artifact()['models']:
    station=spec['station'];lead=spec['lead_hours']
    source=ROOT/'output/decision-validation-20261017/pm25'/f'chiangmai-air4thai-{station.lower()}-hourly-20260917-20261016.csv'
    series={datetime.fromisoformat(r['datetime_as_published']):float(r['pm25_ug_m3']) for r in csv.DictReader(source.open(encoding='utf-8-sig')) if r['pm25_ug_m3']}
    actual=[]
    for origin in sorted(series):
        if not datetime(2026,10,1)<=origin<datetime(2026,10,16) or origin+timedelta(hours=lead) not in series:continue
        try:x=features(series,origin,lead)
        except ValueError:continue
        actual.append(predict(spec['model'],x))
    expected=[r['selected'] for r in report['by_lead'][str(lead)]['rows'] if r['station']==station]
    assert len(actual)==len(expected)
    maximum=max(maximum,max(abs(a-b) for a,b in zip(actual,expected)));count+=len(actual)
assert maximum<1e-10
print(json.dumps({'matched_test_predictions':count,'maximum_absolute_difference':maximum}))
