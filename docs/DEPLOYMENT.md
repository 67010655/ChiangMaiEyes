# Deployment Guide

## Backend: Vercel FastAPI

The backend is deployed as a separate Vercel project named `backend`.

1. Push the repository to GitHub.
2. In Vercel project `backend`, set Root Directory to `backend`.
3. Vercel uses `backend/pyproject.toml` and `backend/api/index.py`.
4. Set environment variables:
   - `CORS_ORIGINS=https://chiangmaieyes.vercel.app`
   - `VITE_GROQ_API_KEY` for the frontend advisor.

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

Current production frontend:

```text
https://chiangmaieyes.vercel.app
```

## Hotspot Refresh Worker

RFD blocks non-Thai infrastructure. Production hotspot freshness therefore
depends on the local Windows refresh worker:

```text
Thai-network PC -> refresh_snapshot.py -> JSON snapshot -> git push -> Vercel deploy
```

The worker is registered in two ways:

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
