# ChiangMaiEyes

Public environmental intelligence dashboard for Chiang Mai, Thailand.

## Stack

- Frontend: React, Vite, TypeScript, Leaflet, OpenStreetMap
- Backend: Python, FastAPI
- Database: none for MVP, cached JSON files only
- Deployment: Vercel frontend, Render backend

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

## MVP Notes

The MVP ships with cached sample JSON so it runs in a hackathon without paid services. Live providers are isolated behind backend service modules and can be enabled through environment variables.
## Project Context

Development decisions and handoff notes from the original build chat are saved in `docs/CHAT_CONTEXT.md`.
