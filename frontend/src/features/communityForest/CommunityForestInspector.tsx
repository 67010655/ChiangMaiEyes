import type { CommunityForestRow } from "./communityForestData";
import { SourceModeChip } from "./SourceModeChip";

type Props = {
  row: CommunityForestRow | null;
};

function formatTime(value: string) {
  if (!value) return "ยังไม่มีรายงาน";
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDelta(value: number | null) {
  if (value === null) return "pending";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function CommunityForestInspector({ row }: Props) {
  if (!row) {
    return (
      <section className="community-forest-inspector community-forest-inspector--empty">
        <span>เลือกป่าชุมชน</span>
        <strong>เลือกป่าชุมชนบนแผนที่หรือในอันดับรายสัปดาห์</strong>
        <p>
          ระบบจะแสดงขอบเขตดูแล กิจกรรมไฟป่า คะแนนรายสัปดาห์ และสถานะข้อมูล
          เพื่อให้คนในพื้นที่เห็นที่มาของตัวเลขก่อนตัดสินใจ
        </p>
      </section>
    );
  }

  return (
    <section className="community-forest-inspector">
      <div className="community-forest-inspector__head">
        <div>
          <span>ป่าชุมชนที่เลือก</span>
          <strong>{row.forestName}</strong>
          <small>
            {row.village || row.tambon} · ต.{row.tambon} · อ.{row.amphoe}
          </small>
        </div>
        <SourceModeChip mode={row.sourceMode} />
      </div>

      <div className="community-forest-inspector__score">
        <span>คะแนนรวม</span>
        <strong>{row.score}</strong>
        <small>รายงานล่าสุด {formatTime(row.lastReportAt)}</small>
      </div>

      <div className="community-forest-inspector__grid">
        <span>
          <b>{row.scoreBreakdown.management}</b>
          การจัดการ
        </span>
        <span>
          <b>{row.scoreBreakdown.prevention}</b>
          ป้องกัน
        </span>
        <span>
          <b>{row.scoreBreakdown.utilization}</b>
          ใช้ประโยชน์
        </span>
        <span>
          <b>{row.scoreBreakdown.ecologicalOutcome}</b>
          นิเวศ
        </span>
      </div>

      <div className="community-forest-inspector__reasons">
        <span>กิจกรรมเด่น</span>
        <p>{row.reasons.join(" / ") || "รอรายงานภาคสนาม"}</p>
      </div>

      <div className="community-forest-inspector__authority">
        <span>
          <b>Authority</b>
          {row.authorityOwner || "Pending owner"}
        </span>
        <span>
          <b>Boundary</b>
          {row.boundarySource || "Pending boundary source"}
        </span>
        <span>
          <b>Confidence</b>
          {row.boundaryConfidence || "pending"}
        </span>
        <span>
          <b>Verification</b>
          {row.verificationStatus || "pending"}
        </span>
        <span>
          <b>Fire activity</b>
          {formatDelta(row.hotspotActivityDeltaPercent)}
        </span>
      </div>

      {row.satelliteContext && (
        <div className="community-forest-inspector__satellite">
          <span>
            <b>Satellite zone</b>
            {row.satelliteContext.nearestZoneName}
          </span>
          <span>
            <b>Dryness</b>
            {row.satelliteContext.drynessClass}
          </span>
          <span>
            <b>Fire pressure</b>
            {row.satelliteContext.firePressureIndex}
          </span>
          <span>
            <b>NDVI / NDMI</b>
            {row.satelliteContext.ndvi.toFixed(2)} /{" "}
            {row.satelliteContext.ndmi.toFixed(2)}
          </span>
        </div>
      )}

      <div className="community-forest-inspector__truth">
        <b>หมายเหตุข้อมูล</b>
        <p>
          ขอบเขตและอันดับชุดนี้ยังใช้ข้อมูลต้นแบบ/ข้อมูลคำนวณ
          ก่อนเชื่อมฐานรายงานที่ยืนยันแล้ว จึงต้องแสดงสถานะข้อมูลทุกครั้ง
        </p>
      </div>
    </section>
  );
}
