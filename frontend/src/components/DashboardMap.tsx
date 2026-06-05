import { useCallback, useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet-velocity';
import { Crosshair, Maximize2, Minimize2, Minus, Plus, Wind } from 'lucide-react';
import type { DashboardResponse, Hotspot, Pm25Station } from '../lib/types';
import provinceGeoData from '../data/chiangmai-province.json';
import districtsGeoData from '../data/chiangmai-districts.json';
import { getDistanceKm, initialSelection, type MapSelection } from '../lib/mapSelection';
import { windDestinationName } from '../lib/wind';
import { buildWindFieldFromStation } from '../lib/windGrid';
import { getDistrictPhysics } from '../lib/firePhysics';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type Props = {
  dashboard: DashboardResponse;
  layers: {
    hotspots: boolean;
    pm25: boolean;
    wind: boolean;
    landmarks: boolean;
    fuelRisk: boolean;
  };
  selection: MapSelection;
  onSelectionChange: (sel: MapSelection) => void;
  uiMode?: 'citizen' | 'authority';
  theme?: 'light' | 'dark';
  userLocation?: [number, number] | null;
  onMapClick?: (coords: [number, number]) => void;
  isPinningMode?: boolean;
  onPinningModeChange?: (v: boolean) => void;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
};

// ─────────────────────────────────────────────
// GeoJSON preparation (module-level, computed once)
// ─────────────────────────────────────────────

// Province boundary: raw Polygon geometry { type, coordinates }
const provinceCoordsRaw = (provinceGeoData as { type: string; coordinates: number[][][] }).coordinates[0];

// World-minus-CM mask — dims everything outside the province
const maskFeature = {
  type: 'Feature',
  geometry: {
    type: 'Polygon',
    coordinates: [
      // outer ring: whole visible world in Web Mercator
      [[-180, -85.05], [180, -85.05], [180, 85.05], [-180, 85.05], [-180, -85.05]],
      // inner ring: CM province → creates the transparent "window"
      provinceCoordsRaw,
    ],
  },
  properties: {},
};

// Province fill + border
const provinceFeature = {
  type: 'Feature',
  geometry: provinceGeoData,
  properties: {},
};

// ─────────────────────────────────────────────
// Helper functions
// ─────────────────────────────────────────────

function formatPm25(v: number) {
  return `${v.toFixed(v % 1 ? 1 : 0)} µg/m³`;
}

function pm25ValueLabel(v: number) {
  return v.toFixed(v % 1 ? 1 : 0);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { timeStyle: 'short' }).format(new Date(value));
}

function pm25Color(pm25: number): string {
  if (pm25 <= 25) return '#16a34a';
  if (pm25 <= 37) return '#eab308';
  if (pm25 <= 50) return '#f97316';
  if (pm25 <= 90) return '#dc2626';
  return '#7c3aed';
}

function pm25Tone(pm25: number): 'good' | 'watch' | 'risk' {
  if (pm25 <= 25) return 'good';
  if (pm25 <= 50) return 'watch';
  return 'risk';
}

// Geographic plume radius in metres (scales naturally with Leaflet zoom)
function plumeRadiusMeters(pm25: number): number {
  return 4000 + (Math.min(pm25, 120) / 120) * 13000;
}

function stationImageKey(s: Pm25Station) {
  if (s.id === 'CM-O23') return 'bhubing';
  if (s.id === 'CM-O70') return 'chiangdao';
  if (s.id === 'CM-O71') return 'maechaem';
  if (s.id === 'CM-O69') return 'hot';
  if (s.id === 'CM-36T') return 'school';
  return 'city';
}

function hotspotImageKey(h: Hotspot) {
  return h.landuse_type && h.landuse_type !== 'OTHER' ? 'forest' : 'hotspot';
}

function hotspotPlaceTitle(h: Hotspot) {
  return h.landuse_name || h.district || h.id;
}

function hotspotLocation(h: Hotspot) {
  return [
    h.subdistrict ? `ต.${h.subdistrict}` : '',
    h.district ? `อ.${h.district}` : '',
  ]
    .filter(Boolean)
    .join(' ');
}

function shortSourceName(source: string): string {
  if (source.startsWith('Royal Forest')) return 'กรมป่าไม้';
  if (source.startsWith('GISTDA')) return 'GISTDA';
  if (source.startsWith('NASA')) return 'NASA';
  return source;
}

function hotspotSourcesLabel(h: Hotspot): string {
  const list = (h.sources && h.sources.length ? h.sources : [h.source]).map(shortSourceName);
  return Array.from(new Set(list)).join(' + ');
}

function hotspotStats(h: Hotspot): MapSelection['stats'] {
  const sourceCount = h.source_count ?? (h.sources?.length || 1);
  const phys = getDistrictPhysics(h.district);
  const slopeEffect = Math.exp(0.0693 * phys.slope_deg) / 4.0;

  return [
    { label: 'Confidence', value: `${h.confidence}%`, tone: h.confidence >= 80 ? 'risk' : 'watch' },
    {
      label: 'ยืนยันโดย',
      value: `${hotspotSourcesLabel(h)}${sourceCount > 1 ? ` (${sourceCount} แหล่ง)` : ''}`,
      tone: sourceCount > 1 ? 'risk' : undefined,
    },
    { label: 'ประเภทพื้นที่', value: h.landuse_name || h.landuse_type || 'ไม่ระบุ' },
    { label: 'สภาพเชื้อเพลิง', value: phys.forest_type },
    { 
      label: 'ความชันภูมิประเทศ', 
      value: `${phys.slope_deg}° (ลามเร็ว ${slopeEffect.toFixed(1)}x)`,
      tone: phys.slope_deg >= 25 ? 'risk' : 'watch'
    },
    { label: 'ประวัติไฟป่า', value: phys.history_level, tone: phys.history_multiplier >= 1.3 ? 'risk' : 'watch' },
    { label: 'ดาวเทียม', value: h.satellite || 'VIIRS' },
    { label: 'เวลา', value: formatTime(h.detected_at) },
  ];
}

