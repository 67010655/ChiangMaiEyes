from pathlib import Path

import httpx

from app.config import Settings
from app.providers import copernicus_provider as cp


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Records calls and returns a token then a statistics payload by URL."""

    last: "_FakeClient | None" = None

    def __init__(self, *args, **kwargs):
        self.calls: list[dict] = []
        _FakeClient.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if url == cp.CDSE_TOKEN_URL:
            return _FakeResponse({"access_token": "fake-token"})
        return _FakeResponse(
            {
                "status": "OK",
                "data": [
                    {
                        "interval": {"from": "2026-05-09", "to": "2026-06-23"},
                        "outputs": {
                            "data": {
                                "bands": {
                                    "ndvi": {"stats": {"mean": 0.30, "sampleCount": 100, "noDataCount": 0}},
                                    "ndmi": {"stats": {"mean": -0.06, "sampleCount": 100, "noDataCount": 0}},
                                    "nbr": {"stats": {"mean": 0.20, "sampleCount": 100, "noDataCount": 0}},
                                }
                            }
                        },
                    }
                ],
            }
        )


def _settings_with_creds() -> Settings:
    return Settings(
        copernicus_client_id="client-123",
        copernicus_client_secret="secret-xyz",
    )


def test_copernicus_enabled_requires_both_credentials():
    assert cp.copernicus_enabled(_settings_with_creds()) is True
    assert cp.copernicus_enabled(Settings(copernicus_client_id="only-id")) is False
    assert cp.copernicus_enabled(Settings()) is False


def test_build_maps_real_means_into_zones(monkeypatch):
    monkeypatch.setattr(cp.httpx, "Client", _FakeClient)

    layer = cp.build_satellite_layers_from_copernicus(
        _settings_with_creds(), now="2026-06-23T12:00:00+07:00"
    )

    assert layer.source_mode == "LIVE"
    assert "Copernicus" in layer.source
    assert len(layer.dryness_zones) == len(cp.SEED_DRYNESS_ZONES)

    first = layer.dryness_zones[0]
    assert first.ndvi == 0.3
    assert first.ndmi == -0.06
    assert first.nbr == 0.2
    # ndvi 0.30 <= 0.33 -> "high" via shared _dryness_class
    assert first.dryness_class == "high"
    assert "Copernicus Data Space" in first.source

    # Auth used client-credentials; statistics request carried the evalscript,
    # the Sentinel-2 L2A collection, and a real geometry (not a point+radius).
    calls = _FakeClient.last.calls
    token_call = next(c for c in calls if c["url"] == cp.CDSE_TOKEN_URL)
    assert token_call["data"]["grant_type"] == "client_credentials"
    assert token_call["data"]["client_id"] == "client-123"

    stats_call = next(c for c in calls if c["url"] == cp.CDSE_STATISTICS_URL)
    body = stats_call["json"]
    assert body["input"]["data"][0]["type"] == "sentinel-2-l2a"
    assert body["input"]["bounds"]["geometry"]["type"] == "Polygon"
    assert "index(s.B08, s.B04)" in body["aggregation"]["evalscript"]
    assert stats_call["headers"]["Authorization"] == "Bearer fake-token"


def test_extract_means_picks_interval_with_most_samples():
    stats = {
        "data": [
            {"outputs": {"data": {"bands": {"ndvi": {"stats": {"mean": 0.1, "sampleCount": 2, "noDataCount": 1}}}}}},
            {"outputs": {"data": {"bands": {
                "ndvi": {"stats": {"mean": 0.4, "sampleCount": 90, "noDataCount": 0}},
                "ndmi": {"stats": {"mean": 0.0, "sampleCount": 90, "noDataCount": 0}},
                "nbr": {"stats": {"mean": 0.3, "sampleCount": 90, "noDataCount": 0}},
            }}}},
        ]
    }
    means = cp._extract_means(stats)
    assert means["ndvi"] == 0.4


def test_empty_window_keeps_seed_and_flags_source(monkeypatch):
    class _EmptyClient(_FakeClient):
        def post(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            if url == cp.CDSE_TOKEN_URL:
                return _FakeResponse({"access_token": "fake-token"})
            return _FakeResponse({"status": "OK", "data": []})

    monkeypatch.setattr(cp.httpx, "Client", _EmptyClient)
    layer = cp.build_satellite_layers_from_copernicus(_settings_with_creds())
    first = layer.dryness_zones[0]
    assert first.ndvi == cp.SEED_DRYNESS_ZONES[0]["ndvi"]  # fell back to seed
    assert "Seed value" in first.source


def test_load_falls_back_to_seed_without_credentials():
    layer = cp.load_copernicus_or_seed(Settings(), now="2026-06-23T12:00:00+07:00")
    assert layer.source_mode == "DERIVED"  # seeded layer
