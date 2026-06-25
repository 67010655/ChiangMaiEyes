import { useState } from "react";
import { BarChart3, Box, ClipboardList, Eye, Bell, RefreshCcw } from "lucide-react";

import "./styles/app.css";

import { useDashboard } from "./hooks/useDashboard";
import { AnalyticsPanel } from "./components/analytics/AnalyticsPanel";
import { LegendPanel } from "./components/analytics/LegendPanel";
import { MapView } from "./components/map/MapView";

type Tab = "analytics" | "report" | "terrain";

const TABS: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
  { id: "analytics", label: "วิเคราะห์", icon: BarChart3 },
  { id: "terrain", label: "3D", icon: Box },
  { id: "report", label: "รายงาน", icon: ClipboardList },
];

export function App() {
  const { dashboard, history, loading, refresh } = useDashboard();
  const [tab, setTab] = useState<Tab>("analytics");

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__mark" aria-hidden>
            <Eye size={22} />
          </span>
          <div>
            <h1 className="topbar__title">ChiangMaiEyes</h1>
            <p className="topbar__subtitle">
              จุดความร้อน · ฝุ่น PM2.5 · ทิศทางลม
            </p>
          </div>
        </div>

        <div className="topbar__actions">
          <button className="icon-btn icon-btn--primary" type="button" aria-label="แจ้งเตือน">
            <Bell size={18} />
          </button>
          <button
            className="icon-btn"
            type="button"
            onClick={refresh}
            aria-label="อัปเดตข้อมูล"
            data-loading={loading}
          >
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      <div className="layout">
        <nav className="rail" aria-label="เมนูหลัก">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={`rail__btn${tab === id ? " is-active" : ""}`}
              onClick={() => setTab(id)}
            >
              <Icon size={20} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <aside className="panel">
          {tab === "analytics" && (
            <AnalyticsPanel dashboard={dashboard} history={history} />
          )}
          {tab === "terrain" && (
            <div className="chart-card">
              <p className="chart-empty">มุมมอง 3D — กำลังย้ายมาสู่โครงสร้างใหม่</p>
            </div>
          )}
          {tab === "report" && (
            <div className="chart-card">
              <p className="chart-empty">ศูนย์รายงาน — กำลังย้ายมาสู่โครงสร้างใหม่</p>
            </div>
          )}
        </aside>

        <div className="mapwrap">
          <MapView hotspots={dashboard.hotspots.items} />
          <div className="map-legend-overlay">
            <LegendPanel
              shownCount={dashboard.hotspots.items.length}
              totalCount={dashboard.hotspots.count}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
