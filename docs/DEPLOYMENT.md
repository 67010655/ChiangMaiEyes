# Deployment Guide

## Backend: Render Free Tier

1. Push the repository to GitHub.
2. Create a new Render Web Service.
3. Set root directory to `backend`.
4. Build command: `pip install -r requirements.txt`.
5. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
6. Set environment variables:
   - `CORS_ORIGINS=https://your-vercel-app.vercel.app`
   - `GEMINI_API_KEY` only if using Gemini free tier.

## Frontend: Vercel Free Tier

1. Import the same GitHub repository in Vercel.
2. Set root directory to `frontend`.
3. Build command: `npm run build`.
4. Output directory: `dist`.
5. Set environment variable:
   - `VITE_API_BASE_URL=https://your-render-service.onrender.com`

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
