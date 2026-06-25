import type { Pm25Response, RiskResponse, WeatherResponse } from "../../lib/types";

type StatTilesProps = {
  hotspotCount: number;
  densityPer100Km2: number;
  pm25: Pm25Response;
  risk: RiskResponse;
  weather: WeatherResponse;
};

const pm25ToneClass: Record<Pm25Response["color"], string> = {
  green: "stat-tile__value--green",
  yellow: "stat-tile__value--amber",
  orange: "stat-tile__value--orange",
  red: "stat-tile__value--red",
  purple: "stat-tile__value--purple",
};

function riskToneClass(category: RiskResponse["category"]): string {
  if (category === "High") return "stat-tile__value--red";
  if (category === "Medium") return "stat-tile__value--amber";
  return "stat-tile__value--green";
}

function riskLabel(category: RiskResponse["category"]): string {
  if (category === "High") return "ความเสี่ยงสูง";
  if (category === "Medium") return "ความเสี่ยงปานกลาง";
  return "ความเสี่ยงต่ำ";
}

// Bento KPI grid. All values straight from the live dashboard payload.
export function StatTiles({
  hotspotCount,
  densityPer100Km2,
  pm25,
  risk,
  weather,
}: StatTilesProps) {
  return (
    <div className="stat-bento" aria-label="สรุปตัวเลขสถานการณ์">
      <div className="stat-tile stat-tile--hero">
        <span className="stat-tile__value stat-tile__value--orange">
          {hotspotCount}
        </span>
        <span className="stat-tile__label">จุดความร้อน</span>
        <span className="stat-tile__sub">
          ความหนาแน่น {densityPer100Km2.toFixed(1)} /100 กม.²
        </span>
      </div>

      <div className="stat-tile">
        <span className={`stat-tile__value ${pm25ToneClass[pm25.color]}`}>
          {Math.round(pm25.current_pm25)}
          <span className="stat-tile__unit">µg/m³</span>
        </span>
        <span className="stat-tile__label">PM2.5 · {pm25.category}</span>
      </div>

      <div className="stat-tile">
        <span className={`stat-tile__value ${riskToneClass(risk.category)}`}>
          {risk.score}
          <span className="stat-tile__unit">/10</span>
        </span>
        <span className="stat-tile__label">{riskLabel(risk.category)}</span>
      </div>

      <div className="stat-tile">
        <span className="stat-tile__value">
          {Math.round(weather.wind_speed_kmh)}
          <span className="stat-tile__unit">กม./ชม.</span>
        </span>
        <span className="stat-tile__label">ลม · {weather.wind_direction_text}</span>
      </div>

      <div className="stat-tile">
        <span className="stat-tile__value">
          {Math.round(weather.temperature_c)}
          <span className="stat-tile__unit">°C</span>
        </span>
        <span className="stat-tile__label">
          อุณหภูมิ · ชื้น {Math.round(weather.humidity_percent)}%
        </span>
      </div>
    </div>
  );
}
