from unittest.mock import MagicMock, patch

from app.providers.osm_structures_provider import fetch_osm_structures


def _overpass_response(elements):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"elements": elements}
    return mock_resp


_BUILDING_WAY = {
    "type": "way",
    "tags": {"building": "yes", "building:levels": "4"},
    "geometry": [
        {"lat": 18.78, "lon": 98.98},
        {"lat": 18.781, "lon": 98.98},
        {"lat": 18.781, "lon": 98.981},
    ],
}
_BUILDING_WAY_NO_LEVELS = {
    "type": "way",
    "tags": {"building": "yes"},
    "geometry": [
        {"lat": 18.79, "lon": 98.99},
        {"lat": 18.791, "lon": 98.99},
        {"lat": 18.791, "lon": 98.991},
    ],
}
_FUEL_NODE = {
    "type": "node",
    "tags": {"amenity": "fuel", "name": "Shell ห้วยแก้ว"},
    "lat": 18.797,
    "lon": 98.973,
}
_FUEL_NODE_NO_NAME = {
    "type": "node",
    "tags": {"amenity": "fuel"},
    "lat": 18.8,
    "lon": 98.97,
}


@patch("httpx.post")
def test_parses_buildings_and_fuel_from_first_mirror(mock_post):
    mock_post.return_value = _overpass_response([_BUILDING_WAY, _FUEL_NODE])
    resp = fetch_osm_structures(18.77, 98.96, 18.81, 99.01)

    assert len(resp.buildings) == 1
    assert resp.buildings[0].height_m == 12.0  # 4 levels * 3m
    assert len(resp.buildings[0].coordinates) == 3
    assert len(resp.fuel_stations) == 1
    assert resp.fuel_stations[0].name == "Shell ห้วยแก้ว"
    mock_post.assert_called_once()  # first mirror succeeded, no fallback needed


@patch("httpx.post")
def test_building_without_levels_uses_default_height(mock_post):
    mock_post.return_value = _overpass_response([_BUILDING_WAY_NO_LEVELS])
    resp = fetch_osm_structures(18.77, 98.96, 18.81, 99.01)
    assert resp.buildings[0].height_m == 8.0


@patch("httpx.post")
def test_fuel_station_without_name_gets_thai_default(mock_post):
    mock_post.return_value = _overpass_response([_FUEL_NODE_NO_NAME])
    resp = fetch_osm_structures(18.77, 98.96, 18.81, 99.01)
    assert resp.fuel_stations[0].name == "ปั๊มน้ำมัน"


@patch("httpx.post")
def test_falls_back_to_second_mirror_when_first_fails(mock_post):
    mock_post.side_effect = [Exception("503 from browser-flagged mirror"), _overpass_response([_FUEL_NODE])]
    resp = fetch_osm_structures(18.77, 98.96, 18.81, 99.01)
    assert len(resp.fuel_stations) == 1
    assert mock_post.call_count == 2


@patch("httpx.post")
def test_both_mirrors_down_degrades_to_empty_not_crash(mock_post):
    mock_post.side_effect = Exception("network down")
    resp = fetch_osm_structures(18.77, 98.96, 18.81, 99.01)
    assert resp.buildings == []
    assert resp.fuel_stations == []


def test_oversized_bbox_rejected_without_calling_overpass():
    with patch("httpx.post") as mock_post:
        resp = fetch_osm_structures(10.0, 90.0, 20.0, 100.0)  # 10x10 degrees, way over the cap
        assert resp.buildings == []
        assert resp.fuel_stations == []
        mock_post.assert_not_called()
