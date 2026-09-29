import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

maplibregl.setWorkerUrl(workerUrl);

// The production dashboard is still an inline classic script. Expose the
// installed MapLibre module until that dashboard is migrated to TypeScript.
Object.assign(window, {
  maplibregl,
  mapTilerKey: import.meta.env.VITE_MAPTILER_KEY || "",
});
