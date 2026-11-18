import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

let loading: Promise<typeof import('maplibre-gl')> | null = null;

// Keep the large 3D renderer out of the initial 2D page download.
Object.assign(window, {
  mapTilerKey: import.meta.env.VITE_MAPTILER_KEY || "",
  ensureMapLibre: () => {
    loading ??= Promise.all([import('maplibre-gl'), import('maplibre-contour')]).then(([maplibregl, contour]) => {
      maplibregl.setWorkerUrl(workerUrl);
      // Contour lines in 3D are drawn in the browser from the same Terrarium elevation tiles.
      Object.assign(window, {maplibregl, mlcontour: (contour as any).default || contour});
      return maplibregl;
    }).catch(error => {
      loading = null;
      throw error;
    });
    return loading;
  },
});
