import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.providers.community_forest_provider import fetch_community_forests


def test_boundary_shapefile_is_the_only_community_forest_count(monkeypatch):
    monkeypatch.setattr("app.providers.community_forest_provider._fetch_thaicfnet", lambda: [
        {"name": "unmatched", "addresses": [["", "", "", "unmatched district"]]}
    ])
    features = json.loads(Path("app/data/community-forests-chiangmai.geojson").read_text(encoding="utf-8"))["features"]
    forests = fetch_community_forests()

    assert len(features) == len(forests) == 677
    assert all(forest.boundary for forest in forests)


def test_community_forest_api_reports_only_boundary_count(monkeypatch):
    monkeypatch.setattr("app.providers.community_forest_provider._fetch_thaicfnet", lambda: [])
    response = TestClient(app).get("/api/community-forests")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == len(payload["forests"]) == 677
    assert "official_registered_count" not in payload
    assert "official_coordinate_count" not in payload
    assert "supplemental_count" not in payload
