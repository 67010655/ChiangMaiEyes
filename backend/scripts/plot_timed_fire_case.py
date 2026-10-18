"""Visual QA of a timed optical reference and a forecast, never a web page."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/fire-perimeter-loop-20261017'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--model', default='pyre_mapped9_dynamic_image_s0.25')
    args = parser.parse_args()
    folder = OUT / 'cases' / args.case
    metadata = json.loads((folder / 'case.json').read_text(encoding='utf8'))
    arrays = dict(np.load(folder / 'model-arrays.npz'))
    figure, axes = plt.subplots(2, 2, figsize=(11, 10), layout='constrained')
    for axis, key, title in [(axes[0, 0], 'initial_falsecolor', 'Initial image'), (axes[0, 1], 'final_falsecolor', 'Later image')]:
        image = np.moveaxis(arrays[key], 0, -1)
        image = np.clip(image/np.array([.4, .5, .25]), 0, 1)
        axis.imshow(image, extent=[0, 10, 0, 10])
        axis.set_title(title)
    axis = axes[1, 0]
    axis.imshow(arrays['initial_nbr'], cmap='gray', vmin=-.3, vmax=.8, extent=[0, 10, 0, 10])
    overlay = np.zeros((500, 500, 4))
    overlay[arrays['initial_scar20']] = [0, .5, 1, .8]
    overlay[arrays['target20']] = [0, 1, .1, 1]
    axis.imshow(overlay, extent=[0, 10, 0, 10])
    r, c = np.where(arrays['seeds_point'])
    axis.scatter((c+.5)*.1, 10-(r+.5)*.1, s=9, c='red')
    axis.set_title('Blue: initial scar; green: new spectral scar; red: past hotspots')
    path = folder / 'predictions' / (args.model + '.npz')
    if path.exists():
        arrival = np.load(path)['arrival_minutes']
        axes[1, 1].imshow(arrival/60, extent=[0, 10, 0, 10], vmin=0, vmax=metadata['horizon_hours'], cmap='magma')
        axes[1, 1].contour(np.linspace(.01, 9.99, 500), np.linspace(9.99, .01, 500), arrays['target20'], levels=[.5], colors=['cyan'], linewidths=.5)
        axes[1, 1].set_title(args.model+'; cyan: reference')
    for axis in axes.ravel():
        axis.set(xlabel='East from window edge (km)', ylabel='North from window edge (km)')
    figure.suptitle(f"{args.case}: {metadata['initial_acquisition']} → {metadata['final_acquisition']}\nSpectral-change reference; initial-image-conditioned hindcast", fontsize=12)
    figure.savefig(folder / 'visual-qa.png', dpi=160)
    plt.close(figure)
    print(folder / 'visual-qa.png')


if __name__ == '__main__':
    main()
