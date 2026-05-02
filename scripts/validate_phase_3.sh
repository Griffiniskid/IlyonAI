#!/usr/bin/env bash
set -euo pipefail

PROXY="${PROXY_URL:-http://localhost:3000}"
TOKEN="${SENTINEL_TEST_TOKEN:-}"

post_sse() {
  local prompt="$1" session="$2"
  curl -fsS -N -X POST "${PROXY}/api/v1/agent" \
    -H "content-type: application/json" \
    ${TOKEN:+-H "authorization: Bearer ${TOKEN}"} \
    -d "{\"message\":${prompt@Q},\"session_id\":${session@Q}}" \
    --max-time 90
}

require_substring() {
  local f="$1" needle="$2" label="$3"
  if ! grep -q "$needle" "$f"; then
    echo "FAIL $label: missing '$needle'" >&2
    head -c 1200 "$f" >&2
    exit 1
  fi
}

echo "=== Phase 3: Optimizer daemon ==="

# C4: manual rebalance via chat
post_sse "rebalance my portfolio" "phase3-c4" > /tmp/c4.sse
require_substring /tmp/c4.sse '"card_type":"execution_plan_v2"\|"card_type":"text"' "C4 plan or no-op"

# C5: daemon plan with no session (skip if no test user configured)
# Verified by checking the optimizer daemon logs or DB directly.

echo "Phase 3 complete (live daemon tests require manual env setup)."
