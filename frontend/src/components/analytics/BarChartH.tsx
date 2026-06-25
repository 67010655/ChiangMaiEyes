export type BarItem = {
  label: string;
  value: number;
  color?: string;
};

type BarChartHProps = {
  title: string;
  icon?: string;
  items: BarItem[];
  unit?: string;
  hint?: string;
  emptyText?: string;
};

// Horizontal bar chart (By Landcover / By District). Pure CSS bars, no chart
// library — matches the existing dependency-free chart style in the app.
export function BarChartH({
  title,
  icon,
  items,
  unit = "",
  hint,
  emptyText = "ยังไม่มีข้อมูล",
}: BarChartHProps) {
  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <section className="chart-card">
      <div className="chart-card__head">
        <span className="chart-card__title">
          {icon ? <span aria-hidden>{icon}</span> : null}
          {title}
        </span>
        {hint ? <span className="chart-card__hint">{hint}</span> : null}
      </div>

      {items.length === 0 ? (
        <p className="chart-empty">{emptyText}</p>
      ) : (
        <div className="barh">
          {items.map((item) => (
            <div className="barh__row" key={item.label}>
              <span className="barh__label" title={item.label}>
                {item.label}
              </span>
              <div className="barh__track">
                <div
                  className="barh__fill"
                  style={{
                    width: `${(item.value / max) * 100}%`,
                    ...(item.color ? { background: item.color } : {}),
                  }}
                />
              </div>
              <span className="barh__value">
                {item.value}
                {unit}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
