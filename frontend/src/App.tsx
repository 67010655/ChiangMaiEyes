import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Flame, Info, Menu, RefreshCcw, ShieldCheck, Wind } from 'lucide-react';
import { fetchDashboard } from './lib/api';
import { riskPercent } from './lib/risk';
import type { DashboardResponse } from './lib/types';
import { DashboardMap } from './components/DashboardMap';
import dashboardSnapshot from './data/dashboardSnapshot.json';
import { windDestinationName } from './lib/wind';

type LayerState = {
  hotspots: boolean;
  pm25: boolean;
  wind: boolean;
};

const fallback = dashboardSnapshot as DashboardResponse;

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { timeStyle: 'short' }).format(new Date(value));
}

function getRiskTone(score: number) {
  if (score <= 3) return 'low';
  if (score <= 6) return 'medium';
  return 'high';
}

const riskLabelTh: Record<string, string> = {
  low: 'ความเสี่ยงต่ำ',
  medium: 'ความเสี่ยงปานกลาง',
  high: 'ความเสี่ยงสูง',
};

const adviceByColor: Record<string, { heading: string; text: string }> = {
  green: {
    heading: 'คุณภาพอากาศดีมาก',
    text: 'เหมาะสำหรับกิจกรรมกลางแจ้ง ทำต่อเนื่องได้ตามปกติ และติดตามสถานการณ์เป็นระยะ',
  },
  yellow: {
    heading: 'คุณภาพอากาศปานกลาง',
    text: 'ทำกิจกรรมกลางแจ้งได้ กลุ่มเสี่ยงควรสังเกตอาการและลดกิจกรรมหนักเป็นเวลานาน',
  },
  orange: {
    heading: 'เริ่มมีผลต่อสุขภาพ',
    text: 'กลุ่มเสี่ยงควรลดกิจกรรมกลางแจ้ง และสวมหน้ากากป้องกันฝุ่นเมื่อต้องอยู่นอกอาคาร',
  },
  red: {
    heading: 'มีผลต่อสุขภาพ',
    text: 'ทุกคนควรลดกิจกรรมกลางแจ้ง สวมหน้ากาก N95 และปิดประตูหน้าต่างเมื่ออยู่ในอาคาร',
  },
  purple: {
    heading: 'อยู่ในระดับอันตราย',
    text: 'งดกิจกรรมกลางแจ้งทั้งหมด อยู่ในอาคารที่ปิดมิดชิด และใช้เครื่องฟอกอากาศหากเป็นไปได้',
  },
};

function Sparkline() {
  // Decorative 24h trend placeholder because the backend does not expose a time series yet.
  const points = [10, 9, 11, 8, 12, 9, 8, 10, 9, 13, 10, 9, 11, 8, 9, 10];
  const w = 132;
  const h = 44;
  const max = Math.max(...points);
  const min = Math.min(...points);
  const step = w / (points.length - 1);
  const path = points
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / (max - min || 1)) * (h - 6) - 3;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg className="sparkline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <path d={`${path} L${w} ${h} L0 ${h} Z`} className="sparkline__fill" />
      <path d={path} className="sparkline__line" />
    </svg>
  );
}

