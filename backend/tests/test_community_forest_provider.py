from unittest.mock import patch

from app.models import CommunityForest
from app.providers.community_forest_provider import (
    _correct_amphoe,
    _official_forests,
    fetch_community_forests,
)
from app.providers.hotspot_provider import estimate_district


def _forest(name="ป่าทดสอบ", amphoe="กัลยาณิวัฒนา", lat=18.376, lon=98.607, **overrides):
    # Default coordinates are real จอมทอง (Chom Thong) coordinates — used with
    # a deliberately wrong amphoe to test correction.
    defaults = dict(
        forest_id="test-1", name=name, village="", tambon="", amphoe=amphoe,
        latitude=lat, longitude=lon,
    )
    defaults.update(overrides)
    return CommunityForest(**defaults)


def test_correct_amphoe_fixes_a_real_mismatch():
    f = _forest(amphoe="กัลยาณิวัฒนา", lat=18.376, lon=98.607)  # real จอมทอง coords
    assert estimate_district(f.latitude, f.longitude) == "จอมทอง"
    fixed = _correct_amphoe([f])
    assert fixed[0].amphoe == "จอมทอง"


def test_correct_amphoe_leaves_a_correct_label_unchanged():
    f = _forest(amphoe="จอมทอง", lat=18.376, lon=98.607)
    fixed = _correct_amphoe([f])
    assert fixed[0].amphoe == "จอมทอง"
    # Every other field must survive untouched too.
    assert fixed[0].forest_id == f.forest_id
    assert fixed[0].latitude == f.latitude


@patch("app.providers.community_forest_provider._fetch_thaicfnet")
def test_fetch_community_forests_every_amphoe_matches_its_real_polygon(mock_thaicfnet):
    # Real production bug caught this session: 14/675 official records had
    # an amphoe label that didn't match the real district polygon actually
    # containing their coordinates. No thaicfnet network call in a unit test.
    mock_thaicfnet.return_value = []
    forests = fetch_community_forests()
    assert len(forests) > 0
    mismatches = [f for f in forests if estimate_district(f.latitude, f.longitude) != f.amphoe]
    assert mismatches == [], f"{len(mismatches)} forests still mismatched: {mismatches[:5]}"


@patch("app.providers.community_forest_provider._fetch_thaicfnet")
def test_forest_count_is_locked_to_the_agency_shapefile_regardless_of_thaicfnet(mock_thaicfnet):
    # User explicitly asked that every part of the app reference the agency
    # shapefile's real count (677 Chiang Mai polygons) — thaicfnet must never
    # add extra entries on top of it, even when it returns records that
    # don't match anything official.
    mock_thaicfnet.return_value = [
        {"name": "ป่าที่ไม่มีในชุดทางการ", "addresses": [["", "หมู่บ้านผี", "ตำบลผี", "อำเภอผี"]]},
    ]
    forests = fetch_community_forests()
    assert len(forests) == len(_official_forests)


@patch("app.providers.community_forest_provider._fetch_thaicfnet")
def test_matching_thaicfnet_record_enriches_fire_activity_without_adding_a_row(mock_thaicfnet):
    target = _official_forests[0]
    mock_thaicfnet.return_value = [{
        "name": target.name,
        "addresses": [["", target.village, target.tambon, target.amphoe]],
        "fireManagementCheck": ["yes"],
        "fireManagementActivityCheck": ["ทำแนวกันไฟ"],
    }]
    forests = fetch_community_forests()
    assert len(forests) == len(_official_forests)
    matched = next(f for f in forests if f.forest_id == target.forest_id)
    assert matched.fire_management_active is True
    assert matched.fire_activities == ["ทำแนวกันไฟ"]


def test_official_forests_carry_a_real_polygon_boundary():
    assert len(_official_forests) > 0
    with_boundary = [f for f in _official_forests if f.boundary]
    assert len(with_boundary) == len(_official_forests)
    sample = with_boundary[0].boundary
    assert sample["type"] in ("Polygon", "MultiPolygon")
    assert len(sample["coordinates"]) > 0
