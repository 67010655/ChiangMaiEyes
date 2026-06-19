import json
from pathlib import Path

from app.config import Settings
from app.providers.earth_engine_provider import load_satellite_layers, refresh_satellite_layers


def test_load_satellite_layers_prefers_existing_export(tmp_path: Path):
    export_path = tmp_path / "satellite_layers.json"
    export_path.write_text(
        json.dumps(
            {
                "source_mode": "LIVE",
                "source": "test export",
                "generated_at": "2026-06-19T10:00:00+07:00",
                "dataset_ids": ["COPERNICUS/S2_SR_HARMONIZED"],
                "cadence": "test",
                "dryness_zones": [
                    {
                        "id": "z1",
                        "name": "Zone 1",
                        "latitude": 18.8,
                        "longitude": 98.9,
                        "radius_m": 1000,
                        "ndvi": 0.3,
                        "ndmi": -0.1,
                        "nbr": 0.2,
                        "dryness_class": "high",
                        "updated_at": "2026-06-19T10:00:00+07:00",
                        "source": "test",
                    }
                ],
                "notes": [],
            }
        ),
        encoding="utf-8",
    )

    layers = load_satellite_layers(Settings(cache_dir=tmp_path, satellite_layers_file=export_path))

    assert layers.source_mode == "LIVE"
    assert layers.source == "test export"
    assert layers.dryness_zones[0].id == "z1"


def test_refresh_satellite_layers_writes_seed_export_without_credentials(tmp_path: Path):
    export_path = tmp_path / "satellite_layers.json"
    settings = Settings(cache_dir=tmp_path, satellite_layers_file=export_path, earth_engine_enabled=False)

    layers = refresh_satellite_layers(settings, now="2026-06-19T10:00:00+07:00")

    assert layers.source_mode == "DERIVED"
    assert "COPERNICUS/S2_SR_HARMONIZED" in layers.dataset_ids
    assert len(layers.dryness_zones) >= 5
    assert export_path.exists()
