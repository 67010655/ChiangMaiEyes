import importlib.util
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('land_reference_builder',ROOT/'scripts/build_land_context_reference.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
STATS=json.loads((ROOT/'backend/app/data/chiangmai-forest-statistics-2000.json').read_text(encoding='utf-8'))


def test_extracted_chiang_mai_values_match_the_source_table_and_use_forest_area_as_denominator():
    assert STATS['total_forest_area_km2']=='16448.5'
    expected={'evergreen':'4908.6','mixed_deciduous':'8355.3','dipterocarp':'2812.7','pine':'179.5'}
    for kind,value in expected.items():
        row=STATS['categories'][kind]
        assert row['area_km2']==value
        percent=Decimal(value)/Decimal('16448.5')*100
        assert abs(Decimal(row['percent'])-percent)<Decimal('.000001')
        assert row['display_percent']==int(percent.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    assert STATS['source_page']==2 and STATS['reference_year']==2000


def test_parser_reads_the_pdf_row_instead_of_using_typed_percentages():
    text='Table 1 Forest Land Assessment by Province in 2000\n'+STATS['source_row']
    parsed=builder.parse_table(text)
    assert parsed['context_text']==STATS['context_text']
    assert parsed['categories']['swamp']['area_km2'] is None
    changed=text.replace('8,355.3','8,355.4').replace('16,448.5','16,448.6')
    assert builder.parse_table(changed)['categories']['mixed_deciduous']['percent']!=STATS['categories']['mixed_deciduous']['percent']


@pytest.mark.parametrize('text',['Table 1 2000\nNo row','Table 1 2000\nเชียงใหม่ 1 2 Chiang Mai','Table 1 2025\n'+STATS['source_row']])
def test_unexpected_pdf_structure_or_year_requires_review(text):
    with pytest.raises(ValueError):builder.parse_table(text)


def test_fuel_measurements_are_converted_not_typed_and_never_describe_the_hotspot():
    measurements,levels=builder.fuel_profiles(STATS)
    assert measurements['dipterocarp_doisuthep']['t_rai']=='0.83'
    assert measurements['mixed_deciduous_nan']['t_rai']=='0.57'
    assert set(levels)=={'dipterocarp','mixed_deciduous','deciduous','unknown_forest','crop'}
    for level in levels.values():
        assert level['status']=='measured_reference' and builder.NOT_AT_POINT in level['text']
        assert all(mid in measurements for mid in level['measurements'])
    assert '68%' in levels['unknown_forest']['text'] and 'ป่าดิบยังไม่มีค่าวัด' in levels['unknown_forest']['text']
    assert 'นาข้าวพื้นราบยังไม่มีค่าวัด' in levels['crop']['text']
