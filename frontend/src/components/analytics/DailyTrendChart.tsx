import type { HotspotHistoryDay } from "../../lib/types";

type DailyTrendChartProps = {
  days: HotspotHistoryDay[];
  title?: string;
  color?: (value: number) => string;
};

function shortLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

// Daily hotspot count as vertical bars. Real history from /api/history.
export function DailyTrendChart({
  days,
  title = "จุดความร้อนรายวัน · Daily Trend",
  color,
}: DailyTrendChartProps) {
  const max = Math.max(...days.map((d) => d.count), 1);
  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <section className="chart-card">
      <div className="chart-card__head">
        <span className="chart-card__title">📊 {title}</span>
      </div>

      {days.length === 0 ? (
        <p className="chart-empty">ยังไม่มีข้อมูลย้อนหลัง</p>
      ) : (
        <div className="trend">
          <div className="trend__bars">
            {days.map((d) => {
              const h = Math.max((d.count / max) * 100, 2);
              const isToday = d.date === todayIso;
              return (
                <div
                  key={d.date}
                  className={`trend__col${isToday ? " trend__col--today" : ""}`}
                  title={`${shortLabel(d.date)} · ${d.count} จุด`}
                >
                  <span className="trend__count">{d.count}</span>
                  <div
                    className="trend__bar"
                    style={{
                      height: `${h}%`,
                      ...(color ? { background: color(d.count) } : {}),
                    }}
                  />
                  <span className="trend__axis">{shortLabel(d.date)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
