# Development Roadmap and MVP Implementation Plan

## Phase 1: Hackathon MVP

- Static cached JSON for hotspot, PM2.5, and weather data.
- FastAPI endpoints for individual resources and dashboard aggregate.
- Transparent risk score, no machine learning.
- Rule-based Thai summary fallback.
- React/Vite dashboard with Leaflet and OpenStreetMap.
- Mobile responsive panels and map filters.

## Phase 2: Live Data Adapters

- Keep GISTDA API Gateway VIIRS 1-day as the primary hotspot source and NASA FIRMS as backup.
- Add NASA FIRMS adapter as backup.
- Add Air4Thai adapter and OpenAQ fallback.
- Add TMD adapter and Open-Meteo fallback.
- Write fetched data back to JSON cache on a schedule.

## Phase 3: Operational Polish

- District GeoJSON boundaries.
- Station-level trend sparkline.
- Daily archive files.
- Source freshness badges.
- Better backend advisor prompt guardrails, timeout fallback, and observability.

## Out of Scope for MVP

- Wildfire prediction.
- Paid APIs or paid datasets.
- Paid infrastructure.
- Database-backed historical analytics.
- Atmospheric dispersion modeling.
