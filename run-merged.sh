#!/bin/bash
# Boots the merged stack:
#   - IlyonAI aiohttp sentinel API on :8080 (token/shield/whales/rekt/etc.)
#   - Assistant FastAPI agent backend on :8000 (agent/chats/auth/portfolio)
#   - Next.js shell on :3030 (proxies /api/* to both backends)
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"

trap 'echo "stopping..."; kill 0' EXIT INT TERM

echo "[1/3] IlyonAI sentinel API → :8080"
( cd "$ROOT" && venv/bin/python -m src.main > "$LOGDIR/ilyon_api.log" 2>&1 ) &

echo "[2/3] Assistant FastAPI → :8000"
( cd "$ROOT/IlyonAi-Wallet-assistant-main/server" && venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$LOGDIR/assistant_api.log" 2>&1 ) &

echo "[3/3] Next.js shell → :3030"
( cd "$ROOT/web" && node_modules/.bin/next dev -p 3030 > "$LOGDIR/web_dev.log" 2>&1 ) &

sleep 8
echo
echo "=== status ==="
curl -sS -m 3 -w "  sentinel  :8080  HTTP %{http_code}\n" -o /dev/null http://127.0.0.1:8080/health || echo "  sentinel  :8080  DOWN"
curl -sS -m 3 -w "  assistant :8000  HTTP %{http_code}\n" -o /dev/null http://127.0.0.1:8000/health || echo "  assistant :8000  DOWN"
curl -sS -m 8 -w "  web       :3030  HTTP %{http_code}\n" -o /dev/null http://127.0.0.1:3030/ || echo "  web       :3030  DOWN"
echo
echo "Open  http://localhost:3030/agent/chat  (Ctrl-C stops everything)"
wait
