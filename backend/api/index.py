import os
import sys

# Make `app` importable whether Vercel builds from the repo root (entrypoint
# "backend.api.index:app") or from backend/ (manual `vercel --prod`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

