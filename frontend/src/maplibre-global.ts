import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// The production dashboard is still an inline classic script. Expose the
// installed MapLibre module until that dashboard is migrated to TypeScript.
Object.assign(window, { maplibregl });
