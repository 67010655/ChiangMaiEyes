"""Extract the Chiang Mai row from RFD Table 1 (2000), calculate shares, sync UI.

Offline build dependencies: scripts/requirements-reference.txt. The PDF is not
queried by the running website, and provincial shares never classify a point.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

import httpx

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'backend/app/data'
SOURCE='https://data.forest.go.th/dataset/231795fd-9355-47d1-bb6e-512054eec9ca/resource/70cedf55-68d7-4edf-884c-b13b15d17713/download/rfd-stat2545il.pdf'
COLUMNS=[('evergreen','ดงดิบ'),('mixed_deciduous','เบญจพรรณ'),('dipterocarp','เต็งรัง'),
         ('swamp','พรุ'),('beach','ชายหาด'),('pine','สน'),('bamboo','ไผ่'),('mangrove','ชายเลน'),('other','อื่น ๆ')]


def parse_table(text):
    if not re.search(r'Table\s+1\b',text) or '2000' not in text:
        raise ValueError('Expected RFD Table 1, reference year 2000')
    rows=[line for line in text.splitlines() if re.search(r'\bChiang\s+Mai\s*$',line)]
    if len(rows)!=1:
        raise ValueError('Expected exactly one Chiang Mai row on PDF page 2')
    row=' '.join(rows[0].split())
    values=re.findall(r'(?<!\S)(?:\d[\d,]*(?:\.\d+)?|-)(?!\S)',row)
    if len(values)!=13:
        raise ValueError('Unexpected RFD table columns; review extraction before updating')
    number=lambda value:None if value=='-' else Decimal(value.replace(',',''))
    total=number(values[10])
    if total is None or total<=0:
        raise ValueError('Missing total forest area')
    categories={}
    for (kind,label),value in zip(COLUMNS,values[1:10]):
        area=number(value);percent=area/total*100 if area is not None else None
        categories[kind]={'label':label,'source_value':value,'area_km2':str(area) if area is not None else None,
            'percent':str(percent.quantize(Decimal('.000001'))) if percent is not None else None,
            'display_percent':int(percent.quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if percent is not None else None}
    summed=sum(Decimal(c['area_km2']) for c in categories.values() if c['area_km2'] is not None)
    if abs(summed-total)>Decimal('.15'):
        raise ValueError('Forest category totals do not reconcile within source rounding')
    for kind in ('mixed_deciduous','dipterocarp','evergreen'):
        if categories[kind]['area_km2'] is None:
            raise ValueError('Missing category needed for provincial context')
    deciduous=(Decimal(categories['mixed_deciduous']['area_km2'])+Decimal(categories['dipterocarp']['area_km2']))/total*100
    c=categories
    prefix='ป่าในเชียงใหม่ส่วนใหญ่เป็นป่าผลัดใบ' if deciduous>50 else 'สัดส่วนชนิดป่าในเชียงใหม่'
    context=f"ตามสถิติปี 2543 {prefix} (เบญจพรรณราว {c['mixed_deciduous']['display_percent']}%, เต็งรังราว {c['dipterocarp']['display_percent']}%, ดงดิบราว {c['evergreen']['display_percent']}% · กรมป่าไม้ 2543) — จุดนี้ยังระบุชนิดป่าไม่ได้"
    return {'source_row':row,'total_forest_area_km2':str(total),'province_area_km2':str(number(values[0])),
        'categories':categories,'deciduous_percent':str(deciduous.quantize(Decimal('.000001'))),'context_text':context,
        'formula':'category area / total forest area * 100; display rounded to whole percent, Decimal ROUND_HALF_UP',
        'scope':'Province-wide historical composition, not a probability, present-day inventory or point-level forest classification. Source dashes remain null, not measured zeros.'}


# Published field measurements of pre-burn fuel load. Values are copied from the
# cited abstract/table (t/ha, oven-dry where the source says so); t/rai is derived
# here (1 ha = 6.25 rai). They describe the measured site, never a hotspot.
HA_PER_RAI = Decimal('6.25')
FUEL_SOURCES = {
    'akkhaak_1992': {'title': 'ศิริ อัคคะอัคร และสนิท กิตติสัทโธ (2535) Fuel characteristics in dry dipterocarp forest at Doi Suthep-Pui National Park · กรมป่าไม้',
                     'url': 'https://agris.fao.org/search/en/records/64722bc9f762bd4124ec948e',
                     'note': '780 แปลง 1×1 ม. พ.ย. 2534–พ.ค. 2535; ค่าในบทคัดย่อ'},
    'wanthongchai_2021': {'title': 'Wanthongchai และคณะ (2021) APN Science Bulletin 11(1): 133–143 · ตารางที่ 1',
                          'url': 'https://doi.org/10.30852/sb.2021.1704',
                          'note': 'พื้นที่สูง จ.น่าน; เชื้อเพลิงก่อนเผา ไม่รวมต้นไม้'},
}
FUEL_MEASUREMENTS = {
    'dipterocarp_doisuthep': {'kind': 'dipterocarp', 'site': 'ป่าเต็งรัง อุทยานแห่งชาติดอยสุเทพ-ปุย เชียงใหม่', 'period': 'ฤดูไฟ พ.ย. 2534–พ.ค. 2535',
        't_ha': '5.19', 'components_t_ha': {'ใบไม้แห้ง': '1.98', 'หญ้า': '1.48', 'ไม้พื้นล่าง': '1.07', 'กิ่งไม้': '0.66'},
        'peak': 'สะสมสูงสุดช่วง มี.ค.–เม.ย.', 'ref': {'id': 'akkhaak_1992'}},
    'mixed_deciduous_nan': {'kind': 'mixed_deciduous', 'site': 'ป่าเบญจพรรณพื้นที่สูง จ.น่าน', 'period': 'ก่อนเผา (Wanthongchai และคณะ 2021)',
        't_ha': '3.57', 'components_t_ha': {'ใบไม้แห้ง': '3.34', 'ไม้พื้นล่าง': '0.23'}, 'ref': {'id': 'wanthongchai_2021', 'page': 5}},
    'corn_nan': {'kind': 'crop', 'site': 'ไร่ข้าวโพดพื้นที่สูง จ.น่าน', 'period': 'ก่อนเผา (Wanthongchai และคณะ 2021)',
        't_ha': '3.86', 'components_t_ha': {'ตอซัง/เศษพืช': '3.59', 'วัชพืช': '0.27'}, 'ref': {'id': 'wanthongchai_2021', 'page': 5}},
    'upland_rice_nan': {'kind': 'crop', 'site': 'ข้าวไร่พื้นที่สูง จ.น่าน', 'period': 'ก่อนเผา (Wanthongchai และคณะ 2021)',
        't_ha': '2.665', 'components_t_ha': {'ตอซัง/เศษพืช': '2.665'}, 'ref': {'id': 'wanthongchai_2021', 'page': 5}},
}
NOT_AT_POINT = 'ค่าที่วัดในพื้นที่ศึกษา ไม่ใช่ค่าที่วัด ณ จุดนี้'


def per_rai(t_ha):
    return (Decimal(t_ha) / HA_PER_RAI).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def one(t_ha):
    return Decimal(t_ha).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)


def fuel_profiles(stats):
    m = {k: {**v, 't_rai': str(per_rai(v['t_ha']))} for k, v in FUEL_MEASUREMENTS.items()}
    dd, md = m['dipterocarp_doisuthep'], m['mixed_deciduous_nan']
    corn, rice = m['corn_nan'], m['upland_rice_nan']
    dd_ref, md_ref = dd['ref'], md['ref']
    deciduous_share = int(Decimal(stats['deciduous_percent']).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    low, high = sorted([per_rai(md['t_ha']), per_rai(dd['t_ha'])])
    pair = f"เบญจพรรณ (น่าน) {one(md['t_ha'])} และเต็งรัง (ดอยสุเทพ-ปุย) {one(dd['t_ha'])} ตัน/เฮกตาร์ (ราว {low}–{high} ตัน/ไร่)"
    entry = lambda text, brief, refs, ids: {'text': text, 'brief': brief, 'refs': refs, 'status': 'measured_reference', 'measurements': ids}
    return m, {
        'dipterocarp': entry(f"ค่าที่เคยวัดใน{dd['site']}: เฉลี่ย {one(dd['t_ha'])} ตัน/เฮกตาร์ (ราว {dd['t_rai']} ตัน/ไร่) {dd['period']} · {dd['peak']} · {NOT_AT_POINT}",
                             f"เชื้อเพลิงที่เคยวัดในป่าเต็งรัง ราว {dd['t_rai']} ตัน/ไร่", [dd_ref], ['dipterocarp_doisuthep']),
        'mixed_deciduous': entry(f"ค่าที่เคยวัดใน{md['site']}: {one(md['t_ha'])} ตัน/เฮกตาร์ (ราว {md['t_rai']} ตัน/ไร่) {md['period']} · {NOT_AT_POINT}",
                                 f"เชื้อเพลิงที่เคยวัดในป่าเบญจพรรณ ราว {md['t_rai']} ตัน/ไร่", [md_ref], ['mixed_deciduous_nan']),
        'deciduous': entry(f"ค่าที่เคยวัดในป่าผลัดใบภาคเหนือ: {pair} · ป่าเต็งรัง{dd['peak']} · {NOT_AT_POINT}",
                           f"เชื้อเพลิงที่เคยวัดในป่าผลัดใบ ราว {low}–{high} ตัน/ไร่", [md_ref, dd_ref], ['mixed_deciduous_nan', 'dipterocarp_doisuthep']),
        'unknown_forest': entry(f"จุดนี้ยังไม่รู้ชนิดป่า · ป่าเชียงใหม่ราว {deciduous_share}% เป็นป่าผลัดใบ (กรมป่าไม้ 2543) ซึ่งเคยวัดได้ {pair} · ป่าดิบยังไม่มีค่าวัดที่ตรวจสอบได้ · {NOT_AT_POINT}",
                                f"ถ้าเป็นป่าผลัดใบ เชื้อเพลิงที่เคยวัด ราว {low}–{high} ตัน/ไร่", [md_ref, dd_ref, {'id': 'rfd_2000', 'page': 2}], ['mixed_deciduous_nan', 'dipterocarp_doisuthep']),
        'crop': entry(f"ค่าที่เคยวัดก่อนเผาในแปลงพื้นที่สูง จ.น่าน: ไร่ข้าวโพด {one(corn['t_ha'])} ตัน/เฮกตาร์ (ราว {corn['t_rai']} ตัน/ไร่), ข้าวไร่ {one(rice['t_ha'])} ตัน/เฮกตาร์ (ราว {rice['t_rai']} ตัน/ไร่) · นาข้าวพื้นราบยังไม่มีค่าวัดที่ตรวจสอบได้ · {NOT_AT_POINT}",
                      None, [corn['ref']], ['corn_nan', 'upland_rice_nan']),
    }


def apply_fuel_measurements(ref, stats):
    measurements, levels = fuel_profiles(stats)
    ref['sources'].update(FUEL_SOURCES)
    ref['fuel_measurements'] = measurements
    ref['fuel_level_policy'] = ('Show only published field measurements of pre-burn fuel load, labelled with site and year, '
                                'never as a value at the hotspot. No low/medium/high threshold is cited, so none is assigned. '
                                'Kinds without a verified measurement stay unknown. Do not substitute fire intensity, carbon loss, EVI or tree cover.')
    for kind, level in levels.items():
        ref['profiles'][kind]['fuel_level'] = {k: v for k, v in level.items() if v is not None}
    return ref


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,help='Cached original RFD PDF')
    args=parser.parse_args()
    raw=args.pdf.read_bytes() if args.pdf else httpx.get(SOURCE,timeout=90,follow_redirects=True).raise_for_status().content
    from pypdf import PdfReader
    stats=parse_table(PdfReader(BytesIO(raw)).pages[1].extract_text())
    stats.update({'source_url':SOURCE,'source_page':2,'table':1,'reference_year':2000,'reference_year_be':2543,
                  'source_pdf_sha256':hashlib.sha256(raw).hexdigest(),'source_pdf_bytes':len(raw)})
    (DATA/'chiangmai-forest-statistics-2000.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    ref_path=DATA/'land-context-reference.json'
    ref=json.loads(ref_path.read_text(encoding='utf-8'))
    ref['province_context']=stats
    ref['sources'].pop('cgls',None)
    ref['profiles'].pop('mixed_forest',None)
    ref['sources']['rfd_2000']={'title':'กรมป่าไม้ ตารางที่ 1 เนื้อที่ป่าไม้แยกรายจังหวัด พ.ศ. 2543','url':SOURCE,'page':2}
    apply_fuel_measurements(ref, stats)
    ref['version']='land-context-reference-v3-measured-fuel'
    payload=(json.dumps(ref,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    ref_path.write_bytes(payload)
    (ROOT/'frontend/public/land-context-reference.json').write_bytes(payload)
    print('Extracted RFD page 2; calculated provincial percentages; synchronized public reference')


if __name__=='__main__':
    main()
