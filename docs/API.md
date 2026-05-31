# API Specification

Base URL locally: `http://localhost:8000`

## GET /api/hotspots

Returns hotspot aggregate and map points.

```json
{
  "count": 134,
  "density_per_100_km2": 3.8,
  "latest_update": "2026-05-30T08:00:00+07:00",
  "source": "cached sample; adapter target: GISTDA primary, NASA FIRMS backup",
  "items": [{ "id": "HS-001", "latitude": 18.9342, "longitude": 98.7424 }]
}
```

## GET /api/pm25

Returns current PM2.5, category, trend, and stations.

Color categories: `green`, `yellow`, `orange`, `red`, `purple`.

## GET /api/weather

Returns wind speed, wind direction, temperature, and humidity.

## GET /api/risk

Returns transparent risk score.

Formula:

```text
min(10, round(min(PM2.5/15,4) + min(hotspot_count/50,4) + wind_factor))
```

`wind_factor = 2` when wind direction is likely to push smoke toward Chiang Mai city, otherwise `0`.

Categories:

- `0-3`: Low
- `4-6`: Medium
- `7-10`: High

## GET /api/summary

Returns a Thai summary with maximum 3 sentences. The MVP includes a deterministic fallback summary. Gemini free tier can be enabled from `GEMINI_API_KEY`.

## GET /api/dashboard

Returns all panels in one payload:

```json
{
  "hotspots": {},
  "pm25": {},
  "weather": {},
  "risk": {},
  "summary": {}
}
```
