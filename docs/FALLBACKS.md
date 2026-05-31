# Risk and Fallback Strategy

## Free-Tier Constraint

All MVP services must be free or have a free tier suitable for hackathon usage. If a provider requires paid access, the backend keeps using cached JSON and marks the source in the response.

## Data Source Fallbacks

| Data | Primary | Backup | MVP fallback |
| --- | --- | --- | --- |
| Hotspots | GISTDA Disaster daily hotspot update | NASA FIRMS | `backend/data/hotspots.json` |
| PM2.5 | Air4Thai | OpenAQ | `backend/data/pm25.json` |
| Weather | TMD Open Data | Open-Meteo | `backend/data/weather.json` |
| AI summary | Gemini free tier | Rule-based Thai text | `fallback_summary()` |
| Map | OpenStreetMap | Browser cache | Leaflet base map still loads when online |

## Operational Risks

- Public data endpoints may change format or rate limits.
- Render free tier may cold start.
- Vercel frontend needs CORS configured on backend.
- OpenStreetMap tile usage should remain lightweight and attribution must stay visible.
- Gemini can fail, timeout, or exceed free quota; summary must fall back without blocking the dashboard.

## Mitigations

- Keep provider adapters isolated in backend services.
- Cache last successful JSON response.
- Return source and update timestamps in every response.
- Make risk score deterministic and explain the formula in the UI.
- Avoid ML or predictive claims.
