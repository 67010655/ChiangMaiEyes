import type { CommunityForestRow } from "./communityForestData";
import { SourceModeChip } from "./SourceModeChip";

type Props = {
  rows: CommunityForestRow[];
  selectedId: string | null;
  onSelect: (row: CommunityForestRow) => void;
};

export function WeeklyForestLeagueTable({ rows, selectedId, onSelect }: Props) {
  return (
    <section className="weekly-forest-table" aria-label="อันดับรายสัปดาห์ป่าชุมชน">
      <div className="weekly-forest-table__head">
        <div>
          <span>อันดับรายสัปดาห์</span>
          <strong>ผลงานดูแลไฟป่าชุมชน</strong>
        </div>
        <small>คะแนนรวมจากการจัดการ ป้องกัน ใช้ประโยชน์ และผลลัพธ์เชิงนิเวศ</small>
      </div>

      <div className="weekly-forest-table__scroll">
        <table>
          <thead>
            <tr>
              <th>อันดับ</th>
              <th>ป่าชุมชน</th>
              <th>อำเภอ</th>
              <th>คะแนน</th>
              <th>กิจกรรมเด่น</th>
              <th>รายงาน</th>
              <th>สถานะ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className={selectedId === row.id ? "is-selected" : ""}
                onClick={() => onSelect(row)}
              >
                <td>
                  <span className="weekly-forest-rank">#{row.rank}</span>
                </td>
                <td>
                  <button type="button" onClick={() => onSelect(row)}>
                    <b>{row.forestName}</b>
                    <small>
                      {row.village || row.tambon} · ต.{row.tambon}
                    </small>
                  </button>
                </td>
                <td>{row.amphoe}</td>
                <td>
                  <strong className="weekly-forest-score">{row.score}</strong>
                </td>
                <td>
                  <span className="weekly-forest-reasons">
                    {row.reasons.slice(0, 3).join(" / ") || "รอรายงาน"}
                  </span>
                </td>
                <td>{row.reportCount} ครั้ง</td>
                <td>
                  <SourceModeChip mode={row.sourceMode} />
                  <small className="weekly-forest-boundary">
                    {row.boundarySource || row.boundaryConfidence || "Boundary pending"}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
