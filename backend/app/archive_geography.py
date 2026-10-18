"""Attach a derived spatial assignment without overwriting the source payload."""
import json
from pathlib import Path
from functools import lru_cache
from app.community_mail import point_in_boundary


@lru_cache(maxsize=1)
def admin_index():
    doc=json.loads((Path(__file__).parent/'data/chiangmai-tambons.geojson').read_text(encoding='utf-8'))
    index=[]
    for f in doc['features']:
        geom=f['geometry'];coords=geom.get('coordinates',[])
        rings=[coords[0]] if geom['type']=='Polygon' and coords else [p[0] for p in coords if p]
        points=[p for r in rings for p in r]
        if points:index.append((f['properties'],geom,min(p[1] for p in points),max(p[1] for p in points),min(p[0] for p in points),max(p[0] for p in points)))
    return index


def assign(lat,lon):
    matches=[p for p,g,s,n,w,e in admin_index() if s<=lat<=n and w<=lon<=e and point_in_boundary(lat,lon,g)]
    if len(matches)!=1:return {'status':'ambiguous' if matches else 'unmatched','method':'boundary_intersection'}
    p=matches[0]
    return {'status':'matched','method':'boundary_intersection','district':p['amphoe_th'],'subdistrict':p['tambon_th'],
            'district_code':p['acode'],'subdistrict_code':p['tcode'],'source':'7 Tambon area shapefile · 204 Chiang Mai polygons'}
