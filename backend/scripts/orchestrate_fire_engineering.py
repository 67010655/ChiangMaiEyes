"""Bounded local execution of the approved offline loop; resumable stage receipts."""
import time,gc
from datetime import datetime,timezone
from threadpoolctl import threadpool_limits
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import run_fire_engineering_loop as loop
import fire_engineering_physics as physical
from fire_engineering_inputs import initial_features
from probe_native_weather_grid import fetch_historical_case_grid


def wait_year(year,target=8):
    deadline=time.monotonic()+3*3600;last=None
    while time.monotonic()<deadline:
        existing=[]
        for path in sorted((c.OUT/'cases').glob('*/case.json')):
            try:meta=c.read(path)
            except (ValueError,OSError):continue
            if meta.get('engineering_cohort')=='expanded_bank' and meta['candidate']['year']==year:existing.append(meta)
        if len(existing)!=last:print('WAIT_BANK',year,len(existing),'/',target,flush=True);last=len(existing)
        if len(existing)>=target:return
        progress=c.OUT/f'bank-progress-{year}.json'
        if progress.exists() and c.read(progress).get('complete'):
            assert len(existing)>=4,f'Insufficient usable {year} cases after bounded quality attempts'
            return
        time.sleep(15)
    raise TimeoutError(f'Casebank {year} did not complete within bounded3hours')


def prepare_available():
    rows=[];errors=[]
    for path in sorted((c.OUT/'cases').glob('*/case.json')):
        meta=c.read(path)
        if not meta.get('engineering_split'):continue
        try:
            quality_path=path.parent/'quality.json'
            q=c.read(quality_path) if quality_path.exists() else prep.prepare(meta)
            q.update(engineering_split=meta['engineering_split'],engineering_cohort=meta['engineering_cohort'])
            initial_features(meta);grid=fetch_historical_case_grid(meta,path.parent)
            rows.append(q);print('CASE_INPUTS_VERIFIED',meta['id'],grid['receipt']['unique_grid_point_count'],flush=True)
        except Exception as error:
            errors.append({'id':meta['id'],'reason':str(error)});print('CASE_INPUT_EXCLUDED',meta['id'],str(error),flush=True)
    c.write(c.OUT/'array-manifest.json',{'ready':rows,'excluded':errors})


def stage(name,function):
    receipt=c.OUT/'stages'/(name+'.json')
    if receipt.exists() and c.read(receipt).get('status')=='complete':print('STAGE_CACHED',name,flush=True);return
    print('STAGE_START',name,flush=True);function();gc.collect()
    c.write(receipt,{'status':'complete','finished_utc':datetime.now(timezone.utc).isoformat()})
    print('STAGE_COMPLETE',name,flush=True)


def main():
    wait_year(2024);prepare_available();stage('fit2024',loop.fit_phase)
    wait_year(2025);prepare_available();stage('select2025',lambda:loop.evaluate('selection'))
    # The standalone physics program uses argparse; keep explicit phase in a
    # child process so no process-wide module/argument changes affect ML.
    import subprocess,sys
    def run_physics(phase):subprocess.run([sys.executable,'-X','utf8',str(c.ROOT/'backend/scripts/fire_engineering_physics.py'),'--phase',phase],check=True)
    stage('physics-select2025',lambda:run_physics('selection'))
    selection=c.read(loop.MODEL_DIR/'selection.json');pselection=c.read(physical.OUT/'selection.json')
    alternatives=[('learned_or_baseline',selection['selected'],selection['summary'][selection['selected']]),('surface_graph',pselection['selected'],pselection['summary'][pselection['selected']])]
    chosen=sorted(alternatives,key=lambda r:(-r[2]['pooled_dice'],r[2]['predicted_growth_km2'],r[1]))[0]
    c.write(c.OUT/'global-frozen-selection.json',{'family':chosen[0],'name':chosen[1],'validation2025':chosen[2],
      'criterion':'2025poolednewgrowthDiceacrossfiniteML/baseline/surfacegraph choices; no2026scoreselection.',
      'ml_selection_sha256':c.sha(loop.MODEL_DIR/'selection.json'),'physics_selection_sha256':c.sha(physical.OUT/'selection.json')})
    wait_year(2026);prepare_available();stage('test2026',lambda:loop.evaluate('test'));stage('physics-test2026',lambda:run_physics('test'))
    c.write(c.OUT/'loop-execution-complete.json',{'status':'scoring_complete','selected_family':chosen[0],'selected_name':chosen[1],'production_changed':False})


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
