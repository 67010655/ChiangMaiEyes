import { useEffect, useState } from "react";
import { Flame, Wind, Trees, AlertTriangle, CheckCircle, Clock } from "lucide-react";

import { fetchFirePhases } from "../../lib/api";
import type {
  DashboardResponse,
  DistrictFirePhase,
  FirePhaseResponse,
  FirePm25Correlation,
} from "../../lib/types";

type Props = { dashboard: DashboardResponse };

const PHASE_LABEL: Record<string, string> = {
  during: "ระหว่างไฟ",
  before: "ก่อนไฟ",
  after: "หลังไฟ",
  normal: "ปกติ",
};
const PHASE_BG: Record<string, string> = {
  during: "#fef2f2",
  before: "#fefce8",
  after: "#f1f5f9",
  normal: "#f0fdf4",
};
const PHASE_BORDER: Record<string, string> = {
  during: "#fca5a5",
  before: "#fde68a",
  after: "#cbd5e1",
  normal: "#86efac",
};
const PHASE_BADGE: Record<string, string> = {
  during: "#dc2626",
  before: "#d97706",
  after: "#64748b",
  normal: "#16a34a",
};

function PhaseBadge({ phase }: { phase: string }) {
  return (
    <span
      style={{
        background: PHASE_BADGE[phase] ?? "#6b7280",
        color: "#fff",
        fontSize: "0.68rem",
        fontWeight: 700,
        padding: "2px 8px",
        borderRadius: 99,
        letterSpacing: "0.02em",
      }}
    >
      {PHASE_LABEL[phase] ?? phase}
    </span>
  );
}

