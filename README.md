# ChiangMaiEyes

Public environmental intelligence dashboard for Chiang Mai, Thailand.

## Stack

- Frontend: React, Vite, TypeScript, Leaflet, OpenStreetMap
- Backend: Python, FastAPI
- Database: none for MVP, cached JSON files only
- Deployment: Vercel frontend and Vercel FastAPI backend
- Hotspots: Vercel backend fetches cloud-friendly NASA/GISTDA satellite feeds; RFD is optional

## Local Development

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

Set `VITE_API_BASE_URL=http://localhost:8000` for local frontend API calls.
Set AI advisor provider keys only on the backend as `GROQ_API_KEYS`; do not put
provider keys in frontend `VITE_*` variables because they are browser-visible.

## MVP Notes

Production no longer requires the local Thai-network refresh worker for
hotspots. RFD Firemap remains available as optional enrichment, but it is
disabled by default because it blocks some serverless infrastructure. The
production path uses NASA/GISTDA satellite hotspot feeds that the Vercel backend
can fetch directly.
## Project Context

Development decisions and handoff notes from the original build chat are saved in `docs/CHAT_CONTEXT.md`.
