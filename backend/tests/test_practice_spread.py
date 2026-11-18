from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import live_spread
from app.live_spread import router


def test_practice_point_uses_the_live_model_and_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(live_spread, '_practice_cache', {})
    monkeypatch.setattr(live_spread, '_practice_runs', [])
    def weather(points):
        calls.append(points)
        return {}
    monkeypatch.setattr(live_spread, 'fetch_weather', weather)
    built = []
    monkeypatch.setattr(live_spread, 'build', lambda points, w, **kw: built.append((points, kw)) or {'used_points': 1, 'frames': [], 'inputs': []})
    app = FastAPI(); app.include_router(router); c = TestClient(app)
    r1 = c.get('/api/spread/practice', params={'lat': 18.31067, 'lon': 98.33598})
    r2 = c.get('/api/spread/practice', params={'lat': 18.31071, 'lon': 98.33601})  # same ~100 m cell
    assert r1.status_code == r2.status_code == 200 and r1.json()['practice'] is True
    assert len(calls) == 1 and built[0][0][0]['latitude'] == 18.311 and built[0][1]['source_mode'] == 'practice_point'
    assert c.get('/api/spread/practice', params={'lat': 13.7, 'lon': 100.5}).status_code == 422


def test_practice_runs_are_capped(monkeypatch):
    monkeypatch.setattr(live_spread, '_practice_cache', {})
    monkeypatch.setattr(live_spread, '_practice_runs', [])
    monkeypatch.setattr(live_spread, 'fetch_weather', lambda points: {})
    monkeypatch.setattr(live_spread, 'build', lambda points, w, **kw: {'used_points': 1})
    monkeypatch.setattr(live_spread, 'PRACTICE_RUNS_PER_10_MIN', 2)
    app = FastAPI(); app.include_router(router); c = TestClient(app)
    codes = [c.get('/api/spread/practice', params={'lat': 18 + i / 100, 'lon': 98.5}).status_code for i in range(3)]
    assert codes == [200, 200, 429]
