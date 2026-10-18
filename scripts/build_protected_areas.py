"""Offline build of reference protected-area boundaries; no WFS calls at runtime.

Use scripts/requirements-terrain.txt. Keep whole intersecting features so that
the provincial border does not become an artificial protected-area edge.
"""
from __future__ import annotations
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

import httpx
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely import transform as transform_geometry
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'https://data.thailand.opendevelopmentmekong.net/en/dataset/thailand-protected-areas'
CATALOG_API = 'https://data.thailand.opendevelopmentmekong.net/api/3/action/package_show?id=thailand-protected-areas'
WFS = 'https://data.opendevelopmentmekong.net/geoserver/ODMekong/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=ODMekong%3AL10_ProtectedArea_MNRE_50k&outputFormat=application%2Fjson'
ORIGIN = 'https://gistdaportal.gistda.or.th/portal/home/item.html?id=299b03fb814a49749cbedaca213a759b'
DNP_NAMES = 'https://portal.dnp.go.th/DNP/FileSystem/download?uuid=8b378236-7cbe-4f50-81e4-c51d6f0115c4.pdf'
TYPE_CHECKS = {
    '1': {'kind':'national_park', 'label':'อุทยานแห่งชาติ', 'anchors':['ดอยสุเทพ-ปุย','ดอยอินทนนท์'], 'source':DNP_NAMES, 'page':1},
    '2': {'kind':'wildlife_sanctuary', 'label':'เขตรักษาพันธุ์สัตว์ป่า', 'anchors':['เชียงดาว','อมก๋อย'], 'source':DNP_NAMES, 'page':1},
    '3': {'kind':'non_hunting_area', 'label':'เขตห้ามล่าสัตว์ป่า', 'anchors':['ดอยสุเทพ','แม่เลา-แม่แสะ'], 'source':DNP_NAMES, 'page':1},
    '4': {'kind':'forest_park', 'label':'วนอุทยาน', 'anchors':['น้ำตกบัวตอง-น้ำพุเจ็ดสี'],
          'source':'https://www.thailandtourismdirectory.go.th/th/attraction/3378'},
}
DISCLAIMER = 'ขอบเขตจาก GISTDA 2017 ใช้อ้างอิง ไม่ใช่แนวเขตทางกฎหมาย'


def transform(fn, geometry):
    return transform_geometry(geometry,fn,interleaved=False)


def vertex_count(geometry):
    if geometry.geom_type == 'Polygon':
        return len(geometry.exterior.coords) + sum(len(r.coords) for r in geometry.interiors)
    return sum(vertex_count(g) for g in geometry.geoms)


def crosschecked_types(features):
    # This is a name-based cross-check, not an official pro_id dictionary.
    # A missing/changed anchor disables that prefix instead of guessing a type.
    return {prefix:check for prefix,check in TYPE_CHECKS.items() if all(
        any(str(f['properties'].get('pro_id','')).startswith(prefix) and f['properties'].get('name_th') == name for f in features)
        for name in check['anchors'])}


def rounded(value, digits=6):
    return [rounded(v,digits) for v in value] if isinstance(value,(tuple,list)) else round(value,digits)