function SpreadArrow({ deg }: { deg: number }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 22 22"
      style={{ transform: `rotate(${deg}deg)`, flexShrink: 0 }}
    >
      <circle cx="11" cy="11" r="10" fill="#fef3c7" stroke="#f59e0b" strokeWidth="1.5" />
      <path d="M11 4 L11 18 M11 4 L7 9 M11 4 L15 9" stroke="#b45309" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PhaseCard({ p }: { p: DistrictFirePhase }) {
  const [open, setOpen] = useState(p.phase === "during" || p.phase === "before");
  const inPath = p.nearby_forests.filter((f) => f.in_spread_path);
  const notInPath = p.nearby_forests.filter((f) => !f.in_spread_path);

  return (
    <div
      style={{
        background: PHASE_BG[p.phase],
        border: `1px solid ${PHASE_BORDER[p.phase]}`,
        borderRadius: 10,
        marginBottom: 8,
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "9px 12px",
          background: "none",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
        }}
        onClick={() => setOpen((v) => !v)}
      >
        <PhaseBadge phase={p.phase} />
        <span style={{ fontWeight: 700, fontSize: "0.85rem", flex: 1 }}>
          อ.{p.district}
          {p.active_hotspots > 0 && (
            <span style={{ color: "#dc2626", marginLeft: 6, fontWeight: 800 }}>
              🔥 {p.active_hotspots} จุด
            </span>
          )}
        </span>
        <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>
          {(p.danger_score * 100).toFixed(0)}%
        </span>
        <span style={{ color: "#9ca3af", fontSize: "0.8rem" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          {/* Reasons */}
          {p.reasons.length > 0 && (
            <div style={{ fontSize: "0.77rem", color: "#374151", marginBottom: 8 }}>
              {p.reasons.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 4, marginBottom: 2 }}>
                  <span style={{ color: "#9ca3af" }}>•</span> {r}
                </div>
              ))}
            </div>
          )}

          {/* Spread projection (during phase) */}
          {p.spread_projection && (
            <div
              style={{
                background: "#fff7ed",
                border: "1px solid #fed7aa",
                borderRadius: 8,
                padding: "8px 10px",
                marginBottom: 8,
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
              }}
            >
              <SpreadArrow deg={p.spread_projection.direction_deg} />
              <div style={{ fontSize: "0.76rem" }}>
                <b style={{ color: "#9a3412" }}>
                  คาดลามทิศ{p.spread_projection.direction_text}
                </b>
                <div style={{ color: "#78350f", marginTop: 2 }}>
                  ~{p.spread_projection.km_6h} กม./6ชม. ·{" "}
                  ~{p.spread_projection.km_12h} กม./12ชม. ·{" "}
                  ~{p.spread_projection.km_24h} กม./24ชม.
                </div>
                <div style={{ color: "#92400e", marginTop: 1 }}>
                  อัตราลาม {p.spread_projection.rate_kmh} กม./ชม. (ประมาณ)
                </div>
              </div>
            </div>
          )}

          {/* Coordination note */}
          {p.coordination_note && (
            <div
              style={{
                background: "#fff1f2",
                border: "1px solid #fecdd3",
                borderRadius: 8,
                padding: "7px 10px",
                marginBottom: 8,
                fontSize: "0.76rem",
                color: "#9f1239",
                display: "flex",
                gap: 6,
                alignItems: "flex-start",
              }}
            >
              <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              {p.coordination_note}
            </div>
          )}

          {/* Nearby forests */}
          {p.nearby_forests.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              {inPath.length > 0 && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{ fontSize: "0.72rem", color: "#dc2626", fontWeight: 700, marginBottom: 3 }}>
                    <Wind size={11} style={{ marginRight: 3 }} />
                    ป่าชุมชนในแนวปลายลม ({inPath.length})
                  </div>
                  {inPath.map((f) => (
                    <div
                      key={f.name + f.distance_km}
                      style={{
                        display: "flex",
                        gap: 6,
                        fontSize: "0.73rem",
                        padding: "2px 0",
                        color: f.fire_management_active ? "#166534" : "#991b1b",
                      }}
                    >
                      <span>{f.fire_management_active ? "✓" : "!"}</span>
                      <span style={{ flex: 1 }}>{f.name} อ.{f.amphoe}</span>
                      <span style={{ color: "#6b7280" }}>{f.distance_km} กม.</span>
                    </div>
                  ))}
                </div>
              )}
              {notInPath.length > 0 && (
                <details style={{ fontSize: "0.72rem" }}>
                  <summary style={{ cursor: "pointer", color: "#6b7280", userSelect: "none" }}>
                    ป่าชุมชนใกล้เคียงอื่น ({notInPath.length} แห่ง)
                  </summary>
                  {notInPath.slice(0, 5).map((f) => (
                    <div
                      key={f.name + f.distance_km}
                      style={{ display: "flex", gap: 6, padding: "2px 0", color: "#4b5563" }}
                    >
                      <span style={{ color: f.fire_management_active ? "#16a34a" : "#9ca3af" }}>
                        {f.fire_management_active ? "✓" : "○"}
                      </span>
                      <span style={{ flex: 1 }}>{f.name}</span>
                      <span style={{ color: "#9ca3af" }}>{f.distance_km} กม.</span>
                    </div>
                  ))}
                </details>
              )}
            </div>
          )}

          {/* Recommended actions */}
          {p.recommended_actions.length > 0 && (
            <div
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: "8px 10px",
              }}
            >
              <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "#334155", marginBottom: 5 }}>
                <CheckCircle size={11} style={{ marginRight: 3 }} />
                แนวทางปฏิบัติ
              </div>
              {p.recommended_actions.map((a, i) => (
                <div key={i} style={{ fontSize: "0.73rem", color: "#475569", display: "flex", gap: 5, marginBottom: 3 }}>
                  <span style={{ color: "#94a3b8" }}>{i + 1}.</span> {a}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CorrelationTable({ rows }: { rows: FirePm25Correlation[] }) {
  if (rows.length === 0) return null;

  const elevated = rows.filter((r) => r.elevated);

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "12px",
        marginTop: 8,
      }}
    >
      <div style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: 8, display: "flex", gap: 6, alignItems: "center" }}>
        <Clock size={14} />
        ความสัมพันธ์จุดความร้อน ↔ PM2.5 (30 วัน)
        {elevated.length > 0 && (
          <span style={{ fontSize: "0.68rem", background: "#fef3c7", color: "#92400e", padding: "1px 6px", borderRadius: 99 }}>
            {elevated.length} วันที่ PM2.5 สูง
          </span>
        )}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.72rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--line)", color: "#6b7280" }}>
              <th style={{ textAlign: "left", padding: "3px 6px" }}>วันที่</th>
              <th style={{ textAlign: "right", padding: "3px 6px" }}>จุดความร้อน</th>
              <th style={{ textAlign: "right", padding: "3px 6px" }}>PM2.5 วันนั้น</th>
              <th style={{ textAlign: "right", padding: "3px 6px" }}>PM2.5 วันถัดมา</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 15).map((r) => (
              <tr
                key={r.date}
                style={{
                  background: r.elevated ? "#fef9c3" : "transparent",
                  borderBottom: "1px solid var(--line)",
                }}
              >
                <td style={{ padding: "3px 6px" }}>{r.date}</td>
                <td style={{ textAlign: "right", padding: "3px 6px", fontWeight: 600, color: "#ea580c" }}>
                  {r.hotspot_count}
                </td>
                <td style={{ textAlign: "right", padding: "3px 6px", color: r.pm25_same_day != null && r.pm25_same_day > 37.5 ? "#dc2626" : "#374151" }}>
                  {r.pm25_same_day != null ? r.pm25_same_day.toFixed(1) : "—"}
                </td>
                <td style={{ textAlign: "right", padding: "3px 6px", color: r.pm25_next_day != null && r.pm25_next_day > 37.5 ? "#dc2626" : "#374151" }}>
                  {r.pm25_next_day != null ? r.pm25_next_day.toFixed(1) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: "0.67rem", color: "#9ca3af", marginTop: 6 }}>
        PM2.5 สีแดง = เกิน 37.5 µg/m³ (เริ่มมีผลต่อสุขภาพ) · แหล่ง: NASA FIRMS + Open-Meteo Air Quality
      </div>
    </div>
  );
}