const BASEMAPS = [
  {
    id: 'standard',
    label: 'ถนน',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    maxZoom: 19,
  },
  {
    id: 'light',
    label: 'มินิมอล',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 20,
  },
  {
    id: 'terrain',
    label: 'ภูมิประเทศ',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenTopoMap &copy; OpenStreetMap',
    maxZoom: 17,
  },
  {
    id: 'satellite',
    label: 'ดาวเทียม',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri',
    maxZoom: 19,
  },
] as const;

type BaseMapId = (typeof BASEMAPS)[number]['id'];

function createBaseTileLayer(id: BaseMapId) {
  const basemap = BASEMAPS.find((item) => item.id === id) ?? BASEMAPS[0];
  return L.tileLayer(basemap.url, {
    maxZoom: basemap.maxZoom,
    attribution: basemap.attribution,
  });
}

let velocityLayerGuardsInstalled = false;

function ensureVelocityLayerGuards() {
  if (velocityLayerGuardsInstalled) return;
  const canvasLayer = (L as any).CanvasLayer?.prototype;
  if (!canvasLayer) return;

  const drawLayer = canvasLayer.drawLayer;
  const onLayerDidMove = canvasLayer._onLayerDidMove;
  const onLayerDidResize = canvasLayer._onLayerDidResize;

  canvasLayer.drawLayer = function guardedDrawLayer(this: { _map?: L.Map | null; _canvas?: HTMLCanvasElement | null; _frame?: unknown }) {
    if (!this._map || !this._canvas) {
      this._frame = null;
      return;
    }
    return drawLayer.call(this);
  };

  canvasLayer._onLayerDidMove = function guardedOnLayerDidMove(this: { _map?: L.Map | null; _canvas?: HTMLCanvasElement | null }) {
    if (!this._map || !this._canvas) return;
    return onLayerDidMove.call(this);
  };

  canvasLayer._onLayerDidResize = function guardedOnLayerDidResize(
    this: { _canvas?: HTMLCanvasElement | null },
    resizeEvent: { newSize?: { x: number; y: number } },
  ) {
    if (!this._canvas || !resizeEvent?.newSize) return;
    return onLayerDidResize.call(this, resizeEvent);
  };

  velocityLayerGuardsInstalled = true;
}

const CHIANG_MAI_LANDMARKS = [
  { id: 'doi-suthep', name: 'วัดพระธาตุดอยสุเทพ', category: 'วัด', mood: 'วัฒนธรรม', area: 'อ.เมือง', bestFor: 'แลนด์มาร์กคู่เมืองเชียงใหม่', featured: true, coords: [18.8049, 98.9218] as [number, number] },
  { id: 'tha-phae', name: 'ประตูท่าแพ', category: 'เมืองเก่า', mood: 'วัฒนธรรม', area: 'อ.เมือง', bestFor: 'ใจกลางเมืองเก่าเชียงใหม่', featured: true, coords: [18.7876, 98.9935] as [number, number] },
  { id: 'nimman', name: 'ถนนนิมมานเหมินทร์', category: 'ไลฟ์สไตล์', mood: 'เดินเล่น', area: 'อ.เมือง', bestFor: 'ย่านคาเฟ่และไลฟ์สไตล์', featured: true, coords: [18.7992, 98.9680] as [number, number] },
  { id: 'doi-inthanon', name: 'อุทยานแห่งชาติดอยอินทนนท์', category: 'ธรรมชาติ', mood: 'ธรรมชาติ', area: 'อ.จอมทอง', bestFor: 'ยอดดอยสูงสุดในไทย', featured: true, coords: [18.5875, 98.4864] as [number, number] },
  { id: 'angkaew', name: 'อ่างแก้ว มช.', category: 'ธรรมชาติ', mood: 'ธรรมชาติ', area: 'อ.เมือง', bestFor: 'อ่างเก็บน้ำสวยกลางมหาวิทยาลัย', featured: true, coords: [18.8027, 98.9533] as [number, number] },
  { id: 'chedi-luang', name: 'วัดเจดีย์หลวง', category: 'วัด', mood: 'วัฒนธรรม', area: 'อ.เมือง', bestFor: 'เจดีย์โบราณใจกลางเมือง', featured: true, coords: [18.7863, 98.9862] as [number, number] },
  { id: 'sirikitbotanic', name: 'สวนพฤกษศาสตร์สิริกิติ์', category: 'สวน', mood: 'ดอกไม้', area: 'อ.แม่ริม', bestFor: 'สวนพฤกษศาสตร์ระดับชาติ', featured: true, coords: [18.8968, 98.8600] as [number, number] },
  { id: 'mon-cham', name: 'ม่อนแจ่ม', category: 'ธรรมชาติ', mood: 'ธรรมชาติ', area: 'อ.แม่ริม', bestFor: 'วิวภูเขาและจุดชมทะเลหมอก', featured: true, coords: [18.9358, 98.8224] as [number, number] },
] as const;

