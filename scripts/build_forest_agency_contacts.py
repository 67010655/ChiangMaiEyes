"""Rebuild the public Chiang Mai agency directory, never retaining person names.

Run: python scripts/build_forest_agency_contacts.py
The publisher's HTTP charset (Windows-874) overrides its incorrect UTF-8 meta tag.
Only organization/address fields and the telephone column are read; the head-of-
office column is deliberately ignored. Raw publisher HTML is not written to disk.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

SOURCE = 'https://forestinfo.forest.go.th/telephone_region.aspx'
OUTPUT = Path(__file__).resolve().parents[1] / 'frontend/public/forest-agency-contacts.json'
PREFIXES = ('หน่วยป้องกันรักษาป่า', 'หน่วยป้องกันและพัฒนาป่าไม้',
            'หน่วยส่งเสริมการควบคุมไฟป่า', 'ศูนย์ป่าไม้เชียงใหม่',
            'สำนักจัดการทรัพยากรป่าไม้ที่ 1 (เชียงใหม่)')


def clean(value: str) -> str:
    return re.sub(r'\s+', ' ', value).strip()


class DirectoryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.rows = []
        self.row = None
        self.cell = None
        self.column = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table':
            if self.table_depth or attrs.get('id') == 'ctl00_CPH_Content_gv':
                self.table_depth += 1
        if self.table_depth != 1:
            return
        if tag == 'tr':
            self.row, self.column = [], 0
        elif tag == 'td' and self.row is not None:
            self.cell = {'text': [], 'fields': {}} if self.column < 2 else None
        elif tag == 'br' and self.cell is not None:
            self.cell['text'].append(' ')
        elif tag == 'input' and self.column == 0 and self.cell is not None:
            # Explicit allowlist: no staff/head-of-office field is retained.
            for suffix in ('hd_name', 'hd_address'):
                if attrs.get('name', '').endswith('$' + suffix):
                    self.cell['fields'][suffix] = clean(attrs.get('value', ''))

    def handle_data(self, value):
        if self.table_depth == 1 and self.cell is not None:
            self.cell['text'].append(value)

    def handle_endtag(self, tag):
        if self.table_depth == 1:
            if tag == 'td' and self.row is not None:
                if self.column < 2 and self.cell is not None:
                    self.row.append({'text': clean(''.join(self.cell['text'])), **self.cell['fields']})
                self.cell = None
                self.column += 1
            elif tag == 'tr' and self.row is not None:
                self.rows.append(self.row)
                self.row, self.cell = None, None
        if tag == 'table' and self.table_depth:
            self.table_depth -= 1


def phones_only(value: str) -> list[str]:
    # Parenthesized annotations can name people. Retain only complete Thai phone
    # numbers, never the annotation, a staff name, or the original cell text.
    value = re.sub(r'\([^()]*\)', ' ', value)
    numbers = [re.sub(r'\D', '', m.group()) for m in re.finditer(
        r'(?<!\d)0(?:[\s.\-–]*\d){8,9}(?![\s.\-–]*\d)', value)]
    return list(dict.fromkeys(numbers))


def location(address: str) -> tuple[str, str]:
    def field(prefix, stop):
        match = re.search(prefix + r'\s*(.*?)' + stop, address)
        return clean(match.group(1)) if match else ''
    tambon = field(r'(?:ต\.|ตำบล)\s*(?:ตำบล\s*)?', r'(?=\s*(?:อ\.|อำเภอ|จ\.|จังหวัด)|$)')
    district = field(r'(?:อ\.|อำเภอ)\s*(?:อำเภอ\s*|อ\.\s*)?', r'(?=\s*(?:จ\.|จังหวัด)|\s+\d{5}|$)')
    if district == 'เมือง':
        district = 'เมืองเชียงใหม่'
    return tambon, district


def parse_directory(html: str, checked_on: str) -> dict:
    date.fromisoformat(checked_on)
    parser = DirectoryParser()
    parser.feed(html)
    agencies, province = [], ''
    for row in parser.rows:
        if len(row) == 1 and row[0]['text']:
            province = row[0]['text']
            continue
        if len(row) < 2:
            continue
        name = row[0].get('hd_name', '')
        if province != 'เชียงใหม่' or not name.startswith(PREFIXES):
            continue
        phones = phones_only(row[1]['text'])
        if not phones:
            continue
        tambon, district = location(row[0].get('hd_address') or row[0]['text'])
        agencies.append({'name': name, 'tambon': tambon, 'district': district,
                         'phones': phones, 'source': SOURCE, 'checked_on': checked_on})
    # Parse only the update date; never capture the editor's name beside it.
    updated = re.search(r'(\d{1,2})/(\d{1,2})/(25\d{2})\s+\d{1,2}:\d{2}:\d{2}', html)
    source_updated_on = date(int(updated[3]) - 543, int(updated[2]), int(updated[1])).isoformat() if updated else None
    return {'source': SOURCE, 'source_updated_on': source_updated_on,
            'checked_on': checked_on, 'agencies': agencies}


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--output', type=Path, default=OUTPUT)
    args.add_argument('--checked-on', default=datetime.now(timezone(timedelta(hours=7))).date().isoformat())
    config = args.parse_args()
    with urlopen(Request(SOURCE, headers={'User-Agent': 'ChiangMaiEyes public agency directory'}), timeout=30) as response:
        encoding = response.headers.get_content_charset() or 'utf-8'
        html = response.read().decode('cp874' if encoding.lower() == 'windows-874' else encoding)
    data = parse_directory(html, config.checked_on)
    names = [a['name'] for a in data['agencies']]
    if not any(n.startswith('สำนักจัดการ') for n in names) or not any(n.startswith('หน่วยป้องกันรักษาป่า') for n in names):
        raise SystemExit('Publisher layout changed or required agencies missing; output was not replaced')
    config.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Wrote {len(names)} agencies with phone numbers; source updated {data['source_updated_on']}; checked {config.checked_on}")


if __name__ == '__main__':
    main()