def build(source, province, *, tolerance_m=20):
    crs_name = source.get('crs',{}).get('properties',{}).get('name')
    if not crs_name or CRS.from_user_input(crs_name).to_epsg() != 3857:
        raise ValueError('Expected explicit EPSG:3857 WFS coordinates; review upstream CRS')
    if province['type']=='FeatureCollection':
        province_shape=unary_union([shape(f['geometry']) for f in province['features']])
    else:
        province_shape=shape(province['geometry'] if province['type']=='Feature' else province)
    if not province_shape.is_valid:
        raise ValueError('Invalid province boundary')
    to_wgs=Transformer.from_crs(3857,4326,always_xy=True).transform
    to_metric=Transformer.from_crs(4326,32647,always_xy=True).transform
    from_metric=Transformer.from_crs(32647,4326,always_xy=True).transform
    types=crosschecked_types(source['features'])
    result=[]; audits=[]
    for feature in source['features']:
        g=transform(to_wgs,shape(feature['geometry']))
        if not g.intersects(province_shape):
            continue
        if g.geom_type not in ('Polygon','MultiPolygon') or not g.is_valid:
            raise ValueError('Selected boundary needs explicit review, not silent geometry repair')
        props=feature['properties']; key=str(props.get('pro_id') or feature['id'])
        metric=transform(to_metric,g)
        for factor in (1,.5,.25,.125,0):
            simple=metric.simplify(tolerance_m*factor,preserve_topology=True)
            output=mapping(transform(from_metric,simple))
            output['coordinates']=rounded(output['coordinates'])
            rendered=shape(output)
            if not rendered.is_valid or rendered.is_empty:
                raise ValueError(f'Coordinate rounding damaged boundary {key}')
            error=metric.hausdorff_distance(transform(to_metric,rendered))
            if error<=tolerance_m+.3:
                break
        else:
            raise ValueError(f'Simplification exceeded error budget: {key} {error}')
        kind=types.get(key[:1])
        name=str(props.get('name_th') or props.get('name_en') or 'ไม่ทราบชื่อ')
        result.append({'type':'Feature','id':key,'bbox':list(rendered.bounds),'properties':{
            'pro_id':key, 'name_th':name, 'name_en':props.get('name_en'), 'pro_type':props.get('pro_type'),
            'area_type':kind['kind'] if kind else 'protected_area',
            'area_type_label':kind['label'] if kind else 'พื้นที่อนุรักษ์',
            'type_method':'name_crosschecked_prefix_2017' if kind else 'unconfirmed',
            'type_source':kind['source'] if kind else None, 'mod_date':props.get('mod_date'),
        },'geometry':output})
        audits.append({'pro_id':key,'source_vertices':vertex_count(g),'web_vertices':vertex_count(rendered),
                       'max_geometry_difference_m':round(error,3),'effective_tolerance_m':tolerance_m*factor})
    result.sort(key=lambda f:f['id'])
    if len({f['id'] for f in result}) != len(result):
        raise ValueError('Duplicate protected-area identifier; review before merging features')
    return result,audits,types


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,help='Cached unmodified WFS GeoJSON')
    parser.add_argument('--catalog',type=Path,help='Cached CKAN package_show response')
    parser.add_argument('--checked-on',default=date.today().isoformat())
    args=parser.parse_args()
    catalog_raw=args.catalog.read_bytes() if args.catalog else httpx.get(CATALOG_API,timeout=45,follow_redirects=True).raise_for_status().content
    catalog=json.loads(catalog_raw)['result']
    if catalog['license_id']!='other-open':
        raise ValueError('Publisher license changed; review before reuse')
    reference_date=catalog.get('CI_Citation_date')
    if reference_date!='2017-06-12':
        raise ValueError('Reference date changed; review boundary year and historical type mapping')
    raw=args.source.read_bytes() if args.source else httpx.get(WFS,timeout=180,follow_redirects=True).raise_for_status().content
    province_path=ROOT/'frontend/public/chiangmai-province.json'
    features,audit,types=build(json.loads(raw),json.loads(province_path.read_text(encoding='utf-8')))
    doc={'type':'FeatureCollection','metadata':{
        'title':'Thailand Protected Areas: features intersecting Chiang Mai',
        'reference_date':reference_date,'checked_on':args.checked_on,'source':CATALOG,'origin':ORIGIN,'download':WFS,
        'license':catalog['license_title'],'license_id':catalog['license_id'],'copyright':True,
        'license_note':'Publisher labels this open government data as Other (Open). Preserve attribution; no claim that this is CC0 or that the site footer relicenses the source.',
        'source_crs':'EPSG:3857','output_crs':'EPSG:4326','simplification_crs':'EPSG:32647','simplification_tolerance_m':20,
        'source_sha256':hashlib.sha256(raw).hexdigest(),'province_sha256':hashlib.sha256(province_path.read_bytes()).hexdigest(),
        'source_feature_count':len(json.loads(raw)['features']),'feature_count':len(features),
        'selection':'Whole features intersecting Chiang Mai; not clipped at province borders, to preserve real nearest-edge distances.',
        'type_policy':'Prefix cross-checked against named official examples; not a published code dictionary. Historical 2017 categories; unconfirmed prefixes stay generic.',
        'type_checks':types,'geometry_audit':audit,'disclaimer':DISCLAIMER,
        'coverage_note':'Historical snapshot may omit later additions or changes; no match does not establish that a point is outside every protected area.',
        'contact':{'phone':'1362','label':'สายด่วนกรมอุทยานฯ','source':'https://portal.dnp.go.th/','checked_on':args.checked_on},
    },'features':features}
    dest=ROOT/'frontend/public/protected-areas-chiangmai.geojson'
    dest.write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8',newline='\n')
    print(f'Wrote {len(features)} features, {dest.stat().st_size} bytes; vertices {sum(a["source_vertices"] for a in audit)} -> {sum(a["web_vertices"] for a in audit)}')


if __name__=='__main__':
    main()
