# API Specification

Base URL locally: `http://localhost:8000`

## GET /api/hotspots

Returns hotspot aggregate and map points.

```json
{
  "count": 134,
  "density_per_100_km2": 3.8,
  "latest_update": "2026-05-30T08:00:00+07:00",
  "source": "cached sample; adapter target: GISTDA API Gateway VIIRS 1-day, NASA FIRMS backup",
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

Returns a Thai summary with maximum 3 sentences. The MVP includes a deterministic fallback summary.

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

## GET /api/data-status

Returns production data freshness and provenance. This endpoint is intentionally
read-only: it reports the current snapshot state and does not fetch upstream
providers.

```json
{
  "mode": "local-refresh-snapshot",
  "latest_update": "2026-06-03T00:43:25+07:00",
  "snapshot_age_minutes": 36,
  "hotspot_count": 18,
  "source": "Royal Forest Department Firemap + NASA FIRMS",
  "source_breakdown": {
    "Royal Forest Department Firemap": 14,
    "NASA FIRMS": 8
  },
  "local_refresh_required": true,
  "vercel_fetches_rfd_directly": false
}
```

## POST /api/advisor/briefing

Returns a short Thai daily briefing generated through the backend advisor proxy.
The request body is:

```json
{
  "dashboard": {}
}
```

The backend reads `GROQ_API_KEYS` from server-side environment variables. The
frontend must not send provider API keys.

## POST /api/advisor/chat

Returns a Thai chat reply from the advisor using the current dashboard context.
The request body is:

```json
{
  "dashboard": {},
  "history": [{ "role": "user", "text": "วันนี้ไปเที่ยวไหนดี" }],
  "user_message": "มีจุดความร้อนแถวไหนบ้าง"
}
```
