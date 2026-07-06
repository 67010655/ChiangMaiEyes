import { useState } from "react";
import { BarChart3, Box, ClipboardList, Eye, Bell, RefreshCcw, Printer, Navigation, FileText, Flame, BookOpen } from "lucide-react";

import "./styles/app.css";

import { useDashboard } from "./hooks/useDashboard";
import { AnalyticsPanel } from "./components/analytics/AnalyticsPanel";
import { LegendPanel } from "./components/analytics/LegendPanel";
import { MapView } from "./components/map/MapView";
import { MapLibreTerrainView } from "./features/threeD/MapLibreTerrainView";
import { ReportPanel } from "./components/analytics/ReportPanel";
import { FirePhasePanel } from "./features/firePhase/FirePhasePanel";

type Tab = "analytics" | "report" | "terrain" | "phase" | "guide";

const TABS: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
  { id: "analytics", label: "วิเคราะห์", icon: BarChart3 },
  { id: "phase", label: "เฟสไฟ", icon: Flame },
  { id: "terrain", label: "3D", icon: Box },
  { id: "report", label: "รายงาน", icon: ClipboardList },
  { id: "guide", label: "คู่มือ", icon: BookOpen },
];

const GUIDE_CARD_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: 16,
  padding: 18,
  boxShadow: "var(--shadow-sm)",
  display: "flex",
  flexDirection: "column",
  gap: 12,
  overflowY: "auto",
};

const GUIDE_SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "ระบบนี้ใช้ทำอะไร",
    body: [
      "ติดตามจุดความร้อน ฝุ่น PM2.5 ทิศทางลม และความเสี่ยงไฟป่าในจังหวัดเชียงใหม่ ใช้ได้ทั้งหน่วยงานระดับภาพรวมและทีมปฏิบัติงานในพื้นที่ เช่น ป่าชุมชน อบต. ผู้ใหญ่บ้าน",
    ],
  },
  {
    title: "ก่อนเกิดไฟ — วางแผนป้องกัน",
    body: [
      "ดูแท็บ \"เฟสไฟ\": พื้นที่สีเหลืองคือช่วงเสี่ยงก่อนเกิดไฟ ใช้ร่วมกับทิศทางลมและความชื้นบนแผนที่เพื่อวางแนวกันไฟหรือจัดการเชื้อเพลิง",
      "ค่าความเสี่ยงเชื้อเพลิงตอนนี้คำนวณระดับอำเภอ ยังไม่ละเอียดถึงรายหมู่บ้าน ใช้ประกอบการตัดสินใจ ไม่ใช่ค่าตายตัว",
    ],
  },
  {
    title: "ระหว่างเกิดไฟ — ติดตามและรับมือ",
    body: [
      "จุดความร้อน (hotspot) บนแผนที่มาจากดาวเทียม NASA/GISTDA อาจดีเลย์ 4-5 ชั่วโมง ให้ดูป้าย \"ตรวจล่าสุด/ควรตรวจซ้ำ/ข้อมูลค้าง\" ที่แถบข้อมูลก่อนเชื่อว่าไฟยังลุกอยู่จริง",
      "เฟสไฟสีแดง = กำลังเกิดไฟ ใช้ร่วมกับทิศทางลมบนแผนที่ช่วยประเมินทิศทางที่ควรเฝ้าระวัง",
    ],
  },
  {
    title: "หลังเกิดไฟ — ฟื้นฟูและรายงาน",
    body: [
      "แท็บ \"รายงาน\" สรุปสถานการณ์ พิมพ์หรือบันทึกเป็น PDF ส่งต่อหน่วยงานหรือรายงานผลการทำงานได้",
    ],
  },
  {
    title: "สัญลักษณ์ข้อมูลที่ต้องรู้",
    body: [
      "LIVE = ดึงสดตอนนี้, SNAPSHOT = ข้อมูลจริงแต่รีเฟรชเป็นรอบ, PROTOTYPE = ข้อมูลตัวอย่าง/จำลอง ยังไม่ใช่ของจริง — ดูป้ายกำกับก่อนอ้างอิงตัวเลขไปใช้งานจริงเสมอ",
      "ปุ่ม DEMO/LIVE มุมบนขวา: LIVE ดึงข้อมูลจริงจากเซิร์ฟเวอร์ DEMO ใช้ข้อมูลตัวอย่างสำหรับสาธิตหรือตอนอินเทอร์เน็ตมีปัญหา",
    ],
  },
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
          {tab === "guide" && (
            <div style={GUIDE_CARD_STYLE}>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 700, display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
                <BookOpen size={18} style={{ color: "var(--green-deep)" }} />
                <span>คู่มือการใช้งาน</span>
              </h3>
              {GUIDE_SECTIONS.map(({ title, body }) => (
                <details key={title} open={title === GUIDE_SECTIONS[0].title}>
                  <summary style={{ fontSize: "0.85rem", fontWeight: 600, cursor: "pointer", color: "var(--text)" }}>
                    {title}
                  </summary>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
                    {body.map((paragraph) => (
                      <p key={paragraph} style={{ fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.5, margin: 0 }}>
                        {paragraph}
                      </p>
                    ))}
                  </div>
                </details>
              ))}
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
