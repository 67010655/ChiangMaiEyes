from unittest.mock import patch

from app.models import CommunityForest
from app.providers.community_forest_provider import _correct_amphoe, fetch_community_forests
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
