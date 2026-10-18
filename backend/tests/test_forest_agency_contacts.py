"""The public directory is generated from agency cells, never staff columns."""
from html import escape
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('agency_builder', ROOT / 'scripts/build_forest_agency_contacts.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def row(name, address, phones='', staff='PRIVATE PERSON DO NOT RETAIN'):
    return f'''<tr><td><input name="grid$hd_name" value="{escape(name)}">
      <input name="grid$hd_address" value="{escape(address)}">{escape(name)} {escape(address)}</td>
      <td>{phones}</td><td>{staff}</td></tr>'''


def test_parser_keeps_only_requested_chiangmai_agencies_with_phones_and_never_retains_people():
    html = '<table id="ctl00_CPH_Content_gv"><tr><td colspan="3"><input name="grid$hd_name" value="เชียงใหม่">เชียงใหม่</td></tr>'
    html += row('หน่วยป้องกันรักษาป่าที่ ชม.1 (น้ำยอน)', 'ต.ตำบลท่าตอน อ.อำเภอแม่อาย จ.เชียงใหม่',
                '053-111222 (PRIVATE ANNOTATION), 081-1112222')
    html += row('หน่วยส่งเสริมการควบคุมไฟป่าเชียงใหม่', 'ต.ออนกลาง อ.แม่ออน จ.เชียงใหม่')
    html += row('สถานีเพาะชำกล้าไม้', 'ต.ช้างคลาน อ.เมือง จ.เชียงใหม่', '053-333444')
    html += '<tr><td colspan="3">ลำพูน</td></tr>' + row('หน่วยป้องกันและพัฒนาป่าไม้ลี้', 'ต.ลี้ อ.ลี้', '053-555666')
    html += '</table><span>PRIVATE EDITOR 20/11/2568 11:42:32</span>'
    data = builder.parse_directory(html, '2026-10-18')
    assert data['source_updated_on'] == '2025-11-20'
    assert len(data['agencies']) == 1
    a = data['agencies'][0]
    assert (a['tambon'], a['district'], a['phones']) == ('ท่าตอน', 'แม่อาย', ['053111222', '0811112222'])
    assert set(a) == {'name', 'tambon', 'district', 'phones', 'source', 'checked_on'}
    assert 'PRIVATE' not in json.dumps(data)


def test_all_requested_categories_are_supported_and_missing_phone_is_not_replaced():
    names = ['สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่)', 'ศูนย์ป่าไม้เชียงใหม่',
             'หน่วยป้องกันและพัฒนาป่าไม้หางดง', 'หน่วยส่งเสริมการควบคุมไฟป่าเชียงใหม่']
    html = '<table id="ctl00_CPH_Content_gv"><tr><td>เชียงใหม่</td></tr>'
    html += ''.join(row(n, 'ต.ช้างคลาน อ.เมือง จ.เชียงใหม่', '053-111222') for n in names)
    html += row('หน่วยป้องกันรักษาป่าที่ ชม.2', 'อ.ฝาง', '-') + '</table>'
    data = builder.parse_directory(html, '2026-10-18')
    assert [a['name'] for a in data['agencies']] == names
    assert all(a['district'] == 'เมืองเชียงใหม่' for a in data['agencies'])


def test_checked_in_directory_has_only_public_allowlisted_fields_and_the_complete_24_units():
    data = json.loads((ROOT / 'frontend/public/forest-agency-contacts.json').read_text(encoding='utf-8'))
    unit_numbers = set()
    import re
    for agency in data['agencies']:
        assert set(agency) == {'name', 'tambon', 'district', 'phones', 'source', 'checked_on'}
        assert agency['source'] == builder.SOURCE
        assert agency['phones'] and all(re.fullmatch(r'0\d{8,9}', p) for p in agency['phones'])
        match = re.search(r'ชม\.\s*(\d+)', agency['name'])
        if match:
            unit_numbers.add(int(match[1]))
    assert unit_numbers == set(range(1, 25))
    assert data['source_updated_on'] == '2025-11-20'
