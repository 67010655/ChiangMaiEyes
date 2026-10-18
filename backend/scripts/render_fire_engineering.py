"""Exportable scientific charts; no new UI or production layer."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import fire_engineering_common as c
b,prep,physics,ml=c.configure()
import timed_fire_growth_dense as dense
import run_fire_engineering_loop as loop
from finalize_fire_engineering import prediction


def main():
    decision=c.read(c.OUT/'FINAL_DECISION.json');selected=c.read(c.OUT/'selected-growth-results.json');choice=selected['choice']
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    values=[decision['priority_parent_coverage_pct'],decision['priority_fusion_coverage_pct']]
    bars=axes[0].bar(['Parent model','+ Himawari\n2025-selected fusion'],values,color=['#2563eb','#d97706'])
    axes[0].set(ylabel='Next-12h hotspot-cell coverage (%)',ylim=(0,100),title='Same 231 retrospective 2026 origins\nSame 250 km² alert area; not perimeter skill')
    axes[0].bar_label(bars,fmt='%.2f%%',padding=3)
    groups=selected['by_split'];names=list(groups);values=[100*groups[name]['pooled_dice'] for name in names]
    bars=axes[1].bar(['Previously inspected\n2026 regression cases','Additional\n2026 cases'] if names==['regression2026','test2026_new_cases'] else names,values,color=['#64748b','#0f766e'])
    axes[1].set(ylabel='New-growth Dice (%)',ylim=(0,100),title='2025-selected growth candidate\nExact image intervals; 20 m spectral reference')
    axes[1].bar_label(bars,fmt='%.2f%%',padding=3)
    for axis in axes:axis.grid(axis='y',alpha=.2);axis.set_axisbelow(True)
    fig.savefig(c.OUT/'results-overview.png',dpi=180);plt.close(fig)
    # Compare the old surface candidate and the new selection on exactly the
    # old11case masks. Do not compare different sample denominators directly.
    old_scores=[];new_scores=[]
    for meta in loop.metas():
        if meta['engineering_split']!='regression2026':continue
        folder=c.OUT/'cases'/meta['id'];arrays=dict(np.load(folder/'model-arrays.npz'))
        old_arrival=np.load(c.OLD/'cases'/meta['id']/'predictions/pyre_mapped8_dynamic_point_s1.npz')['arrival_minutes']
        old_mask=np.repeat(np.repeat(old_arrival<=meta['horizon_hours']*60,5,axis=0),5,axis=1)
        old_scores.append({'scores':{'old':dense.metrics(old_mask,arrays)}})
        new_scores.append({'scores':{'new':dense.metrics(prediction(meta,choice),arrays)}})
    comparison={'cohort':'Exactlysame11previouslyinspected2026cases; retrospectivecomparison, nofuturemodelselection.',
        'old':loop.pooled(old_scores,'old'),'new':loop.pooled(new_scores,'new')}
    c.write(c.OUT/'same-case-old-versus-new.json',comparison)
    new_cases=sorted([m for m in loop.metas() if m['engineering_split']=='test2026_new_cases'],key=lambda m:(m['initial_acquisition'],m['id']))
    cases=[new_cases[0],next(m for m in loop.metas() if m['id']=='2026-04-15-community-cmf-th-2892')]
    for meta in cases:
        folder=c.OUT/'cases'/meta['id'];a=dict(np.load(folder/'model-arrays.npz'));mask=prediction(meta,choice)
        fig,axes=plt.subplots(1,3,figsize=(13,4.8),layout='constrained')
        rgb=np.clip(np.moveaxis(a['initial_falsecolor'],0,-1)/[.4,.5,.25],0,1)
        axes[0].imshow(rgb,extent=(0,10,0,10));axes[0].set_title('Initial SWIR / NIR / red\nOnly this time and earlier are model inputs')
        for axis,show_prediction in ((axes[1],False),(axes[2],True)):
            image=np.ones((500,500,3))*.94;image[~a['valid20']]=[.45,.45,.45]
            image[a['initial_scar20']&a['valid20']]=[.1,.5,1]
            visible=mask&a['valid20']&~a['initial_scar20']
            if show_prediction:image[visible]=[.95,.38,.2]
            image[a['target20']]=[.1,.65,.25]
            if show_prediction:image[visible&a['target20']]=[.75,.3,.85]
            axis.imshow(image,extent=(0,10,0,10))
        axes[1].set_title('Later optical reference: evaluation only\nGreen = newly detected spectral scar')
        axes[2].set_title('Frozen selected prediction vs reference\nPurple = new-growth overlap')
        for axis in axes:axis.set(xlabel='East within window (km)',ylabel='North within window (km)')
        fig.legend(handles=[Patch(color='#f26133',label='Prediction only'),Patch(color='#19a640',label='Reference only'),Patch(color='#bf4dd9',label='Overlap'),
            Patch(color='#1a80ff',label='Known initial scar'),Patch(color='#737373',label='Unknown / not evaluated')],loc='outside lower center',ncol=5)
        fig.suptitle(f"{meta['id']} | {meta['horizon_hours']:.1f} h retrospective interval\nSatellite change candidates, not surveyed fire fronts")
        fig.savefig(c.OUT/(meta['id']+'-selected-comparison.png'),dpi=170);plt.close(fig)
    print('FIGURES_READY',c.OUT,flush=True)


if __name__=='__main__':main()
