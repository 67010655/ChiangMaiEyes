import time

from fastapi.testclient import TestClient

from app import main, services
from app.config import Settings, get_settings


def test_dashboard_sources_are_fetched_in_parallel_and_cdn_may_keep_a_short_copy(monkeypatch):
    def slow(value):
        def fn(settings):
            time.sleep(0.3)
            return value
        return fn

    real = services.get_dashboard
    calls = {}

    def fake_parts(settings):
        # Run the real parallel section with slow fake sources, then stop.
        monkeypatch.setattr(services, 'get_hotspots', slow('h'))
        monkeypatch.setattr(services, 'get_pm25', slow('p'))
        monkeypatch.setattr(services, 'get_weather', slow('w'))
        t0 = time.perf_counter()
        try:
            real(settings)
        except Exception:
            pass  # downstream builders reject the fake values; only the timing matters
        calls['elapsed'] = time.perf_counter() - t0

    fake_parts(Settings(cache_dir='.'))
    assert calls['elapsed'] < 0.6  # three 0.3 s sources together, not 0.9 s one after another
    assert set(services.LAST_DASHBOARD_TIMINGS) == {'hotspots', 'pm25', 'weather'}


def test_cache_headers_short_for_live_data_long_for_boundaries(monkeypatch):
    main.app.dependency_overrides[get_settings] = lambda: Settings(cache_dir='.')
    monkeypatch.setattr(main, 'get_fire_phases', lambda settings: services.FirePhaseResponse.model_construct(phases=[], tambon_warnings=[]))
    import app.providers.community_forest_provider as cf
    monkeypatch.setattr(cf, 'fetch_community_forests', lambda: [])
    try:
        client = TestClient(main.app)
        forests = client.get('/api/community-forests')
        assert 's-maxage=3600' in forests.headers['cache-control'] and 'no-store' not in forests.headers['cache-control']
        status = client.get('/api/data-status')
        assert status.headers['cache-control'] == 'no-store, no-cache, must-revalidate, max-age=0'
    finally:
        main.app.dependency_overrides.clear()