export function FirePhasePanel({ dashboard }: Props) {
  const [data, setData] = useState<FirePhaseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchFirePhases()
      .then((nextData) => {
        if (active) setData(nextData);
      })
      .catch((e) => {
        if (!active) return;
        setError(e instanceof Error ? e.message : "โหลดข้อมูลไม่สำเร็จ");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [dashboard.hotspots.latest_update]);

  if (loading && !data) {
    return (
      <div style={{ padding: 24, color: "var(--muted)", fontSize: "0.85rem", textAlign: "center" }}>
        กำลังโหลดข้อมูลเฟสไฟ…
      </div>
    );
  }
  if (!data) {
    return (
      <div style={{ padding: 16, color: "#dc2626", fontSize: "0.82rem" }}>
        ⚠ {error ?? "ไม่มีข้อมูล"}
      </div>
    );
  }

  const during = data.phases.filter((p) => p.phase === "during");
  const before = data.phases.filter((p) => p.phase === "before");
  const after = data.phases.filter((p) => p.phase === "after");
  const normal = data.phases.filter((p) => p.phase === "normal");

  return (
    <div style={{ overflowY: "auto", height: "100%", padding: "0 2px" }}>
      {/* Phase summary chips */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12, paddingTop: 4 }}>
        {during.length > 0 && (
          <span style={{ background: "#fee2e2", color: "#991b1b", fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: 99 }}>
            🔴 ระหว่างไฟ {during.length} อำเภอ
          </span>
        )}
        {before.length > 0 && (
          <span style={{ background: "#fef9c3", color: "#92400e", fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: 99 }}>
            🟡 ก่อนไฟ {before.length} อำเภอ
          </span>
        )}
        {after.length > 0 && (
          <span style={{ background: "#f1f5f9", color: "#475569", fontSize: "0.72rem", fontWeight: 700, padding: "3px 10px", borderRadius: 99 }}>
            ⬜ หลังไฟ {after.length} อำเภอ
          </span>
        )}
        {normal.length > 0 && (
          <span style={{ background: "#dcfce7", color: "#166534", fontSize: "0.72rem", padding: "3px 10px", borderRadius: 99 }}>
            🟢 ปกติ {normal.length} อำเภอ
          </span>
        )}
      </div>

      {/* Source note */}
      <div style={{ fontSize: "0.68rem", color: "#9ca3af", marginBottom: 10, lineHeight: 1.4 }}>
        <Trees size={10} style={{ marginRight: 3 }} />
        ป่าชุมชน: {data.community_forests_source} · proximity เท่านั้น ไม่ใช่เขตอำนาจจริง
      </div>

      {/* During phase cards */}
      {during.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#dc2626", marginBottom: 6, display: "flex", gap: 5, alignItems: "center" }}>
            <Flame size={13} /> ระหว่างไฟ — ต้องสั่งการทันที
          </div>
          {during.map((p) => <PhaseCard key={p.district} p={p} />)}
        </div>
      )}

      {/* Before phase cards */}
      {before.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#d97706", marginBottom: 6, display: "flex", gap: 5, alignItems: "center" }}>
            <AlertTriangle size={13} /> ก่อนไฟ — เฝ้าระวังและป้องกันเชิงรุก
          </div>
          {before.map((p) => <PhaseCard key={p.district} p={p} />)}
        </div>
      )}

      {/* After phase cards */}
      {after.length > 0 && (
        <div style={{ marginBottom: 4 }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#64748b", marginBottom: 6 }}>
            ⬜ หลังไฟ — ฟื้นฟูและติดตาม
          </div>
          {after.map((p) => <PhaseCard key={p.district} p={p} />)}
        </div>
      )}

      {/* Normal phase — collapsed summary */}
      {normal.length > 0 && (
        <details style={{ marginBottom: 8 }}>
          <summary
            style={{ fontSize: "0.73rem", color: "#6b7280", cursor: "pointer", userSelect: "none", marginBottom: 4 }}
          >
            🟢 อำเภอสถานะปกติ ({normal.length} อำเภอ)
          </summary>
          <div style={{ fontSize: "0.72rem", color: "#6b7280", paddingLeft: 8 }}>
            {normal.map((p) => p.district).join(" · ")}
          </div>
        </details>
      )}

      {/* PM2.5 correlation table */}
      <CorrelationTable rows={data.fire_pm25_correlation} />

      {/* Notes */}
      <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--line)" }}>
        {data.notes.map((n, i) => (
          <div key={i} style={{ fontSize: "0.67rem", color: "#9ca3af", marginBottom: 3, lineHeight: 1.4 }}>
            {n}
          </div>
        ))}
      </div>
    </div>
  );
}
