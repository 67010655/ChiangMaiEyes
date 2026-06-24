import type { CommunityForestRow } from "./communityForestData";
import { SourceModeChip } from "./SourceModeChip";

type Props = {
  rows: CommunityForestRow[];
  selectedId: string | null;
  onSelect: (row: CommunityForestRow) => void;
};

export function WeeklyForestRankList({ rows, selectedId, onSelect }: Props) {
  return (
    <section className="weekly-forest-rank-list" aria-label="อันดับรายสัปดาห์">
      <div className="weekly-forest-rank-list__head">
        <strong>อันดับรายสัปดาห์</strong>
        <span>Top 5</span>
      </div>
      {rows.slice(0, 5).map((row) => (
        <button
          key={row.id}
          type="button"
          className={selectedId === row.id ? "is-selected" : ""}
          onClick={() => onSelect(row)}
        >
          <span className="weekly-forest-rank">#{row.rank}</span>
          <span>
            <b>{row.forestName}</b>
            <small>
              อ.{row.amphoe} · {row.reasons.slice(0, 2).join(" / ") || "รอรายงาน"}
            </small>
          </span>
          <strong>{row.score}</strong>
          <SourceModeChip mode={row.sourceMode} />
        </button>
      ))}
    </section>
  );
}
