import { useState } from "react";
import { BarChart3, Box, ClipboardList, Eye, Bell, RefreshCcw, Printer, Navigation, FileText, Flame } from "lucide-react";

import "./styles/app.css";

import { useDashboard } from "./hooks/useDashboard";
import { AnalyticsPanel } from "./components/analytics/AnalyticsPanel";
import { LegendPanel } from "./components/analytics/LegendPanel";
import { MapView } from "./components/map/MapView";
import { MapLibreTerrainView } from "./features/threeD/MapLibreTerrainView";
import { ReportPanel } from "./components/analytics/ReportPanel";
import { FirePhasePanel } from "./features/firePhase/FirePhasePanel";

type Tab = "analytics" | "report" | "terrain" | "phase";

const TABS: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
  { id: "analytics", label: "วิเคราะห์", icon: BarChart3 },
  { id: "phase", label: "เฟสไฟ", icon: Flame },
  { id: "terrain", label: "3D", icon: Box },
  { id: "report", label: "รายงาน", icon: ClipboardList },
];

export function App() {
  const { dashboard, history, loading, refresh, demoMode, setDemoMode } = useDashboard();
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

        <div className="topbar__mode-toggle" role="group" aria-label="โหมดข้อมูล">
          <button
            type="button"
            className={`mode-btn${demoMode ? " is-active" : ""}`}
            onClick={() => setDemoMode(true)}
          >
            DEMO
          </button>
          <button
            type="button"
            className={`mode-btn${!demoMode ? " is-active" : ""}`}
            onClick={() => setDemoMode(false)}
          >
            LIVE
          </button>
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
          {tab === "phase" && (
            <FirePhasePanel dashboard={dashboard} />
          )}
          {tab === "terrain" && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 16, padding: 18, boxShadow: "var(--shadow-sm)" }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8, margin: "0 0 10px 0" }}>
                <Navigation size={18} style={{ color: "var(--green-deep)" }} />
                <span>มุมมอง 3D ภูมิประเทศ</span>
              </h3>
              <p style={{ fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.5, margin: "0 0 12px 0" }}>
                แผนที่สามมิติวิเคราะห์จุดความร้อนและฝุ่นร่วมกับความชันและความสูงเชิงตัวเลข (DEM) ของจังหวัดเชียงใหม่
              </p>
              <div style={{ display: "grid", gap: 8 }}>
                <div style={{ fontSize: "0.76rem", padding: 10, border: "1px solid var(--line)", borderRadius: 8, background: "var(--surface-soft)" }}>
                  <b style={{ display: "block", color: "var(--green-deep)", marginBottom: 4 }}>ทิศลากจำลองไฟ:</b>
                  การแสดงทิศทางลมปลายลมช่วยคาดการณ์พื้นที่เฝ้าระวังป่าชุมชน
                </div>
                <div style={{ fontSize: "0.76rem", padding: 10, border: "1px solid var(--line)", borderRadius: 8, background: "var(--surface-soft)" }}>
                  <b style={{ display: "block", color: "var(--green-deep)", marginBottom: 4 }}>การเปลี่ยนทัศนียภาพ:</b>
                  คลิกขวาค้างเพื่อลากหมุนปรับก้มเงย (Pitch & Bearing) หรือใช้เมาส์กลางในการขยายมุมมอง
                </div>
              </div>
            </div>
          )}
          {tab === "report" && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 16, padding: 18, boxShadow: "var(--shadow-sm)", display: "flex", flexDirection: "column", gap: 12 }}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
                <FileText size={18} style={{ color: "var(--green-deep)" }} />
                <span>ศูนย์รายงานประจำวัน</span>
              </h3>
              <p style={{ fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.5, margin: 0 }}>
                สรุปสถานการณ์ไฟป่าและฝุ่นละอองเชิงลึกเพื่อการตัดสินใจเชิงนโยบายและการสั่งการภาคสนาม
              </p>
              <button
                className="icon-btn icon-btn--primary"
                type="button"
                style={{ width: "100%", height: "42px", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 4, cursor: "pointer" }}
                onClick={() => window.print()}
              >
                <Printer size={18} />
                <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>พิมพ์รายงาน / บันทึก PDF</span>
              </button>
            </div>
          )}
        </aside>

        <div className="mapwrap">
          {tab !== "report" ? (
            <>
              {tab === "terrain" ? (
                <MapLibreTerrainView
                  dashboard={dashboard}
                  mapTilerKey={import.meta.env.VITE_MAPTILER_KEY}
                />
              ) : (
                <MapView hotspots={dashboard.hotspots.items} weather={dashboard.weather} />
              )}
              {tab !== "terrain" && (
                <div className="map-legend-overlay">
                  <LegendPanel
                    shownCount={dashboard.hotspots.items.length}
                    totalCount={dashboard.hotspots.count}
                  />
                </div>
              )}
            </>
          ) : (
            <ReportPanel dashboard={dashboard} />
          )}
        </div>
      </div>
    </div>
  );
}
