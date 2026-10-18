from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import json

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import forest_terrain
from app.main import app


def processor():
    spec=spec_from_file_location('terrain_processor',Path(__file__).resolve().parents[2]/'scripts/build_forest_terrain.py')
    module=module_from_spec(spec);spec.loader.exec_module(module);return module


def test_horn_slope_uses_metres_and_missing_neighbourhoods_not_zero():
    module=processor()
    dem=np.tile(np.arange(9,dtype=np.float32)*30,(9,1))
    slope=module.horn_slope(dem,30)
    assert np.allclose(slope[1:-1,1:-1],45)
    assert np.isnan(slope[0]).all()
    dem[4,4]=np.nan
    assert np.isnan(module.horn_slope(dem)[3:6,3:6]).all()
    assert module.summary(np.array([0,1,np.nan]))['min']==0


def test_copernicus_native_grid_is_not_shifted_at_pixel_is_point_tile_seams():
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin
    module=processor();files=[];datasets=[]
    try:
        # Two adjoining rasters with a half-pixel origin, as in Copernicus.
        for left,values in ((-.5,[0,1,2,3]),(3.5,[4,5,6,7])):
            mem=MemoryFile();files.append(mem)
            ds=mem.open(driver='GTiff',width=4,height=4,count=1,dtype='float32',crs='EPSG:4326',transform=from_origin(left,4.5,1,1))
            ds.write(np.tile(np.array(values,dtype='float32'),(4,1)),1);datasets.append(ds)
        mosaic,transform=module.merge_native(datasets,(2.1,1.2,4.2,3.8))
        assert (transform.c+.5)%1==pytest.approx(0)
        assert (transform.f-.5)%1==pytest.approx(0)
        row=int((transform.f-2)/1);col=int((3-transform.c)/1)
        assert mosaic[0,row,col]==3 and mosaic[0,row,col+1]==4
    finally:
        for ds in datasets:ds.close()
        for mem in files:mem.close()


def test_real_dataset_retains_677_boundaries_and_excludes_the_quarantined_geometry():
    forest_terrain.dataset.cache_clear()
    metadata,rows=forest_terrain.dataset()
    assert len(rows)==677 and metadata['counts']=={'available':676,'boundary_needs_review':1}
    assert metadata['horizontal_crs']=='EPSG:32647' and metadata['slope_unit']=='degree'
    assert rows['cmf-th-3192']['slope_deg'] is None
    assert len(metadata['sources'])==8 and all(s['sha256'] and s['bytes']>0 for s in metadata['sources'])
    assert all(0<=r['slope_deg']['median']<90 for r in rows.values() if r['slope_deg'])
    assert len({r['slope_deg']['median'] for r in rows.values() if r['slope_deg']})>100


def test_public_terrain_reader_and_unknown_forest():
    client=TestClient(app)
    response=client.get('/api/forest-terrain?forest_id=cmf-th-2522')
    assert response.status_code==200 and response.json()['forest']['status']=='available'
    assert 's-maxage=3600' in response.headers['cache-control']
    assert client.get('/api/forest-terrain?forest_id=unknown').status_code==404
    assert client.get('/api/forest-terrain?forest_id=cmf-th-3192').json()['forest']['status']=='boundary_needs_review'


def test_boundary_version_mismatch_fails_closed(tmp_path,monkeypatch):
    data=json.loads(forest_terrain.DATA.read_text(encoding='utf8'));data['boundary_sha256']='0'*64
    artifact=tmp_path/'wrong.json';artifact.write_text(json.dumps(data),encoding='utf8')
    monkeypatch.setattr(forest_terrain,'DATA',artifact);forest_terrain.dataset.cache_clear()
    try:
        with pytest.raises(HTTPException) as error:forest_terrain.dataset()
        assert error.value.status_code==503
    finally:forest_terrain.dataset.cache_clear()
