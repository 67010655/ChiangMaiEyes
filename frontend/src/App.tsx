import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  Clock3,
  Eye,
  Flame,
  Gauge,
  Layers3,
  MapPin,
  RefreshCcw,
  ShieldCheck,
  Wind,
} from 'lucide-react';
import { fetchDashboard } from './lib/api';
import { riskPercent } from './lib/risk';
import type { DashboardResponse } from './lib/types';
import { DashboardMap } from './components/DashboardMap';
import dashboardSnapshot from './data/dashboardSnapshot.json';

type LayerState = {
  hotspots: boolean;
  pm25: boolean;
  wind: boolean;
  districts: boolean;
};

type MetricCardProps = {
  icon: ReactNode;
  title: string;
  value: string;
  meta: string;
  tone?: string;
  detail?: ReactNode;
};

const fallback = dashboardSnapshot as DashboardResponse;

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function getRiskTone(score: number) {
  if (score <= 3) return 'low';
  if (score <= 6) return 'medium';
  return 'high';
}

function MetricCard({ icon, title, value, meta, tone, detail }: MetricCardProps) {
  return (
    <section className="metric-card" data-tone={tone}>
      <div className="metric-card__top">
        <span className="metric-card__icon">{icon}</span>
        <span>{title}</span>
      </div>
      <strong>{value}</strong>
      <small>{meta}</small>
      {detail}
    </section>
  );
}

export function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerState>({ hotspots: true, pm25: true, wind: true, districts: true });

  const loadDashboard = useCallback(() => {
    setLoading(true);
    fetchDashboard()
      .then((data) => {
        setDashboard(data);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadDashboard();
    const refreshId = window.setInterval(loadDashboard, 5 * 60 * 1000);
    return () => window.clearInterval(refreshId);
  }, [loadDashboard]);

  const updatedAt = useMemo(() => {
    const times = [dashboard.hotspots.latest_update, dashboard.pm25.latest_update, dashboard.weather.latest_update];
    const sorted = [...times].sort();
    return formatTime(sorted[sorted.length - 1] ?? dashboard.pm25.latest_update);
  }, [dashboard]);

  const activeLayerCount = Object.values(layers).filter(Boolean).length;
  const riskTone = getRiskTone(dashboard.risk.score);
  const toggleLayer = (key: keyof LayerState) => setLayers((current) => ({ ...current, [key]: !current[key] }));

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden>
            <Eye size={24} />
          </span>
          <div>
            <h1>ChiangMaiEyes</h1>
            <p>รายงานจุดความร้อน ฝุ่น PM2.5 และทิศทางลม เพื่อคาดการณ์และรับมือในจังหวัดเชียงใหม่</p>
          </div>
        </div>

        <div className="topbar__actions" aria-label="สถานะข้อมูล">
          <div className="live-pill">
            <span className="live-dot" />
            <div>
              <strong>{loading ? 'กำลังอัปเดต' : 'ข้อมูลสด'}</strong>
              <span>{updatedAt}</span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={loadDashboard} aria-label="อัปเดตข้อมูล">
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      {error && <div className="notice">ใช้ snapshot สำรองชั่วคราว เพราะ live API ยังไม่พร้อม: {error}</div>}

      <section className="dashboard-grid">
        <aside className="side-panel" aria-label="สถานการณ์ล่าสุด">
          <section className="focus-panel">
            <div className="section-kicker">
              <MapPin size={16} />
              โฟกัสเฉพาะขอบเขตจังหวัดเชียงใหม่
            </div>
            <h2>เฝ้าระวังหมอกควันด้วยข้อมูลฝุ่น จุดความร้อน และลมล่าสุด</h2>
            <p>{dashboard.summary.text}</p>
          </section>

          <MetricCard
            icon={<Activity size={20} />}
            title="PM2.5 เฉลี่ยล่าสุด"
            value={`${dashboard.pm25.current_pm25} µg/m³`}
            meta={`${dashboard.pm25.category} · ${dashboard.pm25.stations.length} สถานีรายงาน`}
            tone={dashboard.pm25.color}
            detail={<div className="sparkline" aria-hidden><span /></div>}
          />
          <div className="compact-metrics">
            <MetricCard
              icon={<Flame size={20} />}
              title="จุดความร้อน"
              value={`${dashboard.hotspots.count}`}
              meta={`ความหนาแน่น ${dashboard.hotspots.density_per_100_km2}/100 กม²`}
              tone="hotspot"
            />
            <MetricCard
              icon={<Wind size={20} />}
              title="ทิศทางลม"
              value={dashboard.weather.wind_direction_text}
              meta={`${dashboard.weather.wind_speed_kmh} กม./ชม. · ${dashboard.weather.temperature_c}°C`}
              tone="wind"
            />
          </div>

          <section className="risk-panel" data-risk={riskTone}>
            <div className="risk-panel__header">
              <Gauge size={20} />
              <span>โอกาสเกิดหมอกควันสะสม</span>
            </div>
            <div className="risk-panel__score">
              <strong>{dashboard.risk.score}</strong>
              <span>/10</span>
            </div>
            <div className="risk-bar" aria-label={`Risk score ${dashboard.risk.score} จาก 10`}>
              <span style={{ width: `${riskPercent(dashboard.risk.score)}%` }} />
            </div>
            <div className="risk-breakdown">
              <span>PM2.5 {dashboard.risk.factors.pm25_points}/4</span>
              <span>จุดความร้อน {dashboard.risk.factors.hotspot_points}/4</span>
              <span>ลม {dashboard.risk.factors.wind_factor}/2</span>
            </div>
          </section>

          <section className="summary-panel">
            <div>
              <ShieldCheck size={20} />
              <span>คำแนะนำสำหรับประชาชน</span>
            </div>
            <p>{dashboard.summary.text}</p>
            <small>แหล่งข้อมูล: {dashboard.hotspots.source} · {dashboard.pm25.source} · {dashboard.weather.source}</small>
          </section>
        </aside>

        <section className="map-stage" aria-label="แผนที่สถานการณ์เชียงใหม่">
          <div className="map-titlebar">
            <div>
              <div className="section-kicker">
                <Layers3 size={16} />
                {activeLayerCount} เลเยอร์กำลังแสดง
              </div>
              <h2>แผนที่จังหวัดเชียงใหม่</h2>
            </div>
            <div className="map-clock">
              <Clock3 size={16} />
              <span>{updatedAt}</span>
            </div>
          </div>

          <div className="map-toolbar" aria-label="เปิดปิดเลเยอร์ข้อมูล">
            {Object.entries(layers).map(([key, enabled]) => (
              <button key={key} type="button" className={enabled ? 'active' : ''} onClick={() => toggleLayer(key as keyof LayerState)}>
                {key === 'hotspots' ? 'จุดความร้อน' : key === 'pm25' ? 'PM2.5' : key === 'wind' ? 'ลม' : 'ขอบเขตเชียงใหม่'}
              </button>
            ))}
          </div>

          <DashboardMap dashboard={dashboard} layers={layers} />
        </section>
      </section>
    </main>
  );
}
