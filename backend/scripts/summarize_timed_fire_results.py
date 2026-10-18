"""Compare frozen choices and actual community portions without selecting on test."""
from collections import defaultdict
from datetime import datetime
import numpy as np
import timed_fire_spread_benchmark as b


def score_summary(values):
    p, r, i = [sum(v[k] for v in values) for k in ('predicted_growth_km2', 'reference_growth_km2', 'intersection_km2')]
    return {'case_count': len(values), 'macro_dice': float(np.mean([v['dice'] for v in values])),
            'pooled_dice': 2*i/(p+r) if p+r else 1., 'pooled_iou': i/(p+r-i) if p+r-i else 1.,
            'predicted_growth_km2': p, 'reference_growth_km2': r, 'intersection_km2': i,
            'reference_coverage': i/r if r else None, 'unmatched_prediction_km2': p-i,
            'cumulative_macro_dice': float(np.mean([v['cumulative_dice_including_initial'] for v in values])),
            'boundary_mean_m': float(np.mean([v['symmetric_boundary_mean_m'] for v in values if v.get('symmetric_boundary_mean_m') is not None])) if any(v.get('symmetric_boundary_mean_m') is not None for v in values) else None}


def main():
    frozen = b.read(b.OUT/'frozen-inputs.json')
    ml_selection = b.read(b.OUT/'growth-ml/selection.json')
    physical_selection = b.read(b.OUT/'spread-selection.json')
    ml = b.read(b.OUT/'growth-ml/test-results.json')
    physical = b.read(b.OUT/'test-results.json')
    dense = b.read(b.OUT/'growth-20m/test-results.json') if (b.OUT/'growth-20m/test-results.json').exists() else None
    choices = {'selected_physics': ('physics', physical_selection['selected']),
               'selected_growth_policy': ('ml', ml_selection['selected']), 'no_growth': ('physics', 'no_growth')}
    validation_scores={'selected_physics':physical_selection['validation'][physical_selection['selected']]['macro_dice'],
                       'selected_growth_policy':ml_selection['validation'][ml_selection['selected']]['macro_dice']}
    if dense:
        dense_selection=b.read(b.OUT/'growth-20m/selection.json')
        choices['selected_dense20m']=('dense',dense_selection['selected'])
        validation_scores['selected_dense20m']=dense_selection['validation'][dense_selection['selected']]['macro_dice']
    overall=max(validation_scores,key=validation_scores.get)
    choices['selected_overall']=choices[overall]
    # Each subgroup's threshold is chosen by the same 2025 folds, never test.
    for prefix in ('full_small', 'full_large', 'without_pm', 'without_wind_pm'):
        name = next(n for n in ml_selection['ranking'] if n.startswith(prefix+'__'))
        choices[prefix] = ('ml', name)
    physical_simple = next(n for n in physical_selection['ranking'] if n.startswith('isotropic_'))
    choices['selected_isotropic'] = ('physics', physical_simple)
    lookup = {c['id']: c for c in frozen['cases']}
    rows = {'ml': {r['id']: r for r in ml['rows']}, 'physics': {r['id']: r for r in physical['rows']}}
    if dense:rows['dense']={r['id']:r for r in dense['rows']}
    cohorts = {}
    for cohort in ('original_case_studies', 'community_known_hotspot_enriched'):
        ids = [c['id'] for c in frozen['cases'] if c['split'] == 'retrospective_test2026' and c['cohort'] == cohort]
        if not ids:
            continue
        cohorts[cohort] = {}
        for title, (family, name) in choices.items():
            values = [rows[family][i]['scores'][name] for i in ids]
            summary = score_summary(values)
            summary['connected_growth'] = score_summary([v['connected_growth'] for v in values])
            summary['low_threshold_dice'] = score_summary([v['low_reference_threshold'] for v in values])['pooled_dice']
            summary['high_threshold_dice'] = score_summary([v['high_reference_threshold'] for v in values])['pooled_dice']
            cohorts[cohort][title] = summary
    # Case-cluster bootstrap: spatially intersecting windows with overlapping
    # observation times are resampled together; do not pretend 10000 cells are trials.
    ids = [c['id'] for c in frozen['cases'] if c['split'] == 'retrospective_test2026' and c['cohort'] == 'original_case_studies']
    parent = list(range(len(ids)))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i, a in enumerate(ids):
        am = b.read(b.OUT/'cases'/a/'case.json')
        x1,y1,x2,y2 = am['bounds_utm47']
        for j, c in enumerate(ids[:i]):
            cm = b.read(b.OUT/'cases'/c/'case.json')
            u1,v1,u2,v2 = cm['bounds_utm47']
            spatial = max(x1,u1)<min(x2,u2) and max(y1,v1)<min(y2,v2)
            temporal = max(am['initial_acquisition'],cm['initial_acquisition']) < min(am['final_acquisition'],cm['final_acquisition'])
            if spatial and temporal:
                parent[root(i)] = root(j)
    clusters = defaultdict(list)
    for i, case in enumerate(ids):
        clusters[root(i)].append(case)
    cluster_ids = list(clusters.values())
    rng = np.random.default_rng(20261018)
    intervals = {}
    for title, (family,name) in choices.items():
        samples=[]
        for _ in range(2000):
            draw = rng.integers(len(cluster_ids), size=len(cluster_ids))
            scores = [rows[family][case]['scores'][name] for index in draw for case in cluster_ids[index]]
            samples.append(score_summary(scores)['pooled_dice'])
        intervals[title] = {'lower': float(np.percentile(samples,2.5)), 'upper': float(np.percentile(samples,97.5)), 'independent_clusters': len(cluster_ids), 'warning': 'Tiny purposive case cohort; interval is descriptive, not province-wide confidence.'}
    # Forest-event portions: merge duplicate same-forest/date windows by global
    # UTM20m pixel IDs; exclude portions with <65% jointly clear observations.
    forest_events = {}
    community = b.read(b.OUT/'community-reference.json')
    for row in community['cases']:
        case_id = row['case']
        meta = b.read(b.OUT/'cases'/case_id/'case.json')
        if meta['split'] != 'retrospective_test2026':
            continue
        folder = b.OUT/'cases'/case_id
        arrays = np.load(folder/'model-arrays.npz')
        masks = np.load(folder/'community-forest-masks.npz')
        ml_masks = np.load(folder/'growth-ml-predictions.npz')
        dense_masks = np.load(folder/'growth-20m-predictions.npz') if dense else None
        selected_masks = {}
        for title,(family,name) in choices.items():
            if family == 'dense':
                selected_masks[title] = dense_masks[name] & ~arrays['initial_scar20']
                continue
            if family == 'ml':
                mask = ml_masks[name]
            else:
                arrival = np.load(folder/'predictions'/(name+'.npz'))['arrival_minutes']
                mask = arrival <= meta['horizon_hours']*60
            selected_masks[title] = np.repeat(np.repeat(mask,5,axis=0),5,axis=1) & ~arrays['initial_scar20']
        west,south,east,north = meta['bounds_utm47']
        rr,cc = np.indices((500,500))
        pixel_ids = (int(round(west/20))+cc).astype('int64')*1000000 + int(round(north/20))-rr-1
        cohort = meta['candidate'].get('cohort','original_case_studies')
        for fact in row['forests']:
            mask = masks[fact['id']]
            key = (cohort,fact['id'],meta['initial_acquisition'][:10],meta['final_acquisition'][:10])
            event = forest_events.setdefault(key, {'forest':fact['id'],'name':fact['name'],'cohort':cohort,'start':key[2],'end':key[3], 'pixels':set(),'clear':set(),'reference':set(),'predictions':{title:set() for title in choices}})
            event['pixels'].update(pixel_ids[mask].tolist())
            event['clear'].update(pixel_ids[mask & arrays['valid20']].tolist())
            event['reference'].update(pixel_ids[mask & arrays['target20']].tolist())
            for title,predicted in selected_masks.items():
                event['predictions'][title].update(pixel_ids[mask & predicted].tolist())
    events=[]
    for event in forest_events.values():
        events.append({**{k:v for k,v in event.items() if k not in ('pixels','clear','reference','predictions')},
                       'observed_portion_km2':len(event['pixels'])*.0004,'clear_fraction':len(event['clear'])/len(event['pixels']),
                       'observed_new_scar_km2':len(event['reference'])*.0004,
                       'predicted_new_growth_km2':{name:len(px)*.0004 for name,px in event['predictions'].items()}})
    forest_summary={}
    for cohort in cohorts:
        eligible = [e for e in events if e['cohort']==cohort and e['clear_fraction']>=.65]
        forest_summary[cohort]={}
        for threshold in (.01,.001):
            values={}
            for title in choices:
                tp=fn=unmatched=quiet=0
                for event in eligible:
                    observed = event['observed_new_scar_km2']>=threshold-1e-12
                    warned = event['predicted_new_growth_km2'][title]>=threshold-1e-12
                    tp+=int(observed and warned);fn+=int(observed and not warned)
                    unmatched+=int(not observed and warned);quiet+=int(not observed and not warned)
                values[title]={'observed_and_warned':tp,'observed_not_warned':fn,'warned_without_observed_scar':unmatched,'quiet_without_observed_scar':quiet,
                               'observed_event_recall':tp/(tp+fn) if tp+fn else None,
                               'observed_event_precision':tp/(tp+unmatched) if tp+unmatched else None}
            forest_summary[cohort][str(threshold)]={'threshold_km2':threshold,'eligible_forest_portion_periods':len(eligible),'scores':values}
    result={'choices_frozen_from2025':choices,'cohorts':cohorts,'core_overlap_clusters':cluster_ids,'core_pooled_dice_intervals':intervals,
            'community':forest_summary,'community_events':events,
            'community_note':'Clipped forest portions in sampled windows, not whole 677forestpopulation. Sameforest/samedateperiods uniondeduplicated. Unknown/no spectral change is not independently confirmed no fire. Enriched positive cohort reported separately.',
            'best_growth_choice_on2025':overall,'growth_validation_scores':validation_scores,
            'selection_success':False,'decision':'Retain existing priority model as best demonstrated hotspot watch tool. Optical new-growth alternatives are experimental; do not deploy as accurate perimeter forecasts.'}
    diagnostics=[]
    for case_id in ids:
        arrays=np.load(b.OUT/'cases'/case_id/'model-arrays.npz')
        support=arrays['growth_support_fraction'].ravel().astype(float)
        target=arrays['target_fraction'].ravel().astype(float)
        order=np.argsort(-np.divide(target,support,out=np.zeros_like(target),where=support>0),kind='stable')
        scores=2*np.cumsum(target[order])/(np.cumsum(support[order])+target.sum())
        diagnostics.append({'id':case_id,'reference_new_growth_km2':float(target.sum()*.01),
                 'evaluated_growth_support_km2':float(support.sum()*.01),
                 'oracle100m_maximum_dice':float(scores.max()),
                 'no_growth_cumulative_dice':rows['physics'][case_id]['scores']['no_growth']['cumulative_dice_including_initial']})
    result['reference_grid_diagnostics']={'cases':diagnostics,'note':'Oracle uses future labels only to quantify resolution ceiling; not a fitted/evaluated forecast and never eligible for model selection.',
        'no_growth_pixel_accuracy':1-sum(d['reference_new_growth_km2'] for d in diagnostics)/sum(d['evaluated_growth_support_km2'] for d in diagnostics)}
    shared_threshold=choices['full_small'][1].split('__threshold')[1]
    result['matched_architecture_ablation']={'threshold_selected_on2025_full_small':shared_threshold,
        'note':'60trees15leaves, identical threshold. Last arm removes wind plus temperature/moisture/rain, not wind alone. Four training cases cannot establish general benefit.',
        'core2026':{prefix:score_summary([rows['ml'][case]['scores'][prefix+'__threshold'+shared_threshold] for case in ids]) for prefix in ('full_small','without_pm','without_wind_pm')},
        'validation2025':{prefix:ml_selection['validation'][prefix+'__threshold'+shared_threshold] for prefix in ('full_small','without_pm','without_wind_pm')}}
    b.write(b.OUT/'COMPARISON.json',result)
    print('CORE', {name:round(v['pooled_dice'],5) for name,v in cohorts['original_case_studies'].items()})
    print('COMMUNITY',forest_summary)


if __name__ == '__main__':
    main()
