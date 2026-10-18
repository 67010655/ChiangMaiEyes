from pathlib import Path
from datetime import datetime,timezone,timedelta
import math
import pytest
import eccodes
from fastapi.testclient import TestClient
from app.main import app
from app.providers.gfs_ventilation import catalog_cycle,decode_subset,model_bbox
DATA=(Path(__file__).parent/'fixtures/gfs_pbl_20261012_06_f000.grib2').read_bytes()
RUN=datetime(2026,10,12,6,tzinfo=timezone.utc)
BBOX='98.0086,17.2732,99.5730,20.1474'

def chunks(data=DATA):
    out=[];position=0
    while position<len(data):
        size=int.from_bytes(data[position+8:position+16],'big')
        out.append(data[position:position+size]);position+=size
    return out

def mutate(key,value):
    parts=chunks();msg=eccodes.codes_new_from_message(parts[0])
    try:
        eccodes.codes_set(msg,key,value);parts[0]=eccodes.codes_get_message(msg)
    finally:eccodes.codes_release(msg)
    return b''.join(parts)

def test_decodes_four_native_fields_and_binds_ncep_local_hpbl_units():
    result=decode_subset(DATA,RUN,0,BBOX)
    assert len(result['cells'])==66 and result['missing_cells']==0
    hpbl=next(m for m in result['field_metadata'] if m['field']=='pbl_height_m')
    assert hpbl['parameterNumber']==196 and hpbl['normalized_unit']=='m'
    assert hpbl['units']=='unknown' and 'grib2_table4-2-0-3' in hpbl['unit_source']
    cell=result['cells'][0]
    assert cell['pbl_height_m']==pytest.approx(708.1994140625)
    assert cell['ventilation_rate_m2_s']==1000 # native VRATE, not a substituted 10-m calculation
    assert cell['wind_pbl_m_s']==pytest.approx(math.hypot(cell['u_pbl_m_s'],cell['v_pbl_m_s']))
    assert (cell['wind_from_deg']+180)%360==pytest.approx(cell['wind_to_deg'])

@pytest.mark.parametrize('data',[b'<html>Error</html>',DATA[:-5],b''.join(chunks()[:3]),DATA+chunks()[0]])
def test_rejects_non_grib_truncated_missing_and_duplicate_products(data):
    with pytest.raises(ValueError):decode_subset(data,RUN,0,BBOX)

def test_rejects_ten_m_wind_instead_of_pbl_wind():
    with pytest.raises(ValueError):decode_subset(mutate('typeOfLevel','heightAboveGround'),RUN,0,BBOX)

def test_rejects_a_different_model_run_origin_or_valid_time():
    with pytest.raises(ValueError):decode_subset(mutate('centre','ecmf'),RUN,0,BBOX)
    with pytest.raises(ValueError):decode_subset(DATA,RUN,24,BBOX)

def test_catalog_must_publish_a_current_cycle_not_an_invented_one():
    html='<input name="dir" value="/gfs.20261012/06/atmos">'
    assert catalog_cycle(html,RUN+timedelta(hours=1))[1]==RUN
    for now in [RUN-timedelta(hours=1),RUN+timedelta(hours=25)]:
        with pytest.raises(ValueError):catalog_cycle(html,now)
    with pytest.raises(ValueError):catalog_cycle('<input name="dir" value="https://other.test">',RUN)

def test_model_bbox_contains_the_edge_grid_centres():
    assert model_bbox()=='98.0000,17.2500,99.7500,20.2500'

def test_endpoint_limits_forecast_leads_and_does_not_fabricate_missing_cells(monkeypatch):
    from app.providers import gfs_ventilation
    monkeypatch.setattr(gfs_ventilation,'ventilation',lambda lead:{'status':'unavailable','cells':[],'reference_cell':None,'lead_hours':lead})
    client=TestClient(app)
    for lead in [0,24,48]:
        response=client.get('/api/ventilation',params={'lead_hours':lead})
        assert response.status_code==200 and response.json()['reference_cell'] is None
        assert 's-maxage=60' in response.headers['cache-control']
    for lead in [-1,1,36,49]:assert client.get('/api/ventilation',params={'lead_hours':lead}).status_code==422