export const DRY_FOREST_ZONES = [
  {
    name: 'เขตอุทยานแห่งชาติดอยสุเทพ-ปุย',
    center: [18.81, 98.90],
    radius: 7000,
    ndvi: 0.28,
    status: 'แห้งแล้งจัด (เสี่ยงไฟไหม้สูง)',
  },
  {
    name: 'เขตอุทยานแห่งชาติดอยอินทนนท์',
    center: [18.54, 98.52],
    radius: 9500,
    ndvi: 0.35,
    status: 'แห้งปานกลาง',
  },
  {
    name: 'เขตรักษาพันธุ์สัตว์ป่าเชียงดาว',
    center: [19.40, 98.88],
    radius: 8000,
    ndvi: 0.22,
    status: 'วิกฤตความชื้นต่ำ',
  },
  {
    name: 'เขตป่าสงวนแห่งชาติแม่แจ่ม',
    center: [18.50, 98.37],
    radius: 11000,
    ndvi: 0.25,
    status: 'แห้งแล้งจัด (เสี่ยงไฟไหม้สูง)',
  },
  {
    name: 'เขตป่าต้นน้ำศรีลันนา (แม่แตง)',
    center: [19.16, 99.04],
    radius: 7500,
    ndvi: 0.32,
    status: 'แห้งปานกลาง',
  },
];

type ChiangMaiLandmark = (typeof CHIANG_MAI_LANDMARKS)[number];
type LandmarkKind = 'temple' | 'nature' | 'garden' | 'water' | 'activity' | 'community';

function landmarkKind(landmark: ChiangMaiLandmark): LandmarkKind {
  const text = `${landmark.name} ${landmark.category} ${landmark.mood}`;
  if (text.includes('วัด') || text.includes('เมืองเก่า') || text.includes('วัฒนธรรม')) return 'temple';
  if (text.includes('สวน') || text.includes('ดอกไม้') || text.includes('เกษตร')) return 'garden';
  if (text.includes('น้ำพุร้อน') || text.includes('อ่าง') || text.includes('น้ำ')) return 'water';
  if (text.includes('กิจกรรม') || text.includes('แอดเวนเจอร์') || text.includes('ไลฟ์สไตล์') || text.includes('เดินเล่น')) return 'activity';
  if (text.includes('ชุมชน') || text.includes('นาขั้นบันได')) return 'community';
  return 'nature';
}

function landmarkKindLabel(kind: LandmarkKind) {
  return {
    temple: 'วัด',
    nature: 'ดอย',
    garden: 'สวน',
    water: 'น้ำ',
    activity: 'กิจ',
    community: 'ชุม',
  }[kind];
}

function landmarkSelection(landmark: ChiangMaiLandmark, dashboard: DashboardResponse): MapSelection {
  const pm25 = dashboard.pm25.current_pm25;
  const kind = landmarkKind(landmark);
  return {
    eyebrow: `สถานที่เสริม · ${landmark.category} · ${landmark.area}`,
    title: landmark.name,
    detail: `${landmark.bestFor} (${landmark.category}, ${landmark.area}) ใช้เป็นบริบทเสริมเมื่อประเมินผลกระทบต่อพื้นที่ท่องเที่ยวและชุมชนใกล้เคียง`,
    mapUrl: `https://www.google.com/maps?q=${landmark.coords[0]},${landmark.coords[1]}`,
    imageKey: 'landmark',
    imageLabel: landmark.name,
    stats: [
      { label: 'ประเภท', value: landmarkKindLabel(kind) },
      { label: 'จุดเด่น', value: landmark.bestFor },
      { label: 'PM2.5 วันนี้', value: formatPm25(pm25), tone: pm25Tone(pm25) },
      { label: 'ลม', value: `ไป${windDestinationName(dashboard.weather.wind_direction_deg)}` },
    ],
  };
}

// ─────────────────────────────────────────────
// Initial / default selection
// ─────────────────────────────────────────────

// Component
// ─────────────────────────────────────────────

