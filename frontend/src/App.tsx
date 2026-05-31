import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, AlertTriangle, Flame, Gauge, RefreshCcw, Wind } from 'lucide-react';
import { fetchDashboard } from './lib/api';
import { riskPercent } from './lib/risk';
import type { DashboardResponse } from './lib/types';
import { DashboardMap } from './components/DashboardMap';

type LayerState = {
  hotspots: boolean;
  pm25: boolean;
  wind: boolean;
  districts: boolean;
};

const fallback: DashboardResponse = {
  hotspots: {
    count: 134,
    density_per_100_km2: 3.8,
    latest_update: '2026-05-30T08:00:00+07:00',
    source: 'local fallback',
    items: [
      { id: 'HS-001', latitude: 18.9342, longitude: 98.7424, district: 'แม่ริม', confidence: 82, source: 'sample', detected_at: '2026-05-30T07:10:00+07:00' },
      { id: 'HS-002', latitude: 18.6741, longitude: 98.5991, district: 'หางดง', confidence: 76, source: 'sample', detected_at: '2026-05-30T07:25:00+07:00' },
      { id: 'HS-003', latitude: 19.1748, longitude: 98.8914, district: 'เชียงดาว', confidence: 88, source: 'sample', detected_at: '2026-05-30T07:35:00+07:00' },
    ],
  },
  pm25: {
    current_pm25: 48,
    category: 'เริ่มมีผลกระทบต่อสุขภาพ',
    color: 'orange',
    trend: 'rising',
    latest_update: '2026-05-30T08:00:00+07:00',
    source: 'local fallback',
    stations: [
      { id: 'CM-35T', name: 'ศาลากลางจังหวัดเชียงใหม่', district: 'เมืองเชียงใหม่', latitude: 18.8406, longitude: 98.9697, pm25: 52, trend: 'rising', updated_at: '2026-05-30T08:00:00+07:00' },
      { id: 'CM-UP', name: 'มหาวิทยาลัยเชียงใหม่', district: 'เมืองเชียงใหม่', latitude: 18.8021, longitude: 98.9529, pm25: 46, trend: 'stable', updated_at: '2026-05-30T08:00:00+07:00' },
    ],
  },
  weather: {
    wind_speed_kmh: 14,
    wind_direction_deg: 255,
    wind_direction_text: 'ตะวันตกเฉียงใต้',
    temperature_c: 33,
    humidity_percent: 42,
    latest_update: '2026-05-30T08:00:00+07:00',
    source: 'local fallback',
  },
  risk: {
    score: 9,
    category: 'High',
    formula: 'min(10, round(min(PM2.5/15,4) + min(hotspot_count/50,4) + wind_factor))',
    factors: { pm25_points: 3.2, hotspot_points: 2.68, wind_factor: 2, wind_pushes_smoke_to_city: 'yes' },
  },
  summary: {
    language: 'th',
    text: 'เชียงใหม่มีคุณภาพอากาศอยู่ในระดับเริ่มส่งผลกระทบต่อสุขภาพ พบจุดความร้อน 134 จุด และลมมีแนวโน้มพัดควันเข้าสู่ตัวเมือง ควรลดกิจกรรมกลางแจ้ง',
    source: 'local fallback',
  },
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function MetricCard({ icon, title, value, meta, tone }: { icon: ReactNode; title: string; value: string; meta: string; tone?: string }) {
  return (
    <section className="metric-card" data-tone={tone}>
      <div className="metric-card__top">
        <span className="metric-card__icon">{icon}</span>
        <span>{title}</span>
      </div>
      <strong>{value}</strong>
      <small>{meta}</small>
    </section>
  );
}

export function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerState>({ hotspots: true, pm25: true, wind: true, districts: true });

  useEffect(() => {
    fetchDashboard()
      .then((data) => {
        setDashboard(data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const updatedAt = useMemo(() => {
    const times = [dashboard.hotspots.latest_update, dashboard.pm25.latest_update, dashboard.weather.latest_update];
    const sorted = times.sort();
    return formatTime(sorted[sorted.length - 1] ?? dashboard.pm25.latest_update);
  }, [dashboard]);

  const toggleLayer = (key: keyof LayerState) => setLayers((current) => ({ ...current, [key]: !current[key] }));

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>ChiangMaiEyes</h1>
          <p>แดชบอร์ดสถานการณ์จุดความร้อน ฝุ่น PM2.5 และลมในเชียงใหม่</p>
        </div>
        <div className="topbar__status">
          <RefreshCcw size={16} aria-hidden />
          <span>{loading ? 'กำลังโหลดข้อมูล' : `อัปเดตล่าสุด ${updatedAt}`}</span>
        </div>
      </header>

      {error && <div className="notice">ใช้ข้อมูลสำรองในเครื่อง เนื่องจาก API ยังไม่พร้อม: {error}</div>}

      <section className="dashboard-grid">
        <aside className="side-panel" aria-label="สถานการณ์ล่าสุด">
          <MetricCard icon={<Activity size={20} />} title="PM2.5 ปัจจุบัน" value={`${dashboard.pm25.current_pm25} µg/m³`} meta={`${dashboard.pm25.category} · แนวโน้ม ${dashboard.pm25.trend}`} tone={dashboard.pm25.color} />
          <MetricCard icon={<Flame size={20} />} title="จุดความร้อน" value={`${dashboard.hotspots.count} จุด`} meta={`ความหนาแน่น ${dashboard.hotspots.density_per_100_km2}/100 กม²`} tone="hotspot" />
          <MetricCard icon={<Wind size={20} />} title="ลม" value={`${dashboard.weather.wind_direction_text}`} meta={`${dashboard.weather.wind_speed_kmh} กม./ชม. · ${dashboard.weather.temperature_c}°C · RH ${dashboard.weather.humidity_percent}%`} tone="wind" />

          <section className="risk-panel">
            <div className="risk-panel__header">
              <Gauge size={20} />
              <span>คะแนนความเสี่ยง</span>
            </div>
            <div className="risk-panel__score">
              <strong>{dashboard.risk.score}</strong>
              <span>/10</span>
            </div>
            <div className="risk-bar" aria-label={`Risk score ${dashboard.risk.score} จาก 10`}>
              <span style={{ width: `${riskPercent(dashboard.risk.score)}%` }} />
            </div>
            <p className="risk-category">ระดับ {dashboard.risk.category}</p>
            <code>{dashboard.risk.formula}</code>
          </section>

          <section className="summary-panel">
            <div>
              <AlertTriangle size={20} />
              <span>สรุปสถานการณ์</span>
            </div>
            <p>{dashboard.summary.text}</p>
            <small>แหล่งสรุป: {dashboard.summary.source}</small>
          </section>
        </aside>

        <section className="map-stage" aria-label="แผนที่สถานการณ์เชียงใหม่">
          <div className="map-toolbar">
            {Object.entries(layers).map(([key, enabled]) => (
              <button key={key} type="button" className={enabled ? 'active' : ''} onClick={() => toggleLayer(key as keyof LayerState)}>
                {key === 'hotspots' ? 'จุดความร้อน' : key === 'pm25' ? 'PM2.5' : key === 'wind' ? 'ลม' : 'เขตอำเภอ'}
              </button>
            ))}
          </div>
          <DashboardMap dashboard={dashboard} layers={layers} />
        </section>
      </section>
    </main>
  );
}



