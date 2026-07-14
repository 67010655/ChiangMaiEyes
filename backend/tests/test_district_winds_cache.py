from unittest.mock import MagicMock, patch

import pytest

from app import services


@pytest.fixture(autouse=True)
def _clear_district_winds_cache():
    """_fetch_district_winds caches under the fixed key "district_winds" in
    the module-level _cache dict — clear it so tests don't leak into each
    other or into other test files that happen to run in the same process."""
    services._cache.pop("district_winds", None)
    yield
    services._cache.pop("district_winds", None)


def _mock_response(wind_speed=10.0, wind_dir=180.0):
    resp = MagicMock()
    resp.json.return_value = {"current": {"wind_speed_10m": wind_speed, "wind_direction_10m": wind_dir}}
    resp.raise_for_status.return_value = None
    return resp


@patch("httpx.get")
def test_fetches_wind_for_every_centroid(mock_get):
    mock_get.return_value = _mock_response()
    centroids = {"เมืองเชียงใหม่": (18.79, 98.99), "แม่ริม": (18.9, 98.9)}

    result = services._fetch_district_winds(centroids)

    assert result == {"เมืองเชียงใหม่": (10.0, 180.0), "แม่ริม": (10.0, 180.0)}
    assert mock_get.call_count == 2


@patch("httpx.get")
def test_second_call_within_ttl_is_served_from_cache_not_refetched(mock_get):
    # This is the actual regression: before caching, every call to
    # /api/fire-phases or /api/dashboard re-fetched all 25 districts fresh
    # from Open-Meteo, which is what caused the production 504 timeouts
    # (confirmed live 2026-07-14 via curl — see the comment in services.py).
    mock_get.return_value = _mock_response()
    centroids = {"เมืองเชียงใหม่": (18.79, 98.99)}

    first = services._fetch_district_winds(centroids)
    second = services._fetch_district_winds(centroids)

    assert first == second
    assert mock_get.call_count == 1  # only the first call actually hit the network


@patch("httpx.get")
def test_failed_district_is_silently_skipped_not_cached_as_error(mock_get):
    mock_get.side_effect = Exception("network down")
    centroids = {"เมืองเชียงใหม่": (18.79, 98.99)}

    result = services._fetch_district_winds(centroids)

    assert result == {}
