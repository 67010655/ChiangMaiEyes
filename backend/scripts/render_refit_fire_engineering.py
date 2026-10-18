"""Final static figures compare both rounds on unchanged reference masks."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import fire_engineering_common as c
import run_fire_engineering_loop as loop
import refit_fire_engineering as r


def main():
    final=c.read(c.OUT/'CONSOLIDATED_DECISION.json');old=c.read(c.OUT/'same-case-old-versus-new.json');comparison=c.read(r.OUT/'round1-versus-round2.json');priority=c.read(c.OUT/'FINAL_DECISION.json')
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    series=[(['Parent','+ Himawari'],[priority['priority_parent_coverage_pct'],priority['priority_fusion_coverage_pct']],['#2563eb','#d97706']),
       (['Earlier\nphysics','Round 1','Round 2'],[100*old['old']['pooled_dice'],100*comparison['regression2026']['round1']['pooled_dice'],100*comparison['regression2026']['round2']['pooled_dice']],['#94a3b8','#64748b','#0f766e']),
       (['Round 1','Round 2'],[100*comparison['test2026_new_cases']['round1']['pooled_dice'],100*comparison['test2026_new_cases']['round2']['pooled_dice']],['#64748b','#0f766e'])]
    titles=['12 h hotspot coverage\nSame 231 origins, 250 km² budget','New-growth Dice\nSame 11 legacy cases','New-growth Dice\nSame 8 additional cases']
    for axis,(labels,values,colours),title in zip(axes,series,titles):
        bars=axis.bar(labels,values,color=colours);axis.bar_label(bars,fmt='%.2f%%',padding=4);axis.set(ylim=(0,100),ylabel='Percent (%)',title=title);axis.grid(axis='y',alpha=.2);axis.set_axisbelow(True)
    fig.suptitle('Offline retrospective experiments | Different targets across panels\nRound 2: 2025 date-blocked selection; 2026 reused after Round 1')
    fig.savefig(c.OUT/'final-results-overview.png',dpi=180);plt.close(fig)
    cases=[sorted([m for m in loop.metas() if m['engineering_split']=='test2026_new_cases'],key=lambda m:(m['initial_acquisition'],m['id']))[0],next(m for m in loop.metas() if m['id']=='2026-04-15-community-cmf-th-2892')]
    for meta in cases:
        folder=c.OUT/'cases'/meta['id'];a=dict(np.load(folder/'model-arrays.npz'));masks=[np.load(folder/'engineering-prediction.npz')['predicted'],np.load(r.OUT/(meta['id']+'-prediction.npz'))['predicted']]
        fig,axes=plt.subplots(2,2,figsize=(10,10),layout='constrained')
        axes[0,0].imshow(np.clip(np.moveaxis(a['initial_falsecolor'],0,-1)/[.4,.5,.25],0,1),extent=(0,10,0,10));axes[0,0].set_title('Initial SWIR / NIR / red\nOnly initial and earlier inputs')
        def image(mask=None):
            rgb=np.ones((500,500,3))*.94;rgb[~a['valid20']]=[.45,.45,.45];rgb[a['initial_scar20']&a['valid20']]=[.1,.5,1]
            if mask is not None:
                visible=mask&a['valid20']&~a['initial_scar20'];rgb[visible]=[.95,.38,.2]
            rgb[a['target20']]=[.1,.65,.25]
            if mask is not None:rgb[visible&a['target20']]=[.75,.3,.85]
            return rgb
        axes[0,1].imshow(image(),extent=(0,10,0,10));axes[0,1].set_title('Later optical reference\nEvaluation only; not a surveyed fire front')
        for axis,mask,title in zip(axes[1],masks,['Round 1: trained on 8 old cases','Round 2: refit on 19 old cases']):axis.imshow(image(mask),extent=(0,10,0,10));axis.set_title(title)
        for axis in axes.ravel():axis.set(xlabel='East within window (km)',ylabel='North within window (km)')
        fig.legend(handles=[Patch(color='#f26133',label='Prediction only'),Patch(color='#19a640',label='Reference only'),Patch(color='#bf4dd9',label='Overlap'),Patch(color='#1a80ff',label='Known initial scar'),Patch(color='#737373',label='Unknown / not evaluated')],loc='outside lower center',ncol=3)
        fig.suptitle(f"{meta['id']} | {meta['horizon_hours']:.1f} h retrospective image interval")
        fig.savefig(r.OUT/(meta['id']+'-two-round-comparison.png'),dpi=150);plt.close(fig)
    print('FINAL_FIGURES_READY',flush=True)


if __name__=='__main__':main()
