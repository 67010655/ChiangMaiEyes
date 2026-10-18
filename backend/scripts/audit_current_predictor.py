"""Exercise the deployed predictor, preserving its code and existing inputs.

The historical scenario replay verifies what the manual tool produces. It is
not an as-issued forecast backtest: its old requests use retrospective ERA5
and assumed fuel. Never promote its point-coverage result to system accuracy.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.spread_scenario import Scenario, run_scenario

OUT = ROOT / 'output/current-predictor-audit-20261017'
BASE = 'https://chiangmaieyes.vercel.app'


def save(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def main():
    started = datetime.now(timezone.utc).isoformat()
    season = json.loads((ROOT / 'output/hindcast-2026/summary.json').read_text(encoding='utf8'))
    results = []
    with httpx.Client(timeout=60) as client:
        def request(path, body=None):
            response = client.get(BASE + path) if body is None else client.post(BASE + path, json=body)
            response.raise_for_status()
            return response.json()

        live = request('/api/fire-predictions')
        # Save a real delivered forecast before its future target dates occur.
        capture_name = 'captures/' + started.replace(':', '-') + '.json'
        save(capture_name, {'captured_at_utc': started, 'endpoint': BASE + '/api/fire-predictions',
            'available_at_bound': 'Captured now; provider retrieval timestamp is not model initialization time.',
            'response': live})
        print('Live predictor:', live.get('provider_status'), 'spread outputs:', len(live.get('spread_forecast_72h', [])), flush=True)
        for case in season['cases']:
            chosen = next(s for s in case['scenarios'] if s['factor'] == .2 and s['moisture_pct'] == 8)
            inputs = chosen['request']
            snapshot = request('/api/spread/simulate', inputs)
            local = run_scenario(Scenario.model_validate(inputs))
            assert snapshot['input_sha256'] == local['input_sha256']
            assert snapshot['cases'] == local['cases'], 'Production engine differs from local engine'
            evaluation = request('/api/spread/evaluate-snapshot', {'snapshot': snapshot, 'observations': case['observations']})
            rows = evaluation['observations']
            count = sum(r['nominal_point_inside'] for r in rows)
            result = {'case': case['id'], 'known_start': inputs['start_at'], 'points': len(rows), 'covered': count,
                'model_version': snapshot['model_version'], 'matches_local_engine': True,
                'input_sha256': snapshot['input_sha256'],
                'as_issued_forecast_test': False,
                'reason': 'Original retrospective request: ERA5 wind, assumed FM1 fuel/moisture and flat terrain; not an automatic dashboard forecast.'}
            save('cases/' + case['id'] + '.json', {'request': inputs, 'snapshot': snapshot, 'evaluation': evaluation})
            results.append(result)
            print(case['id'], count, '/', len(rows), 'original scenario replay', flush=True)

    files = ['backend/app/predict.py', 'backend/app/services.py', 'backend/app/fire_phase.py',
             'backend/app/spread_scenario.py', 'frontend/public/spread-workspace.js']
    report = {'schema': 'cme-current-predictor-audit-v1', 'captured_at_utc': started,
        'forecast_capture_file': capture_name,
        'question': 'How accurately does the existing dashboard predict subsequent fire spread and PM2.5?',
        'overall_prediction_accuracy': None,
        'current_primary_endpoint': {'endpoint': '/api/fire-predictions',
            'weather_days': len(live.get('weather_forecast', [])),
            'pm25_province_days': len((live.get('pm25_forecast_province') or {}).get('daily', [])),
            'spread_forecast_count': len(live.get('spread_forecast_72h', [])),
            'provider_status': live.get('provider_status'),
            'fire_weather_pm25_coupled_model_present': False,
            'code_reason': 'services.get_fire_predictions calls build_fire_predictions() without phases; _build_spread_projection always returns None; CAMS is fetched independently.'},
        'historical_forecast_scoreability': {
            'fire': 'No automatic fire-spread output in current primary predictor to score.',
            'pm25': 'Available Jan-Apr CAMS series has no verified forecast issue/lead; cannot score as-issued 1/2/3-day forecasts.',
            'weather': 'Earlier score used explicitly selected GFS; primary endpoint uses automatic provider selection and daily maximum wind, so earlier hourly GFS score is not this endpoint accuracy.'},
        'manual_scenario_replay': {'status': 'production_endpoint_replayed_with_original_inputs',
            'cases': results, 'points': sum(r['points'] for r in results), 'covered': sum(r['covered'] for r in results),
            'accuracy_percent': None, 'meaning': 'Coverage of archived later detections under supplied assumptions only; no independent fire perimeter/negative labels.'},
        'source_sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}
    save('audit.json', report)
    print(json.dumps({'cases': len(results), 'covered': report['manual_scenario_replay']['covered'],
        'points': report['manual_scenario_replay']['points'], 'overall_accuracy': None}), flush=True)


if __name__ == '__main__':
    main()