function RiskDonut({ score, tone }: { score: number; tone: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const pct = riskPercent(score) / 100;
  const stroke = tone === 'low' ? '#16a34a' : tone === 'medium' ? '#eab308' : '#dc2626';
  return (
    <svg className="risk-donut" viewBox="0 0 130 130">
      <circle cx="65" cy="65" r={r} fill="none" stroke="#e6efe9" strokeWidth="12" />
      <circle
        cx="65"
        cy="65"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`}
        transform="rotate(-90 65 65)"
      />
      <text x="65" y="60" textAnchor="middle" className="risk-donut__score">
        {score}
      </text>
      <text x="65" y="82" textAnchor="middle" className="risk-donut__max">
        /10
      </text>
    </svg>
  );
}

export function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [layers, setLayers] = useState<LayerState>({ hotspots: true, pm25: true, wind: true });

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
    return sorted[sorted.length - 1] ?? dashboard.pm25.latest_update;
  }, [dashboard]);

  const riskTone = getRiskTone(dashboard.risk.score);
  const allOn = layers.hotspots && layers.pm25 && layers.wind;
  const toggleLayer = (key: keyof LayerState) => setLayers((current) => ({ ...current, [key]: !current[key] }));
  const setAll = () => setLayers({ hotspots: true, pm25: true, wind: true });

  const pm25Time = formatTime(dashboard.pm25.latest_update);
  const advice = adviceByColor[dashboard.pm25.color] ?? adviceByColor.green;
  const factors = dashboard.risk.factors;
  const pm25Points = Number(factors.pm25_points ?? 0);
  const hotspotPoints = Number(factors.hotspot_points ?? 0);
  const windFactor = Number(factors.wind_factor ?? 0);
  const windSourceText = dashboard.weather.wind_direction_text;
  const windDestinationText = windDestinationName(dashboard.weather.wind_direction_deg);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden>
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
              <path d="M7 11l2.5-2.5M12 12l4-4" opacity="0.6" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </span>
          <div className="brand-text">
            <h1>ChiangMaiEyes</h1>
            <p>
              <span className="brand-bar" />รายงานจุดความร้อน ฝุ่นละออง และทิศทางลม
              <span className="brand-sep">|</span>จังหวัดเชียงใหม่
            </p>
          </div>
        </div>

        <div className="topbar__actions">
          <div className="live-pill">
            <span className="live-dot" />
            <div>
              <strong>{loading ? 'กำลังอัปเดต' : 'อัปเดตล่าสุด'}</strong>
              <span>{formatDateTime(updatedAt)}</span>
            </div>
          </div>
          <button className="icon-button" type="button" onClick={loadDashboard} aria-label="อัปเดตข้อมูล">
            <RefreshCcw size={18} />
          </button>
          <button className="icon-button icon-button--filled" type="button" aria-label="เมนู">
            <Menu size={18} />
          </button>
        </div>
      </header>

      {error && <div className="notice">ใช้ snapshot สำรองชั่วคราว เพราะ live API ยังไม่พร้อม: {error}</div>}

      <section className="dashboard-grid">
        <aside className="side-panel" aria-label="สถานการณ์ล่าสุด">
          <section className="card pm-card">
            <div className="card__head">
              <span className="card__title">PM2.5 เฉลี่ย 24 ชม.</span>
              <Info size={16} className="card__info" />
            </div>
            <div className="pm-card__body">
              <div className="pm-card__value">
                <strong>{dashboard.pm25.current_pm25}</strong>
                <span>µg/m³</span>
              </div>
              <div className="pm-card__chart">
                <Sparkline />
                <div className="pm-card__axis">
                  <span>00:00</span>
                  <span>08:00</span>
                  <span>16:00</span>
                </div>
              </div>
            </div>
            <span className={`badge badge--${dashboard.pm25.color}`}>{dashboard.pm25.category}</span>
            <small className="card__foot">อัปเดต {pm25Time} น.</small>
          </section>

          <div className="card-row">
            <section className="card mini-card">
              <span className="card__title">จุดความร้อนวันนี้</span>
              <div className="mini-card__body">
                <span className="mini-card__icon mini-card__icon--fire">
                  <Flame size={20} />
                </span>
                <div className="mini-card__value">
                  <strong>{dashboard.hotspots.count}</strong>
                  <span>จุด</span>
                </div>
              </div>
              <small className="card__foot">อัปเดต {pm25Time} น.</small>
            </section>

            <section className="card mini-card">
              <span className="card__title">ทิศทางลม</span>
              <div className="mini-card__body">
                <span className="mini-card__icon mini-card__icon--wind">
                  <Wind size={20} />
                </span>
                <div className="mini-card__value">
                  <strong className="mini-card__wind">ไป{windDestinationText}</strong>
                  <span>จาก{windSourceText} · {dashboard.weather.wind_speed_kmh} km/h</span>
                </div>
              </div>
              <small className="card__foot">อัปเดต {pm25Time} น.</small>
            </section>
          </div>

          <section className="card risk-card" data-risk={riskTone}>
            <div className="card__head">
              <span className="card__title">คะแนนความเสี่ยงการเกิดหมอกควัน</span>
              <Info size={16} className="card__info" />
            </div>
            <div className="risk-card__body">
              <div className="risk-card__gauge">
                <RiskDonut score={dashboard.risk.score} tone={riskTone} />
                <span className="risk-card__label">{riskLabelTh[riskTone]}</span>
              </div>
              <ul className="risk-card__factors">
                <li>
                  <span><i className="dot dot--pm" />PM2.5</span>
                  <strong>{pm25Points.toFixed(1)} <em>/4</em></strong>
                </li>
                <li>
                  <span><i className="dot dot--hot" />จุดความร้อน</span>
                  <strong>{hotspotPoints.toFixed(1)} <em>/4</em></strong>
                </li>
                <li>
                  <span><i className="dot dot--wind" />ทิศทางลม</span>
                  <strong>{windFactor.toFixed(1)} <em>/2</em></strong>
                </li>
              </ul>
            </div>
            <p className="risk-card__formula">สมการ: {dashboard.risk.formula}</p>
          </section>

          <section className="card advice-card">
            <div className="card__head">
              <ShieldCheck size={18} className="advice-card__shield" />
              <span className="card__title">คำแนะนำสำหรับประชาชน</span>
            </div>
            <h3 className={`advice-card__heading advice-card__heading--${dashboard.pm25.color}`}>{advice.heading}</h3>
            <p className="advice-card__text">{advice.text}</p>
            <svg className="advice-card__art" viewBox="0 0 320 80" preserveAspectRatio="none" aria-hidden>
              <path d="M0 80 L0 52 Q60 30 120 46 T240 40 T320 50 L320 80 Z" fill="#cdecd8" />
              <path d="M0 80 L0 64 Q80 48 170 60 T320 60 L320 80 Z" fill="#a9dcbc" />
              <circle cx="58" cy="40" r="11" fill="#86cba1" />
              <path d="M150 60 l8-22 8 22 Z M182 60 l10-28 10 28 Z" fill="#5fb583" />
            </svg>
          </section>
        </aside>

        <section className="map-stage" aria-label="แผนที่สถานการณ์เชียงใหม่">
          <div className="map-titlebar">
            <h2>แผนที่จังหวัดเชียงใหม่</h2>
            <div className="map-toolbar">
              <button type="button" className={allOn ? 'active' : ''} onClick={setAll}>
                ทั้งหมด
              </button>
              <button type="button" className={layers.pm25 ? 'active' : ''} onClick={() => toggleLayer('pm25')}>
                PM2.5
              </button>
              <button type="button" className={layers.hotspots ? 'active' : ''} onClick={() => toggleLayer('hotspots')}>
                จุดความร้อน
              </button>
              <button type="button" className={layers.wind ? 'active' : ''} onClick={() => toggleLayer('wind')}>
                ลม
              </button>
            </div>
          </div>

          <DashboardMap dashboard={dashboard} layers={layers} />
        </section>
      </section>

      <footer className="page-foot">
        <span>
          แหล่งข้อมูล: {dashboard.hotspots.source} · {dashboard.pm25.source} · {dashboard.weather.source}
        </span>
        <span>ChiangMaiEyes © 2026</span>
      </footer>
    </div>
  );
}
