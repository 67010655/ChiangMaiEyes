import L from 'leaflet';
import { CircleMarker, MapContainer, Marker, Polygon, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';
import { useEffect } from 'react';
import type { DashboardResponse } from '../lib/types';

type Props = {
  dashboard: DashboardResponse;
  layers: {
    hotspots: boolean;
    pm25: boolean;
    wind: boolean;
    districts: boolean;
  };
};

const chiangMaiMapBounds: [[number, number], [number, number]] = [
  [17.35, 97.25],
  [20.28, 99.68],
];

// Simplified province outline for the MVP map. Production can replace this with
// OSM relation 1908771 or an official Thai administrative GeoJSON source.
const chiangMaiProvinceBoundary: [number, number][] = [
  [20.15, 98.78],
  [20.08, 99.14],
  [19.88, 99.42],
  [19.52, 99.54],
  [19.22, 99.34],
  [18.98, 99.47],
  [18.63, 99.34],
  [18.30, 99.35],
  [17.92, 99.20],
  [17.55, 98.96],
  [17.43, 98.62],
  [17.56, 98.28],
  [17.84, 97.96],
  [18.07, 97.58],
  [18.42, 97.38],
  [18.72, 97.50],
  [18.98, 97.74],
  [19.34, 97.76],
  [19.62, 98.02],
  [19.94, 98.26],
  [20.15, 98.78],
];

function windIcon(directionDeg: number) {
  return L.divIcon({
    className: 'wind-marker',
    html: `<span style="transform: rotate(${directionDeg}deg)">↑</span>`,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
  });
}

function pm25Color(pm25: number) {
  if (pm25 <= 25) return '#229954';
  if (pm25 <= 37) return '#f1c40f';
  if (pm25 <= 50) return '#e67e22';
  if (pm25 <= 90) return '#c0392b';
  return '#7d3c98';
}

function ProvinceViewport() {
  const map = useMap();

  useEffect(() => {
    map.fitBounds(chiangMaiMapBounds, { padding: [18, 18] });
  }, [map]);

  return null;
}

export function DashboardMap({ dashboard, layers }: Props) {
  return (
    <MapContainer
      center={[18.92, 98.82]}
      zoom={8}
      minZoom={7}
      maxBounds={chiangMaiMapBounds}
      maxBoundsViscosity={0.75}
      scrollWheelZoom
      className="leaflet-stage"
    >
      <ProvinceViewport />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {layers.districts && (
        <>
          <Polygon
            positions={chiangMaiProvinceBoundary}
            pathOptions={{ color: '#0f4f3e', weight: 11, opacity: 0.18, fillOpacity: 0, interactive: false }}
          />
          <Polygon
            positions={chiangMaiProvinceBoundary}
            pathOptions={{ color: '#0f6b54', weight: 4, opacity: 0.98, fillColor: '#55c28f', fillOpacity: 0.11, dashArray: '10 8' }}
          >
            <Tooltip permanent direction="top" className="province-tooltip" offset={[0, -8]}>
              ขอบเขตจังหวัดเชียงใหม่
            </Tooltip>
            <Popup>
              <strong>จังหวัดเชียงใหม่</strong><br />
              โฟกัสการรายงานเฉพาะพื้นที่ภายในขอบเขตจังหวัดเชียงใหม่
            </Popup>
          </Polygon>
        </>
      )}

      {layers.hotspots &&
        dashboard.hotspots.items.map((hotspot) => (
          <CircleMarker
            key={hotspot.id}
            center={[hotspot.latitude, hotspot.longitude]}
            radius={Math.max(7, hotspot.confidence / 9)}
            pathOptions={{ color: '#b8321b', fillColor: '#ef4e2f', fillOpacity: 0.78, weight: 1 }}
          >
            <Popup>
              <strong>{hotspot.district}</strong><br />
              Confidence {hotspot.confidence}%<br />
              {new Date(hotspot.detected_at).toLocaleString('th-TH')}
            </Popup>
          </CircleMarker>
        ))}

      {layers.pm25 &&
        dashboard.pm25.stations.map((station) => (
          <CircleMarker
            key={station.id}
            center={[station.latitude, station.longitude]}
            radius={12}
            pathOptions={{ color: '#1e293b', fillColor: pm25Color(station.pm25), fillOpacity: 0.88, weight: 2 }}
          >
            <Popup>
              <strong>{station.name}</strong><br />
              PM2.5 {station.pm25} µg/m³<br />
              แนวโน้ม {station.trend}
            </Popup>
          </CircleMarker>
        ))}

      {layers.wind &&
        [
          [18.79, 98.98],
          [19.28, 98.72],
          [18.26, 98.62],
        ].map(([lat, lng]) => (
          <Marker key={`${lat}-${lng}`} position={[lat, lng]} icon={windIcon(dashboard.weather.wind_direction_deg)}>
            <Popup>
              ลม {dashboard.weather.wind_direction_text} {dashboard.weather.wind_speed_kmh} กม./ชม.
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  );
}
