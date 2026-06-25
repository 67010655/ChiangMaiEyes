import { useMemo } from "react";
import type { DashboardResponse, Hotspot } from "../../lib/types";
import "../../styles/report.css";

type ReportPanelProps = {
  dashboard: DashboardResponse;
};

// Helper: Calculate average of an array
function mean(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((sum, val) => sum + val, 0) / arr.length;
}

// Helper: Get PM2.5 category label
function pmAqiLabel(p: number): string {
  return p > 90
    ? "อันตราย"
    : p > 55
    ? "มีผลต่อสุขภาพ"
    : p > 37
    ? "เริ่มมีผลต่อสุขภาพ"
    : "ปานกลาง";
}

// Sizing/intensity scalar: real FRP if present, else a confidence-based proxy
function intensity(h: Hotspot): number {
  return h.frp != null ? h.frp : h.confidence > 70 ? 55 : 22;
}

// Fire spread forecast cones calculation (km only for report display)
function spreadCone(h: Hotspot, windDeg: number, windKmh: number) {
  const km = 2 + windKmh * 0.18 + intensity(h) * 0.03;
  return { km };
}

export function ReportPanel({ dashboard }: ReportPanelProps) {
  const { hotspots, pm25, weather } = dashboard;

  // 1. Filter out critical hotspots (FRP > 90 or confidence > 80 if FRP is null)
  const critHotspots = useMemo(() => {
    return hotspots.items
      .filter((h) => (h.frp ?? 0) > 90 || (h.frp == null && h.confidence > 80))
      .sort((a, b) => (b.frp ?? 0) - (a.frp ?? 0));
  }, [hotspots.items]);

  // 2. PM2.5 statistics (using stations if available, fallback to current average)
  const pmMean = useMemo(() => {
    const stationPms = pm25.stations.map((s) => s.pm25).filter((v) => v != null);
    return stationPms.length > 0 ? Math.round(mean(stationPms)) : Math.round(pm25.current_pm25);
  }, [pm25]);

  const pmPeakV = useMemo(() => {
    const stationPms = pm25.stations.map((s) => s.pm25).filter((v) => v != null);
    return stationPms.length > 0 ? Math.max(...stationPms) : Math.round(pm25.current_pm25);
  }, [pm25]);

  // 3. AQI estimation
  const aqi = Math.round(pmMean * 1.6 + 20);

  // 4. Wind direction details
  const blowTo = (weather.wind_direction_deg + 180) % 360;
  const compass = [
    "เหนือ",
    "ตะวันออกเฉียงเหนือ",
    "ตะวันออก",
    "ตะวันออกเฉียงใต้",
    "ใต้",
    "ตะวันตกเฉียงใต้",
    "ตะวันตก",
    "ตะวันตกเฉียงเหนือ",
  ];
  const blowDir = compass[Math.round(blowTo / 45) % 8];

  // 5. Calculate risk scores for districts present in hotspots
  const rankedDistricts = useMemo(() => {
    const counts = new Map<string, { n: number; frpSum: number }>();
    for (const h of hotspots.items) {
      const d = h.district || "ไม่ระบุ";
      const curr = counts.get(d) ?? { n: 0, frpSum: 0 };
      counts.set(d, {
        n: curr.n + 1,
        frpSum: curr.frpSum + (h.frp ?? 30),
      });
    }

    return Array.from(counts.entries())
      .map(([name, { n, frpSum }]) => {
        const score = Math.round(Math.min(100, frpSum / 3 + n * 8));
        return { name, score, n };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
  }, [hotspots.items]);

  // 6. Overall severity calculation
  const severity = useMemo(() => {
    return critHotspots.length >= 2 || pmMean > 90
      ? "sev"
      : critHotspots.length >= 1 || pmMean > 55
      ? "hi"
      : "mod";
  }, [critHotspots, pmMean]);

  const severityText = {
    sev: "รุนแรง",
    hi: "สูง",
    mod: "ปานกลาง",
  }[severity];

  const dateStr = useMemo(() => {
    try {
      return new Date().toLocaleDateString("th-TH-u-ca-buddhist", {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    } catch (e) {
      return new Date().toLocaleDateString("th-TH");
    }
  }, []);

  const timeStr = useMemo(() => {
    const pad = (n: number) => String(n).padStart(2, "0");
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())} น.`;
  }, []);

  // 7. Dynamic Actionable recommendations
  const recommendations = useMemo(() => {
    const recs: string[] = [];
    if (rankedDistricts.length > 0) {
      const topNames = rankedDistricts.slice(0, 2).map((d) => d.name).join(" และ ");
      recs.push(`ส่งชุดดับไฟ/อาสาสมัครเข้าพื้นที่ <b>${topNames}</b> ซึ่งมีความเสี่ยงสูงสุด`);
    }
    recs.push(
      `เฝ้าระวังการลามไปทาง<b>${blowDir}</b>ตามทิศลม (${Math.round(
        weather.wind_speed_kmh
      )} กม./ชม.) โดยเฉพาะแนวป่าชุมชนปลายลม`
    );
    if (pmMean > 55) {
      recs.push(
        `ออกประกาศเตือนคุณภาพอากาศ — PM2.5 เฉลี่ย <b>${pmMean}</b> µg/m³ แนะนำกลุ่มเสี่ยงงดกิจกรรมกลางแจ้ง`
      );
    }
    if (pmPeakV > 90) {
      recs.push(
        `พิจารณาแจกหน้ากาก/เปิดห้องปลอดฝุ่นในพื้นที่ที่ PM2.5 แตะ <b>${pmPeakV}</b> µg/m³`
      );
    }
    recs.push(
      `ประสานเครือข่ายป่าชุมชนทำแนวกันไฟเชิงรุกในอำเภอเฝ้าระวังสูงสุด ก่อนลมแรงช่วงบ่าย`
    );
    return recs;
  }, [rankedDistricts, blowDir, weather.wind_speed_kmh, pmMean, pmPeakV]);

  // Check if live data or mock data
  const isMock = hotspots.source.toLowerCase().includes("mock");

  return (
    <div className="report-container">
      <div className="report-paper">
        <header className="report-header">
          <div className="report-logo">
            <svg viewBox="0 0 24 24" fill="none" style={{ width: 28, height: 28 }}>
              <path
                d="M2.5 12 C6 6.5,18 6.5,21.5 12 C18 17.5,6 17.5,2.5 12 Z"
                stroke="#fff"
                strokeWidth="1.7"
                fill="rgba(255,255,255,.08)"
              />
              <circle cx="12" cy="12" r="3.6" stroke="#fff" strokeWidth="1.7" fill="none" />
              <circle cx="12" cy="12" r="1.3" fill="#fff" />
            </svg>
          </div>
          <div>
            <h1>รายงานสถานการณ์ไฟป่าและคุณภาพอากาศ</h1>
            <div className="report-meta">ChiangMaiEyes · จังหวัดเชียงใหม่ · รายงานประจำวัน</div>
          </div>
          <div className="report-stamp">
            {dateStr}
            <br />
            เวลา {timeStr}
            <br />
            <span className={`report-stamp__badge badge--${severity}`}>
              ระดับ{severityText}
            </span>
          </div>
        </header>

        <p className="report-lead">
          วันนี้ตรวจพบจุดความร้อนทั้งหมด <b>{hotspots.count}</b> จุด ในจำนวนนี้เป็นจุดวิกฤต <b>{critHotspots.length}</b> จุด
          ค่าฝุ่น PM2.5 เฉลี่ยอยู่ที่ <b>{pmMean}</b> µg/m³ (AQI {aqi}) ระดับ{pmAqiLabel(pmMean)}
          ลมพัดจากทิศ{weather.wind_direction_text} {Math.round(weather.wind_speed_kmh)} กม./ชม. ทำให้ควันและความเสี่ยงไฟลามไปทาง{blowDir}
          {rankedDistricts.length > 0 && (
            <> พื้นที่ที่ต้องเฝ้าระวังสูงสุดคือ <b>{rankedDistricts[0].name}</b></>
          )}
        </p>

        <h2 className="report-section-title">
          <span className="report-section-number">1</span>ตัวเลขสำคัญ
        </h2>
        <div className="report-kpis">
          <div className="report-kpi">
            <div className="report-kpi__label">จุดความร้อน</div>
            <div className="report-kpi__value">
              {hotspots.count}
              <small> จุด</small>
            </div>
          </div>
          <div className="report-kpi">
            <div className="report-kpi__label">จุดวิกฤต</div>
            <div className="report-kpi__value" style={{ color: "#b91c1c" }}>
              {critHotspots.length}
              <small> จุด</small>
            </div>
          </div>
          <div className="report-kpi">
            <div className="report-kpi__label">PM2.5 เฉลี่ย</div>
            <div className="report-kpi__value">
              {pmMean}
              <small> µg/m³</small>
            </div>
          </div>
          <div className="report-kpi">
            <div className="report-kpi__label">PM2.5 สูงสุด</div>
            <div className="report-kpi__value" style={{ color: "#7e22ce" }}>
              {pmPeakV}
              <small> µg/m³</small>
            </div>
          </div>
        </div>

        <h2 className="report-section-title">
          <span className="report-section-number">2</span>พื้นที่เฝ้าระวัง (ดัชนีสะสม)
        </h2>
        <table className="report-table">
          <thead>
            <tr>
              <th style={{ width: "8%" }}>#</th>
              <th style={{ width: "32%" }}>อำเภอ</th>
              <th style={{ width: "20%" }}>จุดความร้อน</th>
              <th style={{ width: "20%" }}>ดัชนีความเสี่ยง</th>
              <th style={{ width: "20%" }}>ระดับการติดตาม</th>
            </tr>
          </thead>
          <tbody>
            {rankedDistricts.length > 0 ? (
              rankedDistricts.map((r, i) => {
                const lv = r.score > 70 ? "sev" : r.score > 45 ? "hi" : "mod";
                const lvT = { sev: "เฝ้าระวังสูงสุด", hi: "เฝ้าระวัง", mod: "ติดตาม" }[lv];
                return (
                  <tr key={r.name}>
                    <td>{i + 1}</td>
                    <td>
                      <b>{r.name}</b>
                    </td>
                    <td>{r.n}</td>
                    <td>{r.score}</td>
                    <td>
                      <span className={`report-badge badge--${lv}`}>{lvT}</span>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", color: "#7a8694" }}>
                  ไม่มีจุดความร้อนในทุกอำเภอในขณะนี้
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <h2 className="report-section-title">
          <span className="report-section-number">3</span>จุดวิกฤตและการคาดการณ์การลาม
        </h2>
        <table className="report-table">
          <thead>
            <tr>
              <th style={{ width: "15%" }}>รหัส</th>
              <th style={{ width: "25%" }}>อำเภอ</th>
              <th style={{ width: "20%" }}>FRP / ความมั่นใจ</th>
              <th style={{ width: "25%" }}>ทิศลาม/ระยะเสี่ยง</th>
              <th style={{ width: "15%" }}>ความสดของข้อมูล</th>
            </tr>
          </thead>
          <tbody>
            {critHotspots.length > 0 ? (
              critHotspots.slice(0, 6).map((h) => {
                const km = spreadCone(h, weather.wind_direction_deg, weather.wind_speed_kmh)
                  .km.toFixed(1);
                // Calculate age in minutes from detected_at
                const diffMs = Date.now() - new Date(h.detected_at).getTime();
                const ageMinutes = Math.max(0, Math.floor(diffMs / 60000));
                const detectedText = ageMinutes > 60
                  ? `${Math.floor(ageMinutes / 60)} ชม. ก่อน`
                  : `${ageMinutes} นาที ก่อน`;

                return (
                  <tr key={h.id}>
                    <td>
                      <b>{h.id.split("-").slice(-1)[0] || h.id}</b>
                    </td>
                    <td>{h.district}</td>
                    <td>{h.frp ? `${h.frp} MW` : `${h.confidence}%`}</td>
                    <td>
                      {blowDir} ~{km} กม.
                    </td>
                    <td>{detectedText}</td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} style={{ textAlign: "center", color: "#7a8694" }}>
                  ไม่มีจุดวิกฤต (FRP &gt; 90 MW) ในขณะนี้
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <h2 className="report-section-title">
          <span className="report-section-number">4</span>ข้อเสนอแนะเชิงปฏิบัติการ
        </h2>
        <ul className="report-recommendations">
          {recommendations.map((r, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: r }} />
          ))}
        </ul>

        <footer className="report-footer">
          แหล่งข้อมูล: NASA FIRMS (VIIRS/MODIS) · GISTDA · กรมควบคุมมลพิษ (PCD) · OpenWeather
          <br />
          รายงานนี้สร้างอัตโนมัติโดย ChiangMaiEyes — {isMock ? "ข้อมูลชุดสาธิต (DEMO)" : "ข้อมูลสด (LIVE) จาก API"} · ออกเมื่อ {dateStr} {timeStr}
        </footer>
      </div>
    </div>
  );
}
