import math
import pytest
from app import grid_spread as grid

def fixture(monkeypatch,wall=False,nodata=False):
    step=math.degrees(100/6371008.8);width=height=101
    meta={'west':-50.5*step,'north':50.5*step,'step_degrees':step,'width':width,'height':height,'nodata':-32768}
    elevations=[100]*(width*height);landcover=bytearray([30])*(width*height)
    if wall:
        for row in range(height):landcover[row*width+51]=80
    if nodata:
        for row in range(height):elevations[row*width+51]=-32768
    monkeypatch.setattr(grid,'terrain_dataset',lambda:(meta,elevations))
    monkeypatch.setattr(grid,'landcover_dataset',lambda:({'blocked_classes':[0,50,60,70,80]},landcover))
    point={'latitude':0,'longitude':0,'detected_at':'2026-01-01T00:00:00Z'}
    steps=[{'from_minute':h*60,'to_minute':(h+1)*60,'wind_10m_mps':0,'wind_from_deg':0} for h in range(6)]
    return [{'point':point,'steps':steps}]

def test_hourly_edge_travel_integrates_wind_changes():
    assert grid.travel(50,30,[60,120],[1,2],120)==70
    assert grid.travel(50,30,[60,120],[0,2],120)==75
    assert grid.travel(60,30,[60,120],[1,2],120)==75
    assert math.isinf(grid.travel(119,30,[60,120],[1,2],120))

def test_water_barrier_blocks_crossing_and_corner_cutting(monkeypatch):
    inputs=fixture(monkeypatch,wall=True)
    masked=grid.run(inputs,as_of='2026-01-01T00:00:00Z')
    unmasked=grid.run(inputs,as_of='2026-01-01T00:00:00Z',use_landcover=False)
    assert all(col<51 for row,col in masked['arrival'])
    assert any(col>=51 for row,col in unmasked['arrival'])

def test_missing_terrain_never_becomes_flat_walkable_land(monkeypatch):
    inputs=fixture(monkeypatch,nodata=True)
    result=grid.run(inputs,as_of='2026-01-01T00:00:00Z',use_landcover=False)
    assert all(col<51 for row,col in result['arrival'])

def test_arrival_symmetry_on_flat_calm_grid_and_budget(monkeypatch):
    inputs=fixture(monkeypatch)
    result=grid.run(inputs,as_of='2026-01-01T00:00:00Z')
    assert result['arrival'][(50,49)]==pytest.approx(result['arrival'][(50,51)])
    limited=grid.run(inputs,as_of='2026-01-01T00:00:00Z',max_cells=1)
    assert limited['truncated'] and limited['processed_cells']==1

def test_rectangles_preserve_concavity_without_filling_holes():
    meta={'west':0,'north':2,'step_degrees':1}
    result=grid.rectangles([(0,0),(0,1),(1,0)],meta)
    area=0
    for feature in result['features']:
        ring=feature['geometry']['coordinates'][0]
        area+=(max(p[0] for p in ring)-min(p[0] for p in ring))*(max(p[1] for p in ring)-min(p[1] for p in ring))
    assert area==3
