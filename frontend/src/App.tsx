import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, AlertTriangle, Flame, Gauge, RefreshCcw, Wind } from 'lucide-react';
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

const fallback = dashboardSnapshot as DashboardResponse;

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



