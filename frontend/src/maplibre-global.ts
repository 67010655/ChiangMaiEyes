import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

let loading: Promise<typeof import('maplibre-gl')> | null = null;

// Keep the large 3D renderer out of the initial 2D page download.
Object.assign(window, {
  mapTilerKey: import.meta.env.VITE_MAPTILER_KEY || "",
  ensureMapLibre: () => {
    loading ??= import('maplibre-gl').then(maplibregl => {
      maplibregl.setWorkerUrl(workerUrl);
      Object.assign(window, {maplibregl});
      return maplibregl;
    }).catch(error => {
      loading = null;
      throw error;
    });
    return loading;
  },
});
