"""Extend the existing approved public FIRMS import to two prior fire seasons.

Reuses the importer with redacted errors; no credential-bearing URL is stored.
"""
import json
from datetime import date,datetime,timedelta
from pathlib import Path
import run_season_hindcast as importer

ROOT=Path(__file__).resolve().parents[2]
def main():
    for year in (2024,2025):
        folder=ROOT/'output'/f'hindcast-{year}';folder.mkdir(exist_ok=True)
        final=folder/'firms-points.json'
        if final.exists():print('cached',year,len(json.loads(final.read_text(encoding='utf8'))),flush=True);continue
        importer.OUT=folder;importer.RAW=folder/'raw';importer.RAW.mkdir(exist_ok=True)
        importer.START=date(year,1,1);importer.END=date(year,4,30)
        importer.FIRST=datetime(year,1,1,tzinfo=importer.ICT);importer.UNTIL=datetime(year,5,1,tzinfo=importer.ICT)
        print('download season',year,flush=True)
        points,coverage=importer.firms()
        complete=sum(importer.complete_day(importer.START+timedelta(days=i),coverage) for i in range((importer.END-importer.START).days+1))
        importer.write(folder/'coverage.json',coverage);importer.write(final,points)
        print('completed',year,'points',len(points),'complete_days',complete,'requests',len(coverage),'failed',sum(c['status']!='received' for c in coverage),flush=True)

if __name__=='__main__':main()
