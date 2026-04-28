#!/bin/bash
set -e
cd "$(dirname "$0")/server"
echo "▶ Starting FastAPI server on http://localhost:8000"
echo "  Docs → http://localhost:8000/docs"
echo "  Health → http://localhost:8000/health"
echo ""
venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
