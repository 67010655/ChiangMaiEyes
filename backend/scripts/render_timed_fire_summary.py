"""Static, exportable figures of every frozen test and two predeclared examples."""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import timed_fire_spread_benchmark as b


def main():
    comparison=b.read(b.OUT/'COMPARISON.json')
    physical=b.read(b.OUT/'test-results.json')
    ml=b.read(b.OUT/'growth-ml/test-results.json')
    dense=b.read(b.OUT/'growth-20m/test-results.json')
    choices=comparison['choices_frozen_from2025']
    physical_name=choices['selected_physics'][1]
    ml_name=choices['selected_growth_policy'][1]
    full_name=choices['full_large'][1]
    dense_name=choices['selected_dense20m'][1]
    rows={r['id']:r for r in ml['rows']}
    ids=[r['id'] for r in physical['rows']]
    fig,axes=plt.subplots(2,1,figsize=(13,9),layout='constrained')
    x=np.arange(len(ids))
    phy=np.array([r['scores'][physical_name]['dice'] for r in physical['rows']])*100
    base=np.array([rows[i]['scores'][ml_name]['dice'] for i in ids])*100
    dense_rows={r['id']:r for r in dense['rows']}
    dense_values=np.array([dense_rows[i]['scores'][dense_name]['dice'] for i in ids])*100
    axes[0].bar(x-.26,phy,.26,label='Physics: selected using 2025',color='#b45309')
    axes[0].bar(x,base,.26,label='Growth policy: selected using 2025',color='#2563eb')
    axes[0].bar(x+.26,dense_values,.26,label='20 m iteration: selected using 2025',color='#0f766e')
    axes[0].set(ylabel='New spectral-scar Dice (%)',title='All frozen 2026 case windows; 2–5 day intervals, not 12 h')
    axes[0].legend()
    cumulative=np.array([r['scores']['no_growth']['cumulative_dice_including_initial'] for r in physical['rows']])*100
    axes[1].bar(x,cumulative,color='#64748b',label='No growth: keep already-known initial scar')
    axes[1].axhline(80,color='#991b1b',ls='--',label='80%')
    axes[1].set(ylabel='Cumulative Dice including known initial scar (%)',ylim=(0,102),title='A high cumulative score can occur with zero prediction of new growth')
    axes[1].legend()
    for axis in axes:
        axis.set_xticks(x,ids,rotation=40,ha='right',fontsize=8)
        axis.grid(axis='y',alpha=.2)
    fig.savefig(b.OUT/'all-test-comparison.png',dpi=170)
    plt.close(fig)
    # Fixed examples: chronological first core case and candidate2892 community.
    # These were selected for illustration before reading model success scores.
    for case_id in ('2026-03-27','2026-04-15-community-cmf-th-2892'):
        folder=b.OUT/'cases'/case_id
        meta=b.read(folder/'case.json')
        arrays=np.load(folder/'model-arrays.npz')
        candidates=np.load(folder/'growth-ml-predictions.npz')
        dense_mask=np.load(folder/'growth-20m-predictions.npz')[dense_name]
        arrival=np.load(folder/'predictions'/(physical_name+'.npz'))['arrival_minutes']
        fig,axes=plt.subplots(2,3,figsize=(14,9),layout='constrained')
        for axis,key,title in [(axes[0,0],'initial_falsecolor','Initial SWIR / NIR / red'),(axes[0,1],'final_falsecolor','Later image: evaluation only')]:
            image=np.clip(np.moveaxis(arrays[key],0,-1)/[.4,.5,.25],0,1)
            axis.imshow(image,extent=(0,10,0,10));axis.set_title(title)
        reference=np.ones((500,500,3))*.92
        reference[~arrays['valid20']]=[.45,.45,.45]
        reference[arrays['initial_scar20'] & arrays['valid20']]=[.1,.5,1]
        reference[arrays['target20']]=[.1,.65,.25]
        axes[0,2].imshow(reference,extent=(0,10,0,10));axes[0,2].set_title('Blue: initial scar; green: new spectral scar')
        for axis,mask,title in [(axes[1,0],arrival<=meta['horizon_hours']*60,'Selected physics'),
                                (axes[1,1],dense_mask,'20 m hotspot + wind + PM growth ML'),
                                (axes[1,2],candidates[ml_name],'Selected 500 m hotspot / vegetation policy')]:
            native=mask if mask.shape==(500,500) else np.repeat(np.repeat(mask,5,axis=0),5,axis=1)
            predicted=native&arrays['valid20']&~arrays['initial_scar20']
            image=np.ones((500,500,3))*.92
            image[~arrays['valid20']]=[.45,.45,.45]
            image[arrays['initial_scar20']&arrays['valid20']]=[.1,.5,1]
            image[predicted]=[.95,.38,.2]
            image[arrays['target20']]=[.1,.65,.25]
            image[predicted & arrays['target20']]=[.75,.3,.85]
            axis.imshow(image,extent=(0,10,0,10));axis.set_title(title)
        for axis in axes.ravel():
            axis.set(xlabel='East (km)',ylabel='North (km)')
        fig.legend(handles=[Patch(color='#f26133',label='Prediction only'),Patch(color='#19a640',label='Reference only'),
                            Patch(color='#bf4dd9',label='Overlap'),Patch(color='#1a80ff',label='Known initial scar'),Patch(color='#737373',label='Unknown / not evaluated')],loc='outside lower center',ncol=5)
        fig.suptitle(f'{case_id}: {meta["horizon_hours"]:.1f} h retrospective image-conditioned hindcast\nSatellite spectral-change candidates, not surveyed fire fronts')
        fig.savefig(b.OUT/(case_id+'-comparison.png'),dpi=170)
        plt.close(fig)
    print('FIGURES_READY',b.OUT)


if __name__=='__main__':
    main()
