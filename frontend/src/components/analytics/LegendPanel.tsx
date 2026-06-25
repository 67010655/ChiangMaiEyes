import { HOTSPOT_AGE_BANDS } from "../../lib/hotspotAge";

type LegendPanelProps = {
  /** total hotspots currently shown, for the header count */
  shownCount?: number;
  totalCount?: number;
};

// Right-side legend, reskinned light. Colour-by-age scale is the single shared
// source (HOTSPOT_AGE_BANDS) so map markers and this legend never drift apart.
export function LegendPanel({ shownCount, totalCount }: LegendPanelProps) {
  return (
    <aside className="legend-panel" aria-label="สัญลักษณ์แผนที่">
      <div className="legend-panel__head">
        <span className="legend-panel__title">สัญลักษณ์ · LEGEND</span>
        {typeof shownCount === "number" && typeof totalCount === "number" ? (
          <span className="legend-panel__count">
            {shownCount} / {totalCount} จุด
          </span>
        ) : null}
      </div>

      <div className="legend-panel__group-label">สีตามอายุจุดความร้อน</div>
      <ul className="legend-scale">
        {HOTSPOT_AGE_BANDS.map((band) => (
          <li className="legend-scale__row" key={band.id}>
            <span
              className="legend-scale__dot"
              style={{ background: band.color }}
              aria-hidden
            />
            <span className="legend-scale__label">{band.label}</span>
            <span className="legend-scale__sub">{band.sublabel}</span>
          </li>
        ))}
      </ul>

      <p className="legend-panel__note">สีจุด = อายุที่ตรวจพบ · ยิ่งแดงยิ่งใหม่</p>
    </aside>
  );
}
