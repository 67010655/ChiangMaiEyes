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

function googleMapsSearchUrl(name: string, area: string) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${name} ${area} เชียงใหม่`)}`;
}

const WONGNAI_CHIANGMAI_TRIP_URL = 'https://www.wongnai.com/trips/travel-at-chiangmai';

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

const CHIANG_MAI_LANDMARKS = [
  {
    rank: 1,
    id: 'wongnai-1',
    name: "วัดพระธาตุดอยสุเทพราชวรวิหาร",
    url: "https://www.wongnai.com/attractions/324436dw-วัดพระธาตุดอยสุเทพราชวรวิหาร",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.เมืองเชียงใหม่",
    address: "สุเทพ, เชียงใหม่, จ.เชียงใหม่, 50200, ประเทศไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "แลนด์มาร์กคู่เมืองและวิวเชียงใหม่",
    featured: true,
    coords: [18.805091, 98.921471] as [number, number],
  },
  {
    rank: 2,
    id: 'wongnai-2',
    name: "One Nimman",
    url: "https://www.wongnai.com/attractions/340131EJ-one-nimman",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.เมืองเชียงใหม่",
    address: "ถนน นิมมานเหมินทร์",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "ย่านเดินเล่น ร้านอาหาร และมุมถ่ายรูป",
    featured: true,
    coords: [18.800000368388126, 98.96800240608218] as [number, number],
  },
  {
    rank: 3,
    id: 'wongnai-3',
    name: "ถนนคนเดินวัวลาย",
    url: "https://www.wongnai.com/attractions/330323yo-ถนนคนเดินวัวลาย-เชียงใหม่",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.เมืองเชียงใหม่",
    address: "ถนน วัวลาย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "อาหาร ของฝาก และงานคราฟต์กลางคืน",
    featured: false,
    coords: [18.7808949, 98.987767] as [number, number],
  },
  {
    rank: 4,
    id: 'wongnai-4',
    name: "ถนนคนเดินท่าแพ",
    url: "https://www.wongnai.com/attractions/337475Mf-ถนนคนเดินท่าแพ",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.เมืองเชียงใหม่",
    address: "ถนน คนเดินท่าแพ",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "อาหาร ของฝาก และงานคราฟต์กลางคืน",
    featured: true,
    coords: [18.787942628930153, 98.99136370066378] as [number, number],
  },
  {
    rank: 5,
    id: 'wongnai-5',
    name: "อ่างแก้ว",
    url: "https://www.wongnai.com/attractions/342238oe-อ่างแก้ว-มหาวิทยาลัยเชียงใหม่",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.เมืองเชียงใหม่",
    address: "ถนน นครพิงค์",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [18.806901, 98.951137] as [number, number],
  },
  {
    rank: 6,
    id: 'wongnai-6',
    name: "วัดพระธาตุดอยคำ",
    url: "https://www.wongnai.com/attractions/324827cg-วัดพระธาตุดอยคำ-วัดสุวรรณบรรพต",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.เมืองเชียงใหม่",
    address: "ถนนหมู่บ้านเชียงใหม่เลคแลนด์",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.759628920202136, 98.91870297572086] as [number, number],
  },
  {
    rank: 7,
    id: 'wongnai-7',
    name: "วัดอุโมงค์ (วัดสวนพุทธธรรม)",
    url: "https://www.wongnai.com/attractions/324434eD-วัดอุโมงค์-วัดสวนพุทธธรรม",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.เมืองเชียงใหม่",
    address: "135 หมู่ที่ 10 ซอย บ้านใหม่หลังมอ",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.78354413260747, 98.95123193277334] as [number, number],
  },
  {
    rank: 8,
    id: 'wongnai-8',
    name: "บ้านข้างวัด",
    url: "https://www.wongnai.com/attractions/326929QW-บ้านข้างวัด",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.เมืองเชียงใหม่",
    address: "191-197 5 ถนน คำหยาดฟ้า",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.77633696707432, 98.94840654232786] as [number, number],
  },
  {
    rank: 9,
    id: 'wongnai-9',
    name: "ศูนย์พัฒนาโครงการหลวงขุนแปะ",
    url: "https://www.wongnai.com/attractions/350644bL-ศูนย์พัฒนาโครงการหลวง-ขุนแปะ",
    category: "เมืองเก่า / ไลฟ์สไตล์",
    mood: "เมืองเก่า / ไลฟ์สไตล์",
    area: "อ.เมืองเชียงใหม่",
    address: "ถนน บ้านขุนแปะ",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เมืองเชียงใหม่ ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.3117417, 98.47984640000004] as [number, number],
  },
  {
    rank: 10,
    id: 'wongnai-10',
    name: "อุทยานแห่งชาติดอยอินทนนท์",
    url: "https://www.wongnai.com/attractions/324494Sm-อุทยานแห่งชาติดอยอินทนนท์",
    category: "ดอยอินทนนท์ / ธรรมชาติ",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.จอมทอง",
    address: "ถนน บ้านหลวง ซอย 2",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.จอมทอง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "ยอดดอย อากาศเย็น และน้ำตก",
    featured: true,
    coords: [18.53664331, 98.52089544] as [number, number],
  },
  {
    rank: 11,
    id: 'wongnai-11',
    name: "เส้นทางศึกษาธรรมชาติกิ่วแม่ปาน",
    url: "https://www.wongnai.com/attractions/325949Yd-เส้นทางศึกษาธรรมชาติกิ่วแม่ปาน",
    category: "ดอยอินทนนท์ / ธรรมชาติ",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.จอมทอง",
    address: "ทางหลวงแผ่นดินหมายเลข 1009",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.จอมทอง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "เส้นทางเดินชมธรรมชาติและทะเลหมอก",
    featured: true,
    coords: [18.55616462, 98.48200362] as [number, number],
  },
  {
    rank: 12,
    id: 'wongnai-12',
    name: "สถานีเกษตรหลวงอินทนนท์",
    url: "https://www.wongnai.com/attractions/325079vG-สถานีเกษตรหลวงอินทนนท์",
    category: "ดอยอินทนนท์ / ธรรมชาติ",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.จอมทอง",
    address: "ทางหลวงหมายเลข 1284",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.จอมทอง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.542625377706187, 98.51940349384108] as [number, number],
  },
  {
    rank: 13,
    id: 'wongnai-13',
    name: "น้ำตกสิริภูมิ",
    url: "https://www.wongnai.com/attractions/324828st-น้ำตกสิริภูมิ",
    category: "ดอยอินทนนท์ / ธรรมชาติ",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.จอมทอง",
    address: "ถนน บ้านหลวง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.จอมทอง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.54695758, 98.51223635] as [number, number],
  },
  {
    rank: 14,
    id: 'wongnai-14',
    name: "บ้านป่าบงเปียง",
    url: "https://www.wongnai.com/attractions/330524pZ-บ้านป่าบงเปียง",
    category: "นาขั้นบันได / ชุมชน",
    mood: "นาขั้นบันได / ชุมชน",
    area: "อ.แม่แจ่ม",
    address: "197 หมู่13 ทางหลวงหมายเลข 1192",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "นาขั้นบันไดและวิวชนบท",
    featured: true,
    coords: [18.532946, 98.447244] as [number, number],
  },
  {
    rank: 15,
    id: 'wongnai-15',
    name: "น้ำแม่ออกฮู",
    url: "https://www.wongnai.com/attractions/353079DR-น้ำแม่ออกฮู",
    category: "นาขั้นบันได / ชุมชน",
    mood: "นาขั้นบันได / ชุมชน",
    area: "อ.แม่แจ่ม",
    address: "ทางหลวงแผ่นดิน หมายเลข 1088",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.546885032053353, 98.38272891783231] as [number, number],
  },
  {
    rank: 16,
    id: 'wongnai-16',
    name: "ดอยม่อนหมาก",
    url: "https://www.wongnai.com/attractions/1592733Av-%E0%B8%94%E0%B8%AD%E0%B8%A2%E0%B8%A1%E0%B9%88%E0%B8%AD%E0%B8%99%E0%B8%AB%E0%B8%A1%E0%B8%B2%E0%B8%81",
    category: "นาขั้นบันได / ชุมชน",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แจ่ม",
    address: "Unnamed Road ตำบล ท่าผา อำเภอแม่แจ่ม เชียงใหม่ 50270 ไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.46091, 98.3504171] as [number, number],
  },
  {
    rank: 17,
    id: 'wongnai-17',
    name: "นาข้าวขั้นบันได บ้านกองกาน",
    url: "https://www.wongnai.com/attractions/1592865On-%E0%B8%99%E0%B8%B2%E0%B8%82%E0%B9%89%E0%B8%B2%E0%B8%A7%E0%B8%82%E0%B8%B1%E0%B9%89%E0%B8%99%E0%B8%9A%E0%B8%B1%E0%B8%99%E0%B9%84%E0%B8%94-%E0%B8%9A%E0%B9%89%E0%B8%B2%E0%B8%99%E0%B8%81%E0%B8%AD%E0%B8%87%E0%B8%81%E0%B8%B2%E0%B8%99",
    category: "นาขั้นบันได / ชุมชน",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.แม่แจ่ม",
    address: "G9W3+MH6 ตำบล แม่ศึก อำเภอแม่แจ่ม เชียงใหม่ 50270 ไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "นาขั้นบันไดและวิวชนบท",
    featured: false,
    coords: [18.546655, 98.353882] as [number, number],
  },
  {
    rank: 18,
    id: 'wongnai-18',
    name: "วัดกองกาน",
    url: "https://www.wongnai.com/attractions/324878yG-%E0%B8%A7%E0%B8%B1%E0%B8%94%E0%B8%81%E0%B8%AD%E0%B8%87%E0%B8%81%E0%B8%B2%E0%B8%99",
    category: "นาขั้นบันได / ชุมชน",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.แม่แจ่ม",
    address: "หมู่ 7",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.54776708, 98.35295695] as [number, number],
  },
  {
    rank: 19,
    id: 'wongnai-19',
    name: "วัดพุทธเอ้น",
    url: "https://www.wongnai.com/attractions/324886TB-%E0%B8%A7%E0%B8%B1%E0%B8%94%E0%B8%9E%E0%B8%B8%E0%B8%97%E0%B8%98%E0%B9%80%E0%B8%AD%E0%B9%89%E0%B8%99",
    category: "นาขั้นบันได / ชุมชน",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.แม่แจ่ม",
    address: "ถนน ช่างเคิ่ง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.51326312128032, 98.35051408611685] as [number, number],
  },
  {
    rank: 20,
    id: 'wongnai-20',
    name: "หมู่บ้านทอผ้าซิ่นตีนจก",
    url: "https://www.wongnai.com/attractions/348698pN-%E0%B8%AB%E0%B8%A1%E0%B8%B9%E0%B9%88%E0%B8%9A%E0%B9%89%E0%B8%B2%E0%B8%99%E0%B8%97%E0%B8%AD%E0%B8%9C%E0%B9%89%E0%B8%B2%E0%B8%8B%E0%B8%B4%E0%B9%88%E0%B8%99%E0%B8%95%E0%B8%B5%E0%B8%99%E0%B8%88%E0%B8%81-%E0%B8%AD%E0%B8%B3%E0%B9%80%E0%B8%A0%E0%B8%AD%E0%B9%81%E0%B8%A1%E0%B9%88%E0%B9%81%E0%B8%88%E0%B9%88%E0%B8%A1",
    category: "นาขั้นบันได / ชุมชน",
    mood: "นาขั้นบันได / ชุมชน",
    area: "อ.แม่แจ่ม",
    address: "ถนน ทางหลวงแผ่นดิน หมายเลข 1088",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แจ่ม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.4915994, 98.36233560000005] as [number, number],
  },
  {
    rank: 21,
    id: 'wongnai-21',
    name: "สวนพฤกษศาสตร์สมเด็จพระนางเจ้าสิริกิติ์",
    url: "https://www.wongnai.com/attractions/324277FT-สวนพฤกษศาสตร์สมเด็จพระนางเจ้าสิริกิติ์",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.แม่ริม",
    address: "ทางหลวงหมายเลข 1096",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [18.896816486288262, 98.86004526826162] as [number, number],
  },
  {
    rank: 22,
    id: 'wongnai-22',
    name: "อุทยานแห่งชาติดอยสุเทพ - ปุย",
    url: "https://www.wongnai.com/attractions/324501gy-อุทยานแห่งชาติดอยสุเทพ-ปุย",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่ริม",
    address: "ทางหลวงหมายเลข 1004",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "แลนด์มาร์กคู่เมืองและวิวเชียงใหม่",
    featured: false,
    coords: [18.8027095, 98.92028219999997] as [number, number],
  },
  {
    rank: 23,
    id: 'wongnai-23',
    name: "น้ำตกแม่สา",
    url: "https://www.wongnai.com/attractions/347929Ye-น้ำตกแม่สา",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่ริม",
    address: "ทางหลวงแผ่นดินหมายเลข 1096",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.906237, 98.89715449999994] as [number, number],
  },
  {
    rank: 24,
    id: 'wongnai-24',
    name: "ม่อนแจ่ม",
    url: "https://www.wongnai.com/attractions/324274Qg-ม่อนแจ่ม",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "สวน / ดอกไม้ / ภูเขา",
    area: "อ.แม่ริม",
    address: "ถนนสาย 1096 น้ำตกแม่สา",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "วิวภูเขาและจุดถ่ายรูป",
    featured: true,
    coords: [18.93576804489993, 98.82241958470513] as [number, number],
  },
  {
    rank: 25,
    id: 'wongnai-25',
    name: "ม่อนอิงดาว",
    url: "https://www.wongnai.com/attractions/364984ym-ม่อนอิงดาว",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "สวน / ดอกไม้ / ภูเขา",
    area: "อ.แม่ริม",
    address: "26/4 หมู่ 7, ตำบลแม่แรม อำเภอแม่ริม, จังหวัดเชียงใหม่ 50180, ประเทศไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "วิวภูเขาและจุดถ่ายรูป",
    featured: false,
    coords: [18.935957, 98.815793] as [number, number],
  },
  {
    rank: 26,
    id: 'wongnai-26',
    name: "โป่งแยงจังเกิลโคสเตอร์และซิปไลน์",
    url: "https://www.wongnai.com/attractions/349985bq-โป่งแยงจังเกิลโคสเตอร์และซิปไลน์",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "สวน / ดอกไม้ / ภูเขา",
    area: "อ.แม่ริม",
    address: "ถนน ทางหลวงแผ่นดิน หมายเลข 4051",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "กิจกรรมสำหรับครอบครัวและกลุ่มเพื่อน",
    featured: false,
    coords: [18.9166373, 98.821483] as [number, number],
  },
  {
    rank: 27,
    id: 'wongnai-27',
    name: "ห้วยตึงเฒ่า (คิงคองยักษ์)",
    url: "https://www.wongnai.com/attractions/340929Aj-ห้วยตึงเฒ่า-คิงคองยักษ์",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "สวน / ดอกไม้ / ภูเขา",
    area: "อ.แม่ริม",
    address: "283 ม.3 ทางหลวงหมายเลข 121",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.867357056972352, 98.94035679600063] as [number, number],
  },
  {
    rank: 28,
    id: 'wongnai-28',
    name: "Elephant Poopoopaper",
    url: "https://www.wongnai.com/attractions/326901tv-เอเลเฟ่นพูพูเปเปอร์พาร์ค",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.แม่ริม",
    address: "ทางหลวงหมายเลข 1096",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.92565239, 98.93159612] as [number, number],
  },
  {
    rank: 29,
    id: 'wongnai-29',
    name: "Into The Flower",
    url: "https://www.wongnai.com/attractions/471836aH-into-the-flower",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.แม่ริม",
    address: "ตำบล เหมืองแก้ว อำเภอแม่ริม เชียงใหม่ 50180",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.8930625, 98.98031249999997] as [number, number],
  },
  {
    rank: 30,
    id: 'wongnai-30',
    name: "I love flower Farm",
    url: "https://www.wongnai.com/attractions/456864qs-i-love-flower-farm",
    category: "สวน / ดอกไม้ / ภูเขา",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.แม่ริม",
    address: "ลานจอดรถชุมชน i love flower farm",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่ริม ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.901101440670505, 98.98050635396731] as [number, number],
  },
  {
    rank: 31,
    id: 'wongnai-31',
    name: "วัดบ้านเด่น",
    url: "https://www.wongnai.com/attractions/324891iJ-วัดเด่นสะหลีศรีเมืองแกน-วัดบ้านเด่น",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.แม่แตง",
    address: "ถนน เชียงใหม่-ฝาง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [19.15773716, 98.97849819] as [number, number],
  },
  {
    rank: 32,
    id: 'wongnai-32',
    name: "เขื่อนแม่งัดสมบูรณ์ชล",
    url: "https://www.wongnai.com/attractions/324831VJ-เขื่อนแม่งัดสมบูรณ์ชล",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แตง",
    address: "ถนน สายเชียงใหม่-ฝาง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [19.16251013, 99.03858621] as [number, number],
  },
  {
    rank: 33,
    id: 'wongnai-33',
    name: "ปางช้างแม่แตง",
    url: "https://www.wongnai.com/attractions/349966Nq-ปางช้างแม่แตง",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.แม่แตง",
    address: "ทางหลวงแผ่นดินหมายเลข 3052",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "กิจกรรมสำหรับครอบครัวและกลุ่มเพื่อน",
    featured: false,
    coords: [19.1981653, 98.88736960000006] as [number, number],
  },
  {
    rank: 34,
    id: 'wongnai-34',
    name: "ไร่ชาลุงเดช",
    url: "https://www.wongnai.com/attractions/335412hg-ไร่ชาลุงเดช",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.แม่แตง",
    address: "ทางหลวงชนบทเชียงใหม่ 3052",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.2059698, 98.7950324] as [number, number],
  },
  {
    rank: 35,
    id: 'wongnai-35',
    name: "อุทยานแห่งชาติห้วยน้ำดัง",
    url: "https://www.wongnai.com/attractions/324383mi-อุทยานแห่งชาติห้วยน้ำดัง",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แตง",
    address: "ถนน ธงชัย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [19.303967428333678, 98.59885028083204] as [number, number],
  },
  {
    rank: 36,
    id: 'wongnai-36',
    name: "น้ำตกหมอกฟ้า",
    url: "https://www.wongnai.com/attractions/324230Zn-น้ำตกหมอกฟ้า",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แตง",
    address: "ถนน สายแม่มาลัย-ปาย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.112764438522014, 98.77469246866781] as [number, number],
  },
  {
    rank: 37,
    id: 'wongnai-37',
    name: "ยอดดอยม่อนเงาะ",
    url: "https://www.wongnai.com/attractions/442270Hv-%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%94%E0%B8%AD%E0%B8%A2%E0%B8%A1%E0%B9%88%E0%B8%AD%E0%B8%99%E0%B9%80%E0%B8%87%E0%B8%B2%E0%B8%B0",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แตง",
    address: "บ้านม่อนเงาะ",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "วิวภูเขาและจุดถ่ายรูป",
    featured: false,
    coords: [19.180456309145473, 98.76809030771255] as [number, number],
  },
  {
    rank: 38,
    id: 'wongnai-38',
    name: "สวนสนแม่แตง",
    url: "https://www.wongnai.com/attractions/352959nj-%E0%B8%AA%E0%B8%A7%E0%B8%99%E0%B8%9C%E0%B8%A5%E0%B8%B4%E0%B8%95%E0%B9%80%E0%B8%A1%E0%B8%A5%E0%B9%87%E0%B8%94%E0%B8%9E%E0%B8%B1%E0%B8%99%E0%B8%98%E0%B8%B8%E0%B9%8C%E0%B9%84%E0%B8%A1%E0%B9%89%E0%B8%AA%E0%B8%99%E0%B8%AA%E0%B8%AD%E0%B8%87%E0%B9%83%E0%B8%9A?_st=cD0wO2I9MzUyOTU5O2FkPWZhbHNlO3Q9MTY1MDcwNDI1Mjc5MDtyaT0xWDdhUzlQQ3RsYlJUQmNLc1Q3SDJLM1JZZjJIOE07aT0xWDZ6dlRBblF2ZkhuNG5BQ3k4QlB0VHJuVFNhU2U7d3JlZj1zcjs%3D",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.แม่แตง",
    address: "ทางหลวงแผ่นดินหมายเลข 107",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.150811, 98.948322] as [number, number],
  },
  {
    rank: 39,
    id: 'wongnai-39',
    name: "อุทยานแห่งชาติ น้ำตกบัวตอง",
    url: "https://www.wongnai.com/attractions/381620Uj-%E0%B8%AD%E0%B8%B8%E0%B8%97%E0%B8%A2%E0%B8%B2%E0%B8%99%E0%B9%81%E0%B8%AB%E0%B9%88%E0%B8%87%E0%B8%8A%E0%B8%B2%E0%B8%95%E0%B8%B4%E0%B8%99%E0%B9%89%E0%B8%B3%E0%B8%95%E0%B8%81%E0%B8%9A%E0%B8%B1%E0%B8%A7%E0%B8%95%E0%B8%AD%E0%B8%87-%E0%B8%99%E0%B9%89%E0%B8%B3%E0%B8%9E%E0%B8%B8%E0%B9%80%E0%B8%88%E0%B9%87%E0%B8%94%E0%B8%AA%E0%B8%B5",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แตง",
    address: "Mae Ho Phra, Mae Taeng, Chiang Mai, 50150, Thailand",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [19.069757, 99.079469] as [number, number],
  },
  {
    rank: 40,
    id: 'wongnai-40',
    name: "บ้านธารกล่อม",
    url: "https://www.wongnai.com/hotels/371324qc-%E0%B8%9A%E0%B9%89%E0%B8%B2%E0%B8%99%E0%B8%98%E0%B8%B2%E0%B8%A3%E0%B8%81%E0%B8%A5%E0%B9%88%E0%B8%AD%E0%B8%A1",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / แอดเวนเจอร์",
    area: "อ.แม่แตง",
    address: "Kuet Chang, Mae Taeng, Chiang Mai, 50150, Thailand",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.232265, 98.879933] as [number, number],
  },
  {
    rank: 41,
    id: 'wongnai-41',
    name: "แก่งกึ๊ด",
    url: "https://www.wongnai.com/attractions/372307Pd-%E0%B9%81%E0%B8%81%E0%B9%88%E0%B8%87%E0%B8%81%E0%B8%B6%E0%B9%8A%E0%B8%94",
    category: "ธรรมชาติ / แอดเวนเจอร์",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.แม่แตง",
    address: "ถนนสาย 3052",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.แม่แตง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.22047941151384, 98.84077113121748] as [number, number],
  },
  {
    rank: 42,
    id: 'wongnai-42',
    name: "ถ้ำเชียงดาว",
    url: "https://www.wongnai.com/attractions/325924Hp-ถ้ำเชียงดาว",
    category: "ถ้ำ / ภูเขา / ชุมชน",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.เชียงดาว",
    address: "ทางหลวงชนบท ชม. 3024",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เชียงดาว ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "ภูเขา ถ้ำ และธรรมชาติทางเหนือ",
    featured: true,
    coords: [19.39418497, 98.9278712] as [number, number],
  },
  {
    rank: 43,
    id: 'wongnai-43',
    name: "ดอยหลวงเชียงดาว",
    url: "https://www.wongnai.com/attractions/324826kS-ดอยหลวงเชียงดาว",
    category: "ถ้ำ / ภูเขา / ชุมชน",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.เชียงดาว",
    address: "ถนน ธงชัย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เชียงดาว ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "ภูเขา ถ้ำ และธรรมชาติทางเหนือ",
    featured: true,
    coords: [19.39986045, 98.87618904] as [number, number],
  },
  {
    rank: 44,
    id: 'wongnai-44',
    name: "โป่งน้ำร้อนบ้านยางปู่โต๊ะ",
    url: "https://www.wongnai.com/attractions/349237Qh-โป่งน้ำร้อนบ้านยางปู่โต๊ะ",
    category: "ถ้ำ / ภูเขา / ชุมชน",
    mood: "ถ้ำ / ภูเขา / ชุมชน",
    area: "อ.เชียงดาว",
    address: "Chiang Dao, Chiang Dao, Chiang Mai, 50170, Thailand",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เชียงดาว ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.362823, 98.923053] as [number, number],
  },
  {
    rank: 45,
    id: 'wongnai-45',
    name: "บ้านแม่แมะ",
    url: "https://www.wongnai.com/attractions/363658ox-บ้านแม่แมะ",
    category: "ถ้ำ / ภูเขา / ชุมชน",
    mood: "ถ้ำ / ภูเขา / ชุมชน",
    area: "อ.เชียงดาว",
    address: "ตำบล แม่นะ อำเภอ เชียงดาว เชียงใหม่ 50170 ประเทศไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.เชียงดาว ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.318542973933873, 98.89069311293224] as [number, number],
  },
  {
    rank: 46,
    id: 'wongnai-46',
    name: "บ่อน้ำพุร้อนฝาง",
    url: "https://www.wongnai.com/attractions/349956Qn-บ่อน้ำพุร้อนฝาง",
    category: "อ่างขาง / น้ำพุร้อน",
    mood: "อ่างขาง / น้ำพุร้อน",
    area: "อ.ฝาง",
    address: "ทางหลวงแผ่นดิน หมายเลข 4050",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.ฝาง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "อากาศเย็นและธรรมชาติบนดอย",
    featured: false,
    coords: [19.965911, 99.15426300000001] as [number, number],
  },
  {
    rank: 47,
    id: 'wongnai-47',
    name: "จุดชมวิวม่อนสน",
    url: "https://www.wongnai.com/hotels/344037Yx-จุดชมวิวม่อนสน",
    category: "อ่างขาง / น้ำพุร้อน",
    mood: "อ่างขาง / น้ำพุร้อน",
    area: "อ.ฝาง",
    address: "อ่างขาง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.ฝาง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [19.86232936853322, 99.05182141810654] as [number, number],
  },
  {
    rank: 48,
    id: 'wongnai-48',
    name: "ดอยอ่างขาง",
    url: "https://www.wongnai.com/attractions/324233Eb-ดอยอ่างขาง",
    category: "อ่างขาง / น้ำพุร้อน",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.ฝาง",
    address: "ทางหลวงหมายเลข 1249",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.ฝาง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "อากาศเย็นและธรรมชาติบนดอย",
    featured: true,
    coords: [19.901050568796965, 99.0400560734887] as [number, number],
  },
  {
    rank: 49,
    id: 'wongnai-49',
    name: "อุทยานแห่งชาติดอยผ้าห่มปก",
    url: "https://www.wongnai.com/attractions/119409jh-อุทยานแห่งชาติดอยผ้าห่มปก",
    category: "อ่างขาง / น้ำพุร้อน",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.ฝาง",
    address: "ทางหลวงหมายเลข 107",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.ฝาง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "อากาศเย็นและธรรมชาติบนดอย",
    featured: false,
    coords: [19.96620616697672, 99.15501576455688] as [number, number],
  },
  {
    rank: 50,
    id: 'wongnai-50',
    name: "สถานีเกษตรหลวงอ่างขาง",
    url: "https://www.wongnai.com/attractions/324249OF-สถานีเกษตรหลวงอ่างขาง",
    category: "อ่างขาง / น้ำพุร้อน",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.ฝาง",
    address: "ถนน แม่งอน-อ่างขาง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.ฝาง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "อากาศเย็นและธรรมชาติบนดอย",
    featured: true,
    coords: [19.90222514, 99.03967207] as [number, number],
  },
  {
    rank: 51,
    id: 'wongnai-51',
    name: "ทุ่งดอกเก๊กฮวย บ้านอมลอง",
    url: "https://www.wongnai.com/attractions/298301WY-ทุ่งดอกเก๊กฮวย-บ้านอมลอง",
    category: "ดอกไม้ / เกษตร",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.สะเมิง",
    address: "ถนน สะเมิง-หางดง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.สะเมิง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.9232365, 98.6050336] as [number, number],
  },
  {
    rank: 52,
    id: 'wongnai-52',
    name: "ศูนย์วิจัยข้าวสะเมิง",
    url: "https://www.wongnai.com/attractions/352747zK-ศูนย์วิจัยข้าวสะเมิง",
    category: "ดอกไม้ / เกษตร",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.สะเมิง",
    address: "202 หมู่ที่ 10 บ้านปางดะ ทางหลวงหมายเลข 1269",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.สะเมิง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.84637, 98.77029779999998] as [number, number],
  },
  {
    rank: 53,
    id: 'wongnai-53',
    name: "ไร่นภ ภูผา",
    url: "https://www.wongnai.com/attractions/326874bN-ไร่นภ-ภูผา",
    category: "ดอกไม้ / เกษตร",
    mood: "ดอกไม้ / เกษตร / ถ่ายรูป",
    area: "อ.สะเมิง",
    address: "156/1 10 ทางหลวงแผ่นดินหมายเลข 1269",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.สะเมิง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.85501479, 98.75225295] as [number, number],
  },
  {
    rank: 54,
    id: 'wongnai-54',
    name: "แกรนด์ แคนยอน (เชียงใหม่)",
    url: "https://www.wongnai.com/attractions/330991ky-แกรนด์-แคนยอน-เชียงใหม่-หางดง",
    category: "กิจกรรม / วัฒนธรรม",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.หางดง",
    address: "ต.น้ำแพร่ อ.หางดง",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.หางดง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "กิจกรรมสำหรับครอบครัวและกลุ่มเพื่อน",
    featured: true,
    coords: [18.697238679683863, 98.89324328906855] as [number, number],
  },
  {
    rank: 55,
    id: 'wongnai-55',
    name: "วัดต้นเกว๋น",
    url: "https://www.wongnai.com/attractions/324890uC-วัดต้นเกว๋น",
    category: "กิจกรรม / วัฒนธรรม",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.หางดง",
    address: "ถนน บ้านต้นเกว๋น",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.หางดง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.72286887, 98.92532753] as [number, number],
  },
  {
    rank: 56,
    id: 'wongnai-56',
    name: "พระตำหนักภูพิงคราชนิเวศน์",
    url: "https://www.wongnai.com/attractions/336972iL-พระตำหนักภูพิงคราชนิเวศน์",
    category: "กิจกรรม / วัฒนธรรม",
    mood: "ไหว้พระ / วัฒนธรรม",
    area: "อ.หางดง",
    address: "ถนน ศรีวิชัย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.หางดง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.804111, 98.899275] as [number, number],
  },
  {
    rank: 57,
    id: 'wongnai-57',
    name: "เชียงใหม่ไนท์ซาฟารี",
    url: "https://www.wongnai.com/attractions/326308Mh-เชียงใหม่ไนท์ซาฟารี",
    category: "กิจกรรม / วัฒนธรรม",
    mood: "เดินเล่น / กิจกรรม / ครอบครัว",
    area: "อ.หางดง",
    address: "33  ทางหลวงหมายเลข 121",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.หางดง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "กิจกรรมสำหรับครอบครัวและกลุ่มเพื่อน",
    featured: true,
    coords: [18.74259081, 98.91716721] as [number, number],
  },
  {
    rank: 58,
    id: 'wongnai-58',
    name: "ชุมชนบ้านป่าตาล",
    url: "https://www.wongnai.com/attractions/402215nd-%E0%B8%8A%E0%B8%B8%E0%B8%A1%E0%B8%8A%E0%B8%99%E0%B8%9A%E0%B9%89%E0%B8%B2%E0%B8%99%E0%B8%9B%E0%B9%88%E0%B8%B2%E0%B8%95%E0%B8%B2%E0%B8%A5",
    category: "กิจกรรม / วัฒนธรรม",
    mood: "กิจกรรม / วัฒนธรรม",
    area: "อ.หางดง",
    address: "175 ม.4 ต.สันผักหวาน อ.หางดง จ.เชียงใหม่ เชียงใหม่ 50230 ไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.หางดง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.7247833, 98.95763979999992] as [number, number],
  },
  {
    rank: 59,
    id: 'wongnai-59',
    name: "ชุมชนบ้านออนใต้",
    url: "https://www.wongnai.com/attractions/402238Nw-%E0%B8%8A%E0%B8%B8%E0%B8%A1%E0%B8%8A%E0%B8%99%E0%B8%9A%E0%B9%89%E0%B8%B2%E0%B8%99%E0%B8%AD%E0%B8%AD%E0%B8%99%E0%B9%83%E0%B8%95%E0%B9%89",
    category: "ชุมชน / อ่างเก็บน้ำ",
    mood: "ชุมชน / อ่างเก็บน้ำ",
    area: "อ.สันกำแพง",
    address: "22/8 หมู่ที่ 10, ตำบลออนใต้ อำเภอสันกำแพง จังหวัดเชียงใหม่, 50130 50130 ไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.สันกำแพง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: false,
    coords: [18.687472, 99.22308299999997] as [number, number],
  },
  {
    rank: 60,
    id: 'wongnai-60',
    name: "อ่างเก็บน้ำห้วยลาน",
    url: "https://www.wongnai.com/attractions/378318WF-อ่างเก็บน้ำห้วยลาน",
    category: "ชุมชน / อ่างเก็บน้ำ",
    mood: "ธรรมชาติ / วิว / เดินทางกลางแจ้ง",
    area: "อ.สันกำแพง",
    address: "Huai Lan Reservoir, Unnamed Road, ตำบล ออนใต้ อำเภอ สันกำแพง เชียงใหม่ 50130 ไทย",
    about: "อยู่ในลิสต์ 60 ที่เที่ยวเชียงใหม่จาก Wongnai หมวดอ.สันกำแพง ข้อมูลตำแหน่งใช้พิกัดจากหน้า Wongnai ของสถานที่นี้โดยตรง",
    bestFor: "สถานที่ท่องเที่ยวตามลิสต์ Wongnai",
    featured: true,
    coords: [18.70611039101114, 99.2063270539154] as [number, number],
  }
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
  if (text.includes('กิจกรรม') || text.includes('แอดเวนเจอร์')) return 'activity';
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
    detail: `${landmark.about} ใช้เป็นบริบทเสริมเมื่อประเมินผลกระทบต่อพื้นที่ท่องเที่ยวและชุมชนใกล้เคียง`,
    mapUrl: googleMapsSearchUrl(landmark.name, landmark.area),
    sourceUrl: landmark.url,
    sourceLabel: `Wongnai #${landmark.rank}`,
    imageKey: 'landmark',
    imageLabel: landmark.name,
    stats: [
      { label: 'ประเภท', value: landmarkKindLabel(kind) },
      { label: 'ลำดับ Wongnai', value: `#${landmark.rank} จาก 60` },
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
  selection: _selection,
  onSelectionChange,
  uiMode,
  theme,
  userLocation,
  onMapClick,
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

  useEffect(() => {
    onSelChangeRef.current = onSelectionChange;
    onMapClickRef.current = onMapClick;
  });

  // Zoom level as React state — triggers marker rebuild only on tier boundary crossings
  const [zoom, setZoom] = useState(9);
  const [baseMapId, setBaseMapId] = useState<BaseMapId>('standard');

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

    tileLayerRef.current = createBaseTileLayer('standard').addTo(map);

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

    // Click on blank map → set user location or reset selection
    map.on('click', (e: L.LeafletMouseEvent) => {
      if (onMapClickRef.current) {
        onMapClickRef.current([e.latlng.lat, e.latlng.lng]);
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
          <span class="lf-hotspot__fire" style="font-size:${Math.round(size * 0.72)}px">🔥</span>
          ${labelHtml}
        </div>`,
        className: 'lf-marker-wrap',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });

      L.marker([h.latitude, h.longitude], { icon, zIndexOffset: 100 })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          const loc = hotspotLocation(h);
          onSelChangeRef.current({
            eyebrow: 'จุดความร้อน',
            title: hotspotPlaceTitle(h),
            detail: `${loc ? `${loc} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
            imageKey: hotspotImageKey(h),
            imageLabel: hotspotPlaceTitle(h),
            stats: hotspotStats(h),
          });
        })
        .on('mouseover', () => {
          const loc = hotspotLocation(h);
          onSelChangeRef.current({
            eyebrow: 'จุดความร้อน',
            title: hotspotPlaceTitle(h),
            detail: `${loc ? `${loc} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
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
        onSelChangeRef.current(aggSel);
      })
      .on('mouseover', () => onSelChangeRef.current(aggSel))
      .addTo(group);

    // Individual station markers
    dashboard.pm25.stations.forEach((s) => {
      const stName =
        tier === 'lg' ? (s.name.trim() || s.id) : s.district || '';
      const stLabelHtml =
        tier !== 'sm' && stName
          ? `<span class="lf-station__label">${stName}</span>`
          : '';
      const next: MapSelection = {
        eyebrow: 'สถานีวัด PM2.5',
        title: s.name.trim() || s.id,
        detail: `${formatPm25(s.pm25)} · อัปเดต ${formatTime(s.updated_at)} · ${s.district}`,
        imageKey: stationImageKey(s),
        imageLabel: s.name.trim() || s.id,
        stats: [
          { label: 'PM2.5', value: formatPm25(s.pm25), tone: pm25Tone(s.pm25) },
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
          onSelChangeRef.current(next);
        })
        .on('mouseover', () => onSelChangeRef.current(next))
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
          onSelChangeRef.current(next);
        })
        .on('mouseover', () => onSelChangeRef.current(next))
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
    const layer = (L as any).velocityLayer({
      displayValues: false,
      data,
      minVelocity: 0,
      maxVelocity: 10,
      velocityScale: 0.01,
      particleAge: 120,
      particleMultiplier: 1 / 280,
      lineWidth: 1.15,
      frameRate: 30,
      opacity: 0.48,
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
      L.polyline([userLocation, [(nearest as Hotspot).latitude, (nearest as Hotspot).longitude]], {
        color: '#dc2626',
        weight: 2,
        dashArray: '4, 8',
        opacity: 0.8,
        interactive: false,
      }).addTo(group);

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
      <div ref={mapDivRef} className="map-leaflet" />

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
        {layers.landmarks && <span><i className="landmark-ic" />สถานที่เสริม 60</span>}
        {layers.landmarks && (
          <span className="landmark-kind-key" aria-label="ประเภทสถานที่เสริม">
            <i className="landmark-kind landmark-kind--temple">วัด</i>
            <i className="landmark-kind landmark-kind--nature">ดอย</i>
            <i className="landmark-kind landmark-kind--garden">สวน</i>
            <i className="landmark-kind landmark-kind--water">น้ำ</i>
            <i className="landmark-kind landmark-kind--activity">กิจ</i>
            <i className="landmark-kind landmark-kind--community">ชุม</i>
          </span>
        )}
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
    </div>
  );
}


