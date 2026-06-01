import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, Flame, Home, Info, MapPin, RefreshCcw, ShieldCheck, Wind } from 'lucide-react';
import { fetchDashboard } from './lib/api';
import { riskPercent } from './lib/risk';
import type { DashboardResponse } from './lib/types';
import { DashboardMap, type MapSelection, initialSelection } from './components/DashboardMap';
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

const REC_ICONS = [Home, BookOpen, MapPin] as const;

function computeRecommendations(pm25: number, hotspots: number, riskScore: number): Array<{ label: string; detail: string }> {
  let r1: string;
  if (pm25 <= 25 && riskScore <= 3) {
    r1 = 'ออกจากบ้านได้:อากาศดี เหมาะสำหรับกิจกรรมกลางแจ้งทุกประเภท';
  } else if (pm25 <= 37) {
    r1 = 'ออกจากบ้านได้:แนะนำสวมหน้ากากหากออกกำลังกายกลางแจ้งนาน';
  } else if (pm25 <= 50 || riskScore <= 6) {
    r1 = 'ออกนอกบ้านด้วยความระมัดระวัง:สวม N95 และลดเวลาอยู่กลางแจ้ง';
  } else {
    r1 = 'แนะนำอยู่ในอาคาร:PM2.5 เกินเกณฑ์ปลอดภัย ลดการสัมผัสอากาศภายนอก';
  }

  let r2: string;
  if (pm25 <= 25) {
    r2 = 'เด็กไปโรงเรียนได้:คุณภาพอากาศดี ปลอดภัยสำหรับเด็ก';
  } else if (pm25 <= 37) {
    r2 = 'เด็กไปโรงเรียนได้:แนะนำสวมหน้ากากและงดกิจกรรมกลางแจ้ง';
  } else if (pm25 <= 50) {
    r2 = 'ควรปรึกษาโรงเรียน:PM2.5 เริ่มส่งผลต่อระบบทางเดินหายใจของเด็ก';
  } else {
    r2 = 'แนะนำให้เด็กอยู่บ้าน:PM2.5 สูงเกินเกณฑ์ปลอดภัยสำหรับเด็กเล็ก';
  }

  let r3: string;
  if (hotspots === 0) {
    r3 = 'เจ้าหน้าที่:ยังไม่พบจุดความร้อน เฝ้าระวังตามปกติ';
  } else if (hotspots <= 10) {
    r3 = `เจ้าหน้าที่:พบ ${hotspots} จุดความร้อน ให้ติดตามพื้นที่ป่าและชายป่า`;
  } else if (hotspots <= 50) {
    r3 = `เจ้าหน้าที่:${hotspots} จุดความร้อน เพิ่มกำลังเฝ้าระวังพื้นที่ป่าและเกษตรชายขอบ`;
  } else {
    r3 = `เจ้าหน้าที่:${hotspots} จุดความร้อน สถานการณ์วิกฤต — ระดมพลทุกพื้นที่หนาแน่น`;
  }

  return [r1, r2, r3].map((s) => {
    const idx = s.indexOf(':');
    return { label: s.slice(0, idx), detail: s.slice(idx + 1) };
  });
}

const PM_SEGMENTS = ['#16a34a', '#eab308', '#f97316', '#dc2626', '#7c3aed'];
const PM_BOUNDS = [0, 25, 37, 50, 90, 150];
const PM_TICKS = [25, 37, 50, 90];

// Map a PM2.5 reading onto an equal-width 5-band category scale so the marker
// lines up with its colour band and the printed thresholds.
function pmScalePercent(value: number) {
  for (let i = 0; i < 5; i += 1) {
    const lo = PM_BOUNDS[i];
    const hi = PM_BOUNDS[i + 1];
    if (value <= hi || i === 4) {
      const t = Math.min(Math.max((value - lo) / (hi - lo), 0), 1);
      return Math.min((i + t) * 20, 100);
    }
  }
  return 100;
}

