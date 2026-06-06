import { useState } from 'react';
import {
  Map as MapIcon,
  BarChart3,
  ShieldCheck,
  Users,
  Settings,
  Flame,
  TreePine,
  Radar,
  Activity as ActivityIcon,
  CalendarDays,
  CloudSun,
  Trophy,
  Medal,
  ArrowRight,
  FileText,
  Camera,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react';
import { InfographicMap } from './InfographicMap';
import {
  DISTRICT_META,
  healthBand,
  LEAGUE,
  PROVINCE_STATS,
  WORKFLOW,
  type DistrictMeta,
} from './pitchData';
import './pitch.css';

const META_BY_NAME = new Map(DISTRICT_META.map((m) => [m.name, m]));

const STAT_ICONS = [TreePine, MapIcon, Users, ShieldCheck];
const WORKFLOW_ICONS = [FileText, Camera, CheckCircle2, TrendingUp];

const NAV = [
  { icon: MapIcon, label: 'แผนที่', active: true },
  { icon: BarChart3, label: 'รายงาน' },
  { icon: ShieldCheck, label: 'กิจกรรม' },
  { icon: Users, label: 'ชุมชน' },
  { icon: Settings, label: 'ตั้งค่า' },
];

const LAYER_DEFS = [
  { key: 'hotspots', label: 'Hotspot', icon: Flame, color: '#c2603f' },
  { key: 'forests', label: 'ป่าชุมชน', icon: TreePine, color: '#0f6b54' },
  { key: 'risk', label: 'Risk Zone', icon: Radar, color: '#d99a4e' },
  { key: 'activity', label: 'Activity', icon: ActivityIcon, color: '#4f7a4a' },
] as const;

const RANK_ACCENT = ['#c79a33', '#9aa3ad', '#b97a4a'];

export function PitchMode() {
  const [layers, setLayers] = useState({
    hotspots: true,
    forests: true,
    risk: true,
    activity: true,
  });
  const [selected, setSelected] = useState('MaeChaem');

  const selectedMeta: DistrictMeta = META_BY_NAME.get(selected) ?? DISTRICT_META[0];
  const selBand = healthBand(selectedMeta.health);
  const selBandLabel =
    selBand === 'green'
      ? 'ปลอดภัย'
      : selBand === 'yellow'
        ? 'เฝ้าระวัง'
        : selBand === 'orange'
          ? 'เสี่ยงสูง'
          : 'เสี่ยงมาก';

  const toggle = (key: keyof typeof layers) =>
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="pm-shell">
      {/* sidebar */}
      <aside className="pm-rail">
        <div className="pm-rail__logo" aria-hidden="true">
          <TreePine size={22} />
        </div>
        <nav className="pm-rail__nav">
          {NAV.map((item) => (
            <button
              key={item.label}
              type="button"
              className={`pm-rail__btn ${item.active ? 'is-active' : ''}`}
            >
              <item.icon size={20} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <div className="pm-main">
        {/* header */}
        <header className="pm-header">
          <div className="pm-header__title">
            <span className="pm-brand">
              ChiangMai<strong>Eyes</strong>
            </span>
            <h1>Community Forest Fire Management</h1>
            <p>เชียงใหม่ · Fire Management Zone · Weekly Proof</p>
          </div>
          <div className="pm-header__meta">
            <div className="pm-chip">
              <CalendarDays size={18} />
              <div>
                <span className="pm-chip__top">สัปดาห์ที่ 20</span>
                <span className="pm-chip__sub">12 – 18 พ.ค. 2568</span>
              </div>
            </div>
            <div className="pm-chip">
              <CloudSun size={18} />
              <div>
                <span className="pm-chip__top">อากาศ</span>
                <span className="pm-chip__sub">31°C</span>
              </div>
            </div>
            <div className="pm-chip">
              <div>
                <span className="pm-chip__top">PM2.5</span>
                <span className="pm-chip__sub pm-chip__sub--ok">37 · ดี</span>
              </div>
            </div>
          </div>
        </header>

        <div className="pm-grid">
          {/* left column */}
          <div className="pm-left">
            <section className="pm-panel">
              <h2 className="pm-panel__title">Layer</h2>
              <ul className="pm-layers">
                {LAYER_DEFS.map((layer) => {
                  const on = layers[layer.key as keyof typeof layers];
                  return (
                    <li key={layer.key}>
                      <span className="pm-layer__icon" style={{ color: layer.color }}>
                        <layer.icon size={16} />
                      </span>
                      <span className="pm-layer__label">{layer.label}</span>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={on}
                        aria-label={`สลับชั้น ${layer.label}`}
                        className={`pm-switch ${on ? 'is-on' : ''}`}
                        onClick={() => toggle(layer.key as keyof typeof layers)}
                      >
                        <span className="pm-switch__knob" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>

            <section className="pm-panel">
              <h2 className="pm-panel__title">ภาพรวมจังหวัดเชียงใหม่</h2>
              <ul className="pm-stats">
                {PROVINCE_STATS.map((stat, i) => {
                  const Icon = STAT_ICONS[i];
                  return (
                    <li key={stat.label}>
                      <span className="pm-stat__icon">
                        <Icon size={18} />
                      </span>
                      <div className="pm-stat__body">
                        <span className="pm-stat__label">{stat.label}</span>
                        <span className="pm-stat__value">
                          {stat.value} <em>{stat.unit}</em>
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <p className="pm-updated">ข้อมูลอัปเดตล่าสุด 18 พ.ค. 2568</p>
            </section>
          </div>

          {/* center map */}
          <div className="pm-center">
            <InfographicMap layers={layers} selected={selected} onSelect={setSelected} />
          </div>

          {/* right column */}
          <div className="pm-right">
            <section className="pm-league">
              <div className="pm-league__head">
                <Trophy size={22} />
                <div>
                  <h2>Weekly Forest League</h2>
                  <p>จัดอันดับการจัดการไฟป่าชุมชนประจำสัปดาห์</p>
                </div>
              </div>
              <ul className="pm-league__list">
                {LEAGUE.map((row) => (
                  <li key={row.rank} className={`pm-league__row ${row.rank <= 3 ? 'is-podium' : ''}`}>
                    <span
                      className="pm-league__rank"
                      style={row.rank <= 3 ? { color: RANK_ACCENT[row.rank - 1] } : undefined}
                    >
                      {row.rank <= 3 ? <Medal size={20} /> : null}
                      {row.rank}
                    </span>
                    <span className="pm-league__badge">
                      <ShieldCheck size={16} />
                    </span>
                    <div className="pm-league__info">
                      <span className="pm-league__village">{row.village}</span>
                      <span className="pm-league__district">{row.district}</span>
                      <div className="pm-league__tags">
                        {row.tags.map((tag) => (
                          <span key={tag}>{tag}</span>
                        ))}
                      </div>
                    </div>
                    <div className="pm-league__score">
                      <span className="pm-league__score-label">คะแนน</span>
                      <strong>{row.score}</strong>
                    </div>
                  </li>
                ))}
              </ul>
              <button type="button" className="pm-league__more">
                ดูอันดับทั้งหมด <ArrowRight size={15} />
              </button>
            </section>

            <section className="pm-zone">
              <div className="pm-zone__head">
                <span>พื้นที่ที่เลือก</span>
              </div>
              <div className="pm-zone__body">
                <div className="pm-zone__thumb" aria-hidden="true">
                  <TreePine size={26} />
                </div>
                <div className="pm-zone__info">
                  <div className="pm-zone__name">
                    <strong>อ.{selectedMeta.label}</strong>
                    <span className={`pm-zone__tag pm-zone__tag--${selBand}`}>{selBandLabel}</span>
                  </div>
                  <span className="pm-zone__metric">Health Score</span>
                  <div className="pm-zone__score">
                    <strong>{selectedMeta.health}</strong>
                    <span>/ 100</span>
                  </div>
                  <div className="pm-zone__bar">
                    <div
                      className={`pm-zone__bar-fill pm-zone__bar-fill--${selBand}`}
                      style={{ width: `${selectedMeta.health}%` }}
                    />
                  </div>
                  <span className="pm-zone__forests">
                    {selectedMeta.forests} จุดป่าชุมชน
                  </span>
                </div>
              </div>
            </section>
          </div>
        </div>

        {/* workflow */}
        <footer className="pm-flow">
          <div className="pm-flow__intro">
            <span className="pm-flow__icon">
              <TreePine size={20} />
            </span>
            <span>
              Community
              <br />
              Report Workflow
            </span>
          </div>
          {WORKFLOW.map((item, i) => {
            const Icon = WORKFLOW_ICONS[i];
            return (
              <div key={item.step} className="pm-flow__step">
                <span className="pm-flow__num">{item.step}</span>
                <span className="pm-flow__step-icon">
                  <Icon size={20} />
                </span>
                <div className="pm-flow__text">
                  <strong>{item.title}</strong>
                  <span>{item.desc}</span>
                </div>
                {i < WORKFLOW.length - 1 && <ArrowRight className="pm-flow__arrow" size={18} />}
              </div>
            );
          })}
        </footer>
      </div>
    </div>
  );
}
