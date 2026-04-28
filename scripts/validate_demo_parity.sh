#!/usr/bin/env bash
# Boot the server (if not already up), run the demo-parity validator,
# then kill the temporary server we started. Honors ILYON_AGENT_URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BOOTED_PID=""
cleanup() {
  if [[ -n "$BOOTED_PID" ]]; then
    kill "$BOOTED_PID" 2>/dev/null || true
    wait "$BOOTED_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# If port 8080 isn't responding, boot the server.
if ! curl -sS -m 2 -o /dev/null http://localhost:8080/ 2>&1; then
  :
fi

# Probe for a live aiohttp server on :8080
if ! ss -ltn 2>/dev/null | grep -q ':8080 '; then
  echo "→ booting API server on :8080"
  PYTHONPATH="$ROOT" python -m src.main > /tmp/ai-sentinel.parity.log 2>&1 &
  BOOTED_PID=$!
  # Wait up to 30s for readiness
  for _ in $(seq 1 30); do
    if ss -ltn 2>/dev/null | grep -q ':8080 '; then
      break
    fi
    sleep 1
  done
fi

PYTHONPATH="$ROOT" python "$ROOT/scripts/validate_demo_parity.py"
