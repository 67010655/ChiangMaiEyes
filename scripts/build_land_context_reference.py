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
    ref['version']='land-context-reference-v2-esa-only'
    payload=(json.dumps(ref,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    ref_path.write_bytes(payload)
    (ROOT/'frontend/public/land-context-reference.json').write_bytes(payload)
    print('Extracted RFD page 2; calculated provincial percentages; synchronized public reference')


if __name__=='__main__':
    main()
