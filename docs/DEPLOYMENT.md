# Deployment Guide

## Backend: Vercel FastAPI

The backend is deployed as a separate Vercel project named `backend`.

1. Push the repository to GitHub.
2. In Vercel project `backend`, set Root Directory to `backend`.
3. Vercel uses `backend/pyproject.toml` and `backend/api/index.py`.
4. Set environment variables:
   - `CORS_ORIGINS=https://chiangmaieyes.vercel.app`
   - `GROQ_API_KEYS=gsk_...` for the backend advisor proxy. Multiple keys can be comma-separated.
   - `GISTDA_DISASTER_API_KEY` for GISTDA Disaster STAC hotspot data. A default key is bundled for MVP use.
   - `GISTDA_API_KEY` for optional GISTDA API Gateway VIIRS 1-day data.
   - `NASA_FIRMS_MAP_KEY` for NASA FIRMS VIIRS backup/history. Recommended for production.
   - `HOTSPOT_INCLUDE_RFD=false` unless the environment has reliable Thai egress.

Current production backend:

```text
https://backend-mocha-tau-49.vercel.app
```

## Frontend: Vercel Free Tier

1. Import the same GitHub repository in Vercel project `frontend`.
2. Use repo-root `vercel.json`, which installs/builds `frontend`.
3. Build command: `npm --prefix frontend run build`.
4. Output directory: `frontend/dist`.
5. Set environment variable:
   - `VITE_API_BASE_URL=https://backend-mocha-tau-49.vercel.app`

Do not set provider API keys in the frontend project. Browser-visible `VITE_*`
variables are public, so the AI advisor calls `/api/advisor/*` on the backend
instead of calling Groq directly from the client.

Current production frontend:

```text
https://chiangmaieyes.vercel.app
```

## Hotspot Data Mode

Production does not require the local Windows refresh worker for hotspots. The
backend fetches cloud-friendly NASA/GISTDA satellite feeds directly and caches
responses briefly so the dashboard stays current enough for hourly decisions.

```text
Browser -> Vercel backend -> GISTDA/NASA -> reconciled Chiang Mai hotspot response
```

RFD Firemap is optional enrichment only. If `HOTSPOT_INCLUDE_RFD=true`, use the
legacy Thailand refresh worker because RFD blocks some serverless infrastructure:

- Startup launcher: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\chiangmaieyes-refresh.cmd`
- Scheduled Task: `ChiangMaiEyes hotspot refresh`

See `scripts/README-refresh.md` for setup and troubleshooting.

## Local Run

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.