function Pm25Scale({ value }: { value: number }) {
  // Real category scale: the current reading against published thresholds, not
  // a fabricated time series. The number + badge carry the value for assistive
  // tech, so the bar itself is decorative to a screen reader.
  const pct = pmScalePercent(value);
  return (
    <div className="pm-scale" aria-hidden>
      <div className="pm-scale__bar">
        <div className="pm-scale__track">
          {PM_SEGMENTS.map((color) => (
            <span key={color} className="pm-scale__seg" style={{ background: color }} />
          ))}
        </div>
        <span className="pm-scale__marker" style={{ left: `${pct}%` }} />
      </div>
      <div className="pm-scale__ticks">
        {PM_TICKS.map((tick, i) => (
          <span key={tick} style={{ left: `${(i + 1) * 20}%` }}>
            {tick}
          </span>
        ))}
      </div>
    </div>
  );
}

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
    <div style={{ position: 'relative' }} aria-label="กราฟแนวโน้ม PM2.5 ย้อนหลัง 24 ชั่วโมง (ข้อมูลตัวอย่าง)">
      <svg className="sparkline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
        <path d={`${path} L${w} ${h} L0 ${h} Z`} className="sparkline__fill" />
        <path d={path} className="sparkline__line" />
      </svg>
      <span style={{ position: 'absolute', top: 0, right: 0, fontSize: '0.6rem', color: 'var(--muted)', opacity: 0.7 }}>
        ตัวอย่าง
      </span>
    </div>
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
  const [note, setNote] = useState<'pm' | 'risk' | null>(null);
  const [mapSelection, setMapSelection] = useState<MapSelection>(initialSelection);

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
  const toggleNote = (key: 'pm' | 'risk') => setNote((current) => (current === key ? null : key));
  const setAll = () => setLayers({ hotspots: true, pm25: true, wind: true });

  const pm25Time = formatTime(dashboard.pm25.latest_update);
  const advice = adviceByColor[dashboard.pm25.color] ?? adviceByColor.green;
  const recommendations = computeRecommendations(
    dashboard.pm25.current_pm25,
    dashboard.hotspots.count,
    dashboard.risk.score,
  );
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
        </div>
      </header>

      {error && <div className="notice">ใช้ snapshot สำรองชั่วคราว เพราะ live API ยังไม่พร้อม: {error}</div>}

      {/* ② Map — core feature, now second after header */}
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

        <DashboardMap dashboard={dashboard} layers={layers} selection={mapSelection} onSelectionChange={setMapSelection} />
      </section>

      {/* Map detail bar — below the map, not overlapping it */}
      <div className="map-detail-bar card" aria-live="polite">
        <div className="map-detail-bar__left">
          <span className="map-detail-bar__eyebrow">{mapSelection.eyebrow}</span>
          <strong className="map-detail-bar__title">{mapSelection.title}</strong>
          <p className="map-detail-bar__detail">{mapSelection.detail}</p>
        </div>
        {mapSelection.stats && mapSelection.stats.length > 0 && (
          <div className="map-inspector__stats map-detail-bar__stats">
            {mapSelection.stats.map((stat) => (
              <div key={`${stat.label}-${stat.value}`} className={`map-inspector__stat ${stat.tone ? `map-inspector__stat--${stat.tone}` : ''}`}>
                <span>{stat.label}</span>
                <b>{stat.value}</b>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ③④⑤ Stats cards — below map */}
      <section className="stats-panel" aria-label="สถานการณ์ล่าสุด">
        {/* ③ PM2.5 + hotspot + wind */}
        <div className="stats-main">
          <section className="card pm-card">
            <div className="card__head">
              <span className="card__title">PM2.5 เฉลี่ย 24 ชม.</span>
              <button
                type="button"
                className="card__info-btn"
                aria-label="คำอธิบายค่า PM2.5"
                aria-expanded={note === 'pm'}
                aria-controls="pm-note"
                onClick={() => toggleNote('pm')}
              >
                <Info size={15} />
              </button>
            </div>
            {note === 'pm' && (
              <p id="pm-note" className="card__note">
                ค่าเฉลี่ย PM2.5 รอบ 24 ชั่วโมงจากสถานีตรวจวัดในเชียงใหม่ · เกณฑ์สี: ≤25 ดี · ≤37 ปานกลาง · ≤50 เริ่มมีผล · ≤90 มีผล · เกิน 90 อันตราย
              </p>
            )}
            <div className="pm-card__body">
              <div className="pm-card__value">
                <strong>{dashboard.pm25.current_pm25}</strong>
                <span>µg/m³</span>
              </div>
              <Pm25Scale value={dashboard.pm25.current_pm25} />
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
        </div>

        {/* ④ Risk score */}
        <section className="card risk-card" data-risk={riskTone}>
          <div className="card__head">
            <span className="card__title">คะแนนความเสี่ยงการเกิดหมอกควัน</span>
            <button
              type="button"
              className="card__info-btn"
              aria-label="คำอธิบายคะแนนความเสี่ยง"
              aria-expanded={note === 'risk'}
              aria-controls="risk-note"
              onClick={() => toggleNote('risk')}
            >
              <Info size={15} />
            </button>
          </div>
          {note === 'risk' && (
            <p id="risk-note" className="card__note">
              คะแนน 0–10 รวมจาก 3 ปัจจัย: PM2.5 (สูงสุด 4), จุดความร้อน (สูงสุด 4) และทิศทางลม (สูงสุด 2) · ยิ่งคะแนนสูง โอกาสเกิดและสะสมหมอกควันยิ่งมาก
            </p>
          )}
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

        {/* ④⑤ Advice + recommendations + AI summary */}
        <section className="card advice-card">
          <div className="card__head">
            <ShieldCheck size={18} className="advice-card__shield" />
            <span className="card__title">คำแนะนำสำหรับประชาชน</span>
          </div>
          <h3 className={`advice-card__heading advice-card__heading--${dashboard.pm25.color}`}>{advice.heading}</h3>
          <p className="advice-card__text">{advice.text}</p>
          <ul className="advice-recs">
            {recommendations.map(({ label, detail }, i) => {
              const Icon = REC_ICONS[i];
              return (
                <li key={i} className="advice-rec">
                  <span className="advice-rec__icon"><Icon size={15} /></span>
                  <span className="advice-rec__body"><strong>{label}:</strong> {detail}</span>
                </li>
              );
            })}
          </ul>
          {dashboard.summary.text && (
            <div className="advice-card__summary">
              <p className="advice-card__summary-text">{dashboard.summary.text}</p>
              <span className="advice-card__summary-source">{dashboard.summary.source}</span>
            </div>
          )}
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
