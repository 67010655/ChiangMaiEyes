"""Secondary positive corroboration, never treat HII zeros as negative labels."""
from datetime import datetime
import re
import numpy as np
import fire_engineering_common as c
from probe_hii_monthly_reference import read_case_monthly,download_numeric_tile


def main():
    rows=[]
    # Freeze the tile inventory for this pass before any mosaicking. Otherwise
    # an adjoining tile downloaded later could change an earlier case union.
    requests=set()
    for path in sorted((c.OUT/'cases').glob('*/case.json')):
        meta=c.read(path)
        if not meta['initial_acquisition'].startswith('2026'):continue
        grid=re.search(r'_T(\d{2}[A-Z]{3})_',meta['initial_scene']).group(1)
        for key in ('initial_acquisition','final_acquisition'):requests.add((grid,meta[key][:7].replace('-','')))
    for grid,month in sorted(requests):
        try:download_numeric_tile(grid,month,c.OUT/'hii-qa')
        except Exception as error:rows.append({'grid':grid,'month':month,'error':str(error)})
    inventory={p.name:c.sha(p) for p in (c.OUT/'hii-qa').glob('BURNSCAR_*_B2F.tif')}
    for path in sorted((c.OUT/'cases').glob('*/case.json')):
        meta=c.read(path)
        if not meta['initial_acquisition'].startswith('2026'):continue
        folder=path.parent;cache=folder/'hii-monthly-positive-only.npz';receipt_path=folder/'hii-monthly-positive-only.json'
        if cache.exists() and receipt_path.exists() and c.read(receipt_path).get('tile_inventory')==inventory:continue
        start=datetime.fromisoformat(meta['initial_acquisition']);end=datetime.fromisoformat(meta['final_acquisition'])
        months=sorted({start.strftime('%Y%m'),end.strftime('%Y%m')})
        positive=np.zeros((500,500),bool);receipts=[]
        try:
            for month in months:
                mask,coverage,receipt=read_case_monthly(meta,c.OUT/'hii-qa',month)
                assert coverage is None;positive|=mask;receipts.append(receipt)
            np.savez_compressed(cache,positive=positive)
            record={'case_id':meta['id'],'months':months,'receipts':receipts,'tile_inventory':inventory,'used_for_fitting_or_selection':False,
              'interpretation':'Same-month legal-forest positives only, not exact-interval reference or independent field survey. Missing/zero not negative. No Dice/precision/recall computed against this layer.',
              'mask_sha256':c.sha(cache)}
            c.write(receipt_path,record);print('HII_CASE',meta['id'],positive.sum(),flush=True)
        except Exception as error:
            rows.append({'id':meta['id'],'status':'unavailable','error':str(error)});print('HII_UNAVAILABLE',meta['id'],str(error),flush=True)
    c.write(c.OUT/'hii-case-exclusions.json',rows)


if __name__=='__main__':main()