export function DashboardMap({
  dashboard,
  layers,
  selection,
  onSelectionChange,
  uiMode,
  theme,
  userLocation,
  onMapClick,
  isPinningMode,
  onPinningModeChange,
  isFullscreen,
  onToggleFullscreen,
}: Props) {
  const mapDivRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const hotspotsLayerRef = useRef<L.LayerGroup | null>(null);
  const pm25LayerRef = useRef<L.LayerGroup | null>(null);
  const landmarksLayerRef = useRef<L.LayerGroup | null>(null);
  const plumesLayerRef = useRef<L.LayerGroup | null>(null);
  const fuelRiskLayerRef = useRef<L.LayerGroup | null>(null);
  const userLocationLayerRef = useRef<L.LayerGroup | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const velocityLayerRef = useRef<L.Layer | null>(null);

  const [windParticlesOn, setWindParticlesOn] = useState(false);

  const onSelChangeRef = useRef(onSelectionChange);
  const onMapClickRef = useRef(onMapClick);
  const isPinningRef = useRef(false);
  const onPinningChangeRef = useRef(onPinningModeChange);

  useEffect(() => {
    onSelChangeRef.current = onSelectionChange;
    onMapClickRef.current = onMapClick;
    isPinningRef.current = isPinningMode ?? false;
    onPinningChangeRef.current = onPinningModeChange;
  });

  // Zoom level as React state — triggers marker rebuild only on tier boundary crossings
  const [zoom, setZoom] = useState(9);
  const [baseMapId, setBaseMapId] = useState<BaseMapId>('terrain');

  const pinHomeFromMapEvent = (e: L.LeafletMouseEvent) => {
    if (!isPinningRef.current || !onMapClickRef.current) return false;
    onMapClickRef.current([e.latlng.lat, e.latlng.lng]);
    onPinningChangeRef.current?.(false);
    return true;
  };

  // ── Initialise Leaflet map (once) ──────────────────────────────────────────
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return;

    const map = L.map(mapDivRef.current, {
      center: [18.78, 98.98],
      zoom: 9,
      minZoom: 7,
      maxZoom: 14,
      // Pan limit: CM + surrounding provinces (Mae Hong Son, Chiang Rai, Phayao, Lampang, Lamphun, Tak)
      maxBounds: L.latLngBounds([[16.8, 96.6], [21.2, 101.4]]),
      maxBoundsViscosity: 0.85,
      zoomControl: false, // we render our own buttons
      touchZoom: true,
      // tap: false handled below via CSS touch-action
      doubleClickZoom: true,
      scrollWheelZoom: true,
    });

    tileLayerRef.current = createBaseTileLayer('terrain').addTo(map);

    // Leaflet built-in scale bar (replaces our static "20 km")
    L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);

    // ── Static layers ─────────────────────────────────────────────────────────

    // 1. World-minus-CM mask (dim surrounding area)
    L.geoJSON(maskFeature as any, {
      style: {
        color: 'transparent',
        weight: 0,
        fillColor: '#0d1a15',
        fillOpacity: 0.24,
      },
      interactive: false,
    }).addTo(map);

    // 2. CM province fill (subtle green tint) + strong border
    L.geoJSON(provinceFeature as any, {
      style: {
        color: '#0f6b54',
        weight: 2.5,
        opacity: 0.9,
        fillColor: '#22c55e',
        fillOpacity: 0.05,
        lineJoin: 'round',
      },
      interactive: false,
    }).addTo(map);

    // 3. District boundaries (thin, hover highlight, clickable)
    L.geoJSON(districtsGeoData as any, {
      style: {
        color: '#6aab7a',
        weight: 0.8,
        opacity: 0.45,
        fillColor: 'transparent',
        fillOpacity: 0,
      },
      onEachFeature: (feature, layer) => {
        const nameTh: string = feature.properties?.nameTh || feature.properties?.name || '';
        layer.on({
          click: (e: L.LeafletMouseEvent) => {
            L.DomEvent.stopPropagation(e);
            if (pinHomeFromMapEvent(e)) return;
            onSelChangeRef.current({
              eyebrow: 'อำเภอ',
              title: nameTh,
              detail: 'คลิกจุดข้อมูลเพื่อดูสถานะ PM2.5 หรือจุดความร้อน',
              imageKey: 'district',
              imageLabel: nameTh,
              stats: [
                { label: 'จังหวัด', value: 'เชียงใหม่' },
                { label: 'ชั้นข้อมูล', value: 'ขอบเขตอำเภอ' },
              ],
            });
          },
          mouseover: () => (layer as L.Path).setStyle({ fillOpacity: 0.08, opacity: 0.8 }),
          mouseout: () => (layer as L.Path).setStyle({ fillOpacity: 0, opacity: 0.45 }),
        });
      },
    }).addTo(map);

    // 4. Province title label (DivIcon — fixed pixel size, doesn't scale)
    L.marker([18.6, 98.6], {
      icon: L.divIcon({
        html: '<span class="province-title-label">เชียงใหม่</span>',
        className: '',
        iconSize: [160, 40],
        iconAnchor: [80, 20],
      }),
      interactive: false,
    }).addTo(map);

    // ── Dynamic layer groups ───────────────────────────────────────────────────
    hotspotsLayerRef.current = L.layerGroup().addTo(map);
    pm25LayerRef.current = L.layerGroup().addTo(map);
    landmarksLayerRef.current = L.layerGroup().addTo(map);
    plumesLayerRef.current = L.layerGroup().addTo(map);
    fuelRiskLayerRef.current = L.layerGroup().addTo(map);
    userLocationLayerRef.current = L.layerGroup().addTo(map);

    // Click on blank map → set user location if in pinning mode, else reset selection
    map.on('click', (e: L.LeafletMouseEvent) => {
      if (isPinningRef.current && onMapClickRef.current) {
        onMapClickRef.current([e.latlng.lat, e.latlng.lng]);
        onPinningChangeRef.current?.(false);
      } else {
        onSelChangeRef.current(initialSelection);
      }
    });

    // Track zoom for React re-renders (controls zoom readout + marker tier)
    map.on('zoomend', () => setZoom(map.getZoom()));

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      tileLayerRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Basemap switching ─────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }
    const nextLayer = createBaseTileLayer(baseMapId);
    nextLayer.addTo(map);
    nextLayer.setZIndex(0);
    tileLayerRef.current = nextLayer;
  }, [baseMapId]);

  // ── Hotspot markers (rebuild on data/toggle/zoom) ──────────────────────────
  useEffect(() => {
    const group = hotspotsLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.hotspots) return;

    // Zoom tiers (matches Leaflet tile-zoom levels):
    //   sm  ≤ 9  → icon only, no label
    //   md 10–11 → icon + abbreviated district name
    //   lg ≥ 12  → icon + full district·subdistrict
    const tier = zoom <= 9 ? 'sm' : zoom <= 11 ? 'md' : 'lg';
    const size = tier === 'sm' ? 20 : tier === 'md' ? 26 : 34;

    dashboard.hotspots.items.forEach((h) => {
      const isForest = h.landuse_type && h.landuse_type !== 'OTHER';
      const labelHtml =
        tier !== 'sm' && h.district
          ? `<span class="lf-hotspot__label">${
              tier === 'lg' && h.subdistrict
                ? `อ.${h.district} · ต.${h.subdistrict}`
                : `อ.${h.district}`
            }</span>`
          : '';

      const icon = L.divIcon({
        html: `<div class="lf-hotspot${isForest ? ' lf-hotspot--forest' : ''}" style="width:${size}px;height:${size}px">
          <div class="lf-hotspot__halo"></div>
          <span class="lf-hotspot__fire" aria-hidden="true" style="font-size:${Math.round(size * 0.72)}px"></span>
          ${labelHtml}
        </div>`,
        className: 'lf-marker-wrap',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });

      L.marker([h.latitude, h.longitude], { icon, zIndexOffset: 100 })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          if (pinHomeFromMapEvent(e)) return;
          const loc = hotspotLocation(h);
          onSelChangeRef.current({
            eyebrow: 'จุดความร้อน',
            title: hotspotPlaceTitle(h),
            detail: `${loc ? `${loc} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
            mapUrl: `https://www.google.com/maps?q=${h.latitude},${h.longitude}`,
            imageKey: hotspotImageKey(h),
            imageLabel: hotspotPlaceTitle(h),
            stats: hotspotStats(h),
          });
        })
        .on('mouseover', () => {
          if (isPinningRef.current) return;
          const loc = hotspotLocation(h);
          onSelChangeRef.current({
            eyebrow: 'จุดความร้อน',
            title: hotspotPlaceTitle(h),
            detail: `${loc ? `${loc} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
            mapUrl: `https://www.google.com/maps?q=${h.latitude},${h.longitude}`,
            imageKey: hotspotImageKey(h),
            imageLabel: hotspotPlaceTitle(h),
            stats: hotspotStats(h),
          });
        })
        .addTo(group);
    });
  }, [dashboard.hotspots.items, layers.hotspots, zoom]);

  // ── PM2.5 markers (rebuild on data/toggle/zoom) ────────────────────────────
  useEffect(() => {
    const group = pm25LayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.pm25) return;

    const tier = zoom <= 9 ? 'sm' : zoom <= 11 ? 'md' : 'lg';
    const size = tier === 'sm' ? 28 : tier === 'md' ? 36 : 44;
    const currentPm25 = dashboard.pm25.current_pm25;

    // Plume circles use L.circle (radius in metres) → scale naturally with zoom
    L.circle([18.78, 98.6], {
      radius: plumeRadiusMeters(currentPm25) * 1.35,
      className: `lf-pm-plume lf-pm-plume--${pm25Tone(currentPm25)}`,
      interactive: false,
    }).addTo(group);

    dashboard.pm25.stations.forEach((s) => {
      L.circle([s.latitude, s.longitude], {
        radius: plumeRadiusMeters(s.pm25),
        className: `lf-pm-plume lf-pm-plume--${pm25Tone(s.pm25)}`,
        interactive: false,
      }).addTo(group);
    });

    // Province aggregate station (slightly larger marker)
    const aggSize = Math.round(size * 1.35);
    const aggLabelHtml =
      tier !== 'sm' ? `<span class="lf-station__label">เฉลี่ยจังหวัด</span>` : '';
    const aggSel: MapSelection = {
      eyebrow: 'ค่าเฉลี่ยจังหวัด',
      title: 'PM2.5 เชียงใหม่',
      detail: `${formatPm25(currentPm25)} · ${dashboard.pm25.category} · อัปเดต ${formatTime(dashboard.pm25.latest_update)}`,
      imageKey: 'province',
      imageLabel: 'Chiang Mai province',
      stats: [
        { label: 'PM2.5 เฉลี่ย', value: formatPm25(currentPm25), tone: pm25Tone(currentPm25) },
        { label: 'สถานี', value: `${dashboard.pm25.stations.length} จุด` },
      ],
    };

    const aggIcon = L.divIcon({
      html: `<div class="lf-station lf-station--agg" style="background:${pm25Color(currentPm25)};width:${aggSize}px;height:${aggSize}px">
        <span class="lf-station__value">${pm25ValueLabel(currentPm25)}</span>
        ${aggLabelHtml}
      </div>`,
      className: 'lf-marker-wrap',
      iconSize: [aggSize, aggSize],
      iconAnchor: [aggSize / 2, aggSize / 2],
    });
    L.marker([18.78, 98.6], { icon: aggIcon, zIndexOffset: 200 })
      .on('click', (e: L.LeafletMouseEvent) => {
        L.DomEvent.stopPropagation(e);
        if (pinHomeFromMapEvent(e)) return;
        onSelChangeRef.current(aggSel);
      })
      .on('mouseover', () => {
        if (!isPinningRef.current) onSelChangeRef.current(aggSel);
      })
      .addTo(group);

    // Individual station markers
    dashboard.pm25.stations.forEach((s) => {
      const stName =
        tier === 'lg' ? (s.name.trim() || s.id) : s.district || '';
      const stLabelHtml =
        tier !== 'sm' && stName
          ? `<span class="lf-station__label">${stName}</span>`
          : '';
      const qualityLabel = s.pm25 <= 25 ? 'ดีมาก' : s.pm25 <= 37 ? 'ดี' : s.pm25 <= 50 ? 'ปานกลาง' : s.pm25 <= 90 ? 'เริ่มมีผลกระทบ' : 'อันตราย';
      const healthAdvice = s.pm25 <= 37 ? 'ปลอดภัยสำหรับทุกคน' : s.pm25 <= 50 ? 'กลุ่มเสี่ยงควรระวัง' : 'หลีกเลี่ยงกิจกรรมกลางแจ้ง';
      const next: MapSelection = {
        eyebrow: 'สถานีวัด PM2.5',
        title: s.name.trim() || s.id,
        detail: `${formatPm25(s.pm25)} · ${qualityLabel} · อัปเดต ${formatTime(s.updated_at)} · ${s.district}`,
        imageKey: stationImageKey(s),
        imageLabel: s.name.trim() || s.id,
        stats: [
          { label: 'PM2.5', value: formatPm25(s.pm25), tone: pm25Tone(s.pm25) },
          { label: 'ระดับคุณภาพอากาศ', value: qualityLabel, tone: pm25Tone(s.pm25) },
          { label: 'คำแนะนำสุขภาพ', value: healthAdvice, tone: pm25Tone(s.pm25) },
          { label: 'อำเภอ', value: s.district },
          { label: 'อัปเดต', value: formatTime(s.updated_at) },
        ],
      };

      const stIcon = L.divIcon({
        html: `<div class="lf-station" style="background:${pm25Color(s.pm25)};width:${size}px;height:${size}px">
          <span class="lf-station__value">${pm25ValueLabel(s.pm25)}</span>
          ${stLabelHtml}
        </div>`,
        className: 'lf-marker-wrap',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      L.marker([s.latitude, s.longitude], { icon: stIcon, zIndexOffset: 150 })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          if (pinHomeFromMapEvent(e)) return;
          onSelChangeRef.current(next);
        })
        .on('mouseover', () => {
          if (!isPinningRef.current) onSelChangeRef.current(next);
        })
        .addTo(group);
    });
  }, [dashboard.pm25, layers.pm25, zoom]);

  // ── Chiang Mai landmarks (tourism layer) ───────────────────────────────────
  useEffect(() => {
    const group = landmarksLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.landmarks) return;

    const tier = zoom <= 8 ? 'sm' : zoom <= 10 ? 'md' : 'lg';
    const size = tier === 'sm' ? 16 : tier === 'md' ? 21 : 27;

    CHIANG_MAI_LANDMARKS.forEach((landmark) => {
      const showLabel = tier === 'lg' || (tier === 'md' && zoom >= 10 && 'featured' in landmark && landmark.featured);
      const kind = landmarkKind(landmark);
      const labelHtml =
        showLabel
          ? `<span class="lf-landmark__label">${landmark.name}</span>`
          : '';
      const icon = L.divIcon({
        html: `<div class="lf-landmark lf-landmark--${kind}" style="width:${size}px;height:${size}px">
          <span class="lf-landmark__pin">${landmarkKindLabel(kind)}</span>
          ${labelHtml}
        </div>`,
        className: 'lf-marker-wrap',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      const next = landmarkSelection(landmark, dashboard);

      L.marker(landmark.coords, { icon, zIndexOffset: 35 })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          if (pinHomeFromMapEvent(e)) return;
          onSelChangeRef.current(next);
        })
        .on('mouseover', () => {
          if (!isPinningRef.current) onSelChangeRef.current(next);
        })
        .addTo(group);
    });
  }, [dashboard, layers.landmarks, zoom]);

  // ── Windy-style wind particles from the current TMD AWS station reading ───
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Tear down when the layer is toggled off.
    if (!layers.wind) {
      if (velocityLayerRef.current) {
        map.removeLayer(velocityLayerRef.current);
        velocityLayerRef.current = null;
      }
      setWindParticlesOn(false);
      return;
    }

    const data = buildWindFieldFromStation(
      dashboard.weather.wind_speed_kmh,
      dashboard.weather.wind_direction_deg,
      dashboard.weather.latest_update,
    );
    if (velocityLayerRef.current) {
      map.removeLayer(velocityLayerRef.current);
      velocityLayerRef.current = null;
    }
    ensureVelocityLayerGuards();
    const layer = (L as any).velocityLayer({
      displayValues: false,
      data,
      minVelocity: 0,
      maxVelocity: 10,
      velocityScale: 0.01,
      particleAge: 120,
      particleMultiplier: 1 / 200,
      lineWidth: 2.5,
      frameRate: 30,
      opacity: 0.22,
      colorScale: ['#2f7ad1', '#45a6d9', '#75c7e5', '#a8dfee'],
    });
    layer.addTo(map);
    velocityLayerRef.current = layer;
    setWindParticlesOn(true);

    return () => {
      if (velocityLayerRef.current && mapRef.current) {
        mapRef.current.removeLayer(velocityLayerRef.current);
        velocityLayerRef.current = null;
      }
    };
  }, [dashboard.weather.latest_update, dashboard.weather.wind_direction_deg, dashboard.weather.wind_speed_kmh, layers.wind]);

  // ── Plume vectors (rebuild on data/toggle/wind change) ──────────────────────
  useEffect(() => {
    const group = plumesLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.hotspots || !layers.wind) return;

    const windDir = dashboard.weather.wind_direction_deg;
    const windSpeed = dashboard.weather.wind_speed_kmh;
    
    // Meteorological wind angle (coming from). Convert to blowing towards:
    const blowingTowardsRad = ((windDir + 180) * Math.PI) / 180;
    
    // Plume length (approx 4km to 20km)
    const length = 0.025 + Math.min(0.09, (windSpeed / 32) * 0.09); 
    const spreadHalfRad = 0.3; // ~17 degrees spread on each side

    dashboard.hotspots.items.forEach((h) => {
      const lat0 = h.latitude;
      const lng0 = h.longitude;

      const angle1 = blowingTowardsRad - spreadHalfRad;
      const angle2 = blowingTowardsRad + spreadHalfRad;
      const latScale = Math.cos((lat0 * Math.PI) / 180);

      const lat1 = lat0 + length * Math.cos(angle1);
      const lng1 = lng0 + (length * Math.sin(angle1)) / latScale;

      const lat2 = lat0 + length * Math.cos(angle2);
      const lng2 = lng0 + (length * Math.sin(angle2)) / latScale;

      L.polygon([[lat0, lng0], [lat1, lng1], [lat2, lng2]], {
        color: '#f97316',
        weight: 1,
        fillColor: '#f97316',
        fillOpacity: 0.16,
        className: 'lf-smoke-plume',
        interactive: false,
      }).addTo(group);
    });
  }, [dashboard.hotspots.items, dashboard.weather.wind_direction_deg, dashboard.weather.wind_speed_kmh, layers.hotspots, layers.wind]);

  // ── Sentinel NDVI Fuel Load Layer ──────────────────────────────────────────
  useEffect(() => {
    const group = fuelRiskLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.fuelRisk) return;

    DRY_FOREST_ZONES.forEach((zone) => {
      L.circle(zone.center as [number, number], {
        radius: zone.radius,
        color: zone.ndvi <= 0.25 ? '#dc2626' : '#eab308',
        weight: 1.5,
        dashArray: '4, 6',
        fillColor: '#dc2626',
        fillOpacity: 0.12,
        className: 'lf-fuel-zone',
      })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          if (pinHomeFromMapEvent(e)) return;
          onSelChangeRef.current({
            eyebrow: 'Space Tech · Sentinel-2 NDVI',
            title: zone.name,
            detail: `วิเคราะห์พื้นที่ป่าสงวนจากภาพถ่ายดัชนีความแห้งแล้ง (NDWI/NDVI) พบสภาพ ${zone.status}`,
            imageKey: 'forest',
            imageLabel: zone.name,
            stats: [
              { label: 'ดัชนี NDVI', value: zone.ndvi.toString(), tone: zone.ndvi <= 0.25 ? 'risk' : 'watch' },
              { label: 'ระดับความแห้ง', value: zone.ndvi <= 0.25 ? 'แห้งแล้งวิกฤต' : 'แห้งแล้งปานกลาง' },
              { label: 'สถานะเชื้อเพลิง', value: 'มีเศษใบไม้แห้งหนาแน่น', tone: 'risk' },
            ],
          });
        })
        .on('mouseover', () => {
          if (isPinningRef.current) return;
          onSelChangeRef.current({
            eyebrow: 'Space Tech · Sentinel-2 NDVI',
            title: zone.name,
            detail: `วิเคราะห์พื้นที่ป่าสงวนจากภาพถ่ายดัชนีความแห้งแล้ง (NDWI/NDVI) พบสภาพ ${zone.status}`,
            imageKey: 'forest',
            imageLabel: zone.name,
            stats: [
              { label: 'ดัชนี NDVI', value: zone.ndvi.toString(), tone: zone.ndvi <= 0.25 ? 'risk' : 'watch' },
              { label: 'ระดับความแห้ง', value: zone.ndvi <= 0.25 ? 'แห้งแล้งวิกฤต' : 'แห้งแล้งปานกลาง' },
              { label: 'สถานะเชื้อเพลิง', value: 'มีเศษใบไม้แห้งหนาแน่น', tone: 'risk' },
            ],
          });
        })
        .addTo(group);
    });
  }, [layers.fuelRisk]);

  // ── User location marker and nearest hotspot link line ────────────────────
  useEffect(() => {
    const group = userLocationLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!userLocation) return;

    const userIcon = L.divIcon({
      html: `<div class="lf-user-home">
        <span class="lf-user-home__pulse"></span>
        <span class="lf-user-home__icon">🏠</span>
      </div>`,
      className: 'lf-marker-wrap',
      iconSize: [38, 38],
      iconAnchor: [19, 19],
    });

    L.marker(userLocation, { icon: userIcon, zIndexOffset: 300 }).addTo(group);

    let nearest: Hotspot | null = null;
    let minD = Infinity;
    dashboard.hotspots.items.forEach((h) => {
      const d = getDistanceKm(userLocation[0], userLocation[1], h.latitude, h.longitude);
      if (d < minD) {
        minD = d;
        nearest = h;
      }
    });

    if (nearest) {
      const d = minD;
      const line = L.polyline([userLocation, [(nearest as Hotspot).latitude, (nearest as Hotspot).longitude]], {
        color: '#dc2626',
        weight: 2.5,
        dashArray: '6, 10',
        opacity: 0.85,
      }).addTo(group);

      line.bindTooltip(`${d.toFixed(1)} กม.`, {
        permanent: true,
        direction: 'center',
        className: 'lf-distance-tooltip',
      });

      mapRef.current?.panTo(userLocation, { animate: true });
    }
  }, [userLocation, dashboard.hotspots.items]);

  // ── Zoom controls ─────────────────────────────────────────────────────────
  const handleZoomIn = useCallback(() => mapRef.current?.zoomIn(), []);
  const handleZoomOut = useCallback(() => mapRef.current?.zoomOut(), []);
  const handleReset = useCallback(() => {
    mapRef.current?.setView([18.78, 98.98], 9, { animate: true });
    onSelectionChange(initialSelection);
  }, [onSelectionChange]);

  // ── Wind ──────────────────────────────────────────────────────────────────
  const windRotation = dashboard.weather.wind_direction_deg + 180;
  const windSpeed = dashboard.weather.wind_speed_kmh;
  const windSourceText = dashboard.weather.wind_direction_text;
  const windDestinationText = windDestinationName(dashboard.weather.wind_direction_deg);

  const windSelection: MapSelection = {
    eyebrow: 'ทิศทางลม',
    title: `ไปทาง${windDestinationText}`,
    detail: `${windSpeed} km/h · ลมมาจาก${windSourceText} แล้วพัดไปทาง${windDestinationText} · อัปเดต ${formatTime(dashboard.weather.latest_update)}`,
    imageKey: 'wind',
    imageLabel: 'Wind layer',
    stats: [
      { label: 'ความเร็ว', value: `${windSpeed} km/h` },
      { label: 'มาจาก', value: windSourceText },
      { label: 'ไปทาง', value: windDestinationText },
    ],
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="map-canvas">
      {/* Leaflet map mount point */}
      <div ref={mapDivRef} className={`map-leaflet${isPinningMode ? ' map-pinning' : ''}`} />

      {/* Wind chip button */}
      {layers.wind && (
        <button
          type="button"
          className={`wind-chip${windParticlesOn ? '' : ' wind-chip--loading'}`}
          onClick={() => onSelectionChange(windSelection)}
          aria-label={`ลมไปทาง${windDestinationText} ${windSpeed} km/h`}
        >
          <span className="wind-chip__compass" style={{ transform: `rotate(${windRotation}deg)` }}>
            <Wind size={15} />
          </span>
          <span className="wind-chip__text">
            <b>ไป{windDestinationText}</b>
            <small>{windSpeed} km/h</small>
          </span>
        </button>
      )}

      <div className="map-help">ลากเพื่อเลื่อน · เลื่อนเมาส์เพื่อซูม · คลิกจุดข้อมูล</div>

      <div className="map-legend">
        <span><i className="dot dot--pm" />สถานีวัด PM2.5</span>
        <span><i className="fire-ic">🔥</i>จุดความร้อน</span>
        {layers.fuelRisk && <span><i className="dot dot--fuel" />ดัชนีป่าแห้ง NDVI</span>}
        {layers.hotspots && layers.wind && <span><i className="cone-ic" />ขอบเขตควันลอย</span>}
        {layers.landmarks && <span><i className="landmark-ic" />แลนด์มาร์ก</span>}
        <span><i className="arrow-ic">↑</i>ทิศลม TMD</span>
      </div>

      <div className="basemap-switcher" aria-label="เลือกพื้นแผนที่">
        {BASEMAPS.map((basemap) => (
          <button
            key={basemap.id}
            type="button"
            className={baseMapId === basemap.id ? 'active' : ''}
            onClick={() => setBaseMapId(basemap.id)}
          >
            {basemap.label}
          </button>
        ))}
      </div>

      <div className="map-controls">
        <span className="zoom-readout">ซูม {zoom}</span>
        <button type="button" aria-label="ขยาย" onClick={handleZoomIn}>
          <Plus size={18} />
        </button>
        <button type="button" aria-label="ย่อ" onClick={handleZoomOut}>
          <Minus size={18} />
        </button>
        <button type="button" aria-label="กลับสู่มุมมองเริ่มต้น" onClick={handleReset}>
          <Crosshair size={18} />
        </button>
        {onToggleFullscreen && (
          <button
            type="button"
            aria-label={isFullscreen ? 'ย่อแผนที่' : 'ขยายแผนที่เต็มจอ'}
            className={`map-fullscreen-btn${isFullscreen ? ' active' : ''}`}
            onClick={() => {
              onToggleFullscreen();
              // Give Leaflet a frame to pick up the new container size
              setTimeout(() => mapRef.current?.invalidateSize(), 120);
            }}
          >
            {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
          </button>
        )}
      </div>

      {/* Fullscreen-only: the map-detail-bar lives outside the map, so in
          fullscreen we surface the tapped feature's info on the map itself. */}
      {isFullscreen && (
        <div className="map-fs-detail" aria-live="polite">
          {selection.eyebrow && <span className="map-fs-detail__eyebrow">{selection.eyebrow}</span>}
          <strong className="map-fs-detail__title">{selection.title}</strong>
          {selection.detail && <p className="map-fs-detail__text">{selection.detail}</p>}
          {selection.stats && selection.stats.length > 0 && (
            <div className="map-fs-detail__stats">
              {selection.stats.slice(0, 6).map((stat) => (
                <div
                  key={`${stat.label}-${stat.value}`}
                  className={`map-fs-stat${stat.tone ? ` map-fs-stat--${stat.tone}` : ''}`}
                >
                  <span>{stat.label}</span>
                  <b>{stat.value}</b>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


