#!/usr/bin/env bash
set -euo pipefail

BASE="${SENTINEL_API_TARGET:-http://localhost:8080}"
PROXY="${PROXY_URL:-http://localhost:3000}"
TOKEN="${SENTINEL_TEST_TOKEN:-}"

post_sse() {
  local prompt="$1" session="$2"
  curl -fsS -N -X POST "${PROXY}/api/v1/agent" \
    -H "content-type: application/json" \
    ${TOKEN:+-H "authorization: Bearer ${TOKEN}"} \
    -d "{\"message\":${prompt@Q},\"session_id\":${session@Q}}" \
    --max-time 60
}

require_event() {
  local stream="$1" event="$2" label="$3"
  if ! grep -q "event: ${event}" "$stream"; then
    echo "FAIL ${label}: missing event=${event}" >&2
    head -c 800 "$stream" >&2
    exit 1
  fi
}

require_substring() {
  local stream="$1" needle="$2" label="$3"
  if ! grep -q "$needle" "$stream"; then
    echo "FAIL ${label}: missing substring '${needle}'" >&2
    head -c 800 "$stream" >&2
    exit 1
  fi
}

echo "=== Phase 1: Universal Sentinel scoring ==="

# A1
post_sse "allocate \$10k USDC" "phase1-a1" > /tmp/a1.sse
require_event /tmp/a1.sse card "A1 card frame"
require_substring /tmp/a1.sse '"card_type":"allocation"' "A1 allocation card"
require_substring /tmp/a1.sse '"card_type":"sentinel_matrix"' "A1 sentinel_matrix"
require_substring /tmp/a1.sse '"card_type":"execution_plan"' "A1 execution_plan"

# A2
post_sse "highest APR for USDC on Polygon" "phase1-a2" > /tmp/a2.sse
require_substring /tmp/a2.sse '"sentinel"' "A2 sentinel sidecar"
require_substring /tmp/a2.sse '"risk_level"' "A2 risk_level"

# A3
post_sse "where can I stake BNB" "phase1-a3" > /tmp/a3.sse
require_substring /tmp/a3.sse '"sentinel"' "A3 sentinel sidecar"
require_substring /tmp/a3.sse '"shield"' "A3 shield sidecar"

# A4 (skipped if no wallet) — test stub
post_sse "what's my balance" "phase1-a4" > /tmp/a4.sse
require_event /tmp/a4.sse done "A4 done"

# A5
post_sse "explain your scoring methodology" "phase1-a5" > /tmp/a5.sse
require_substring /tmp/a5.sse "Safety" "A5 safety word"
require_substring /tmp/a5.sse "Durability" "A5 durability word"
require_substring /tmp/a5.sse "0.40" "A5 weight 0.40"

# A6
post_sse "swap 1 ETH to USDC" "phase1-a6" > /tmp/a6.sse
require_substring /tmp/a6.sse '"card_type":"swap_quote"' "A6 swap quote"
require_substring /tmp/a6.sse '"shield"' "A6 shield"

# A7
post_sse "swap 1 ETH to RANDOMSCAMTOKEN" "phase1-a7" > /tmp/a7.sse
require_substring /tmp/a7.sse '"shield"' "A7 shield present"

# A8
post_sse "bridge 100 USDC to Arbitrum" "phase1-a8" > /tmp/a8.sse
require_substring /tmp/a8.sse '"card_type":"bridge"' "A8 bridge card"
require_substring /tmp/a8.sse '"shield"' "A8 shield"

# A9 / A10: chip presets
post_sse "low-risk only" "phase1-a9" > /tmp/a9.sse
require_substring /tmp/a9.sse "Sentinel" "A9 mentions Sentinel"
post_sse "maximize APY" "phase1-a10" > /tmp/a10.sse
require_event /tmp/a10.sse card "A10 card emitted"

# A11: persisted slippage cap (requires authenticated user; skipped without TOKEN)
if [ -n "$TOKEN" ]; then
  post_sse "set my slippage cap to 30 bps" "phase1-a11" > /tmp/a11.sse
  require_substring /tmp/a11.sse '"card_type":"preferences"' "A11 preferences card"
fi

# A12: preferred chains
if [ -n "$TOKEN" ]; then
  post_sse "set my preferred chains to Arbitrum and Base" "phase1-a12" > /tmp/a12.sse
  require_substring /tmp/a12.sse '"card_type":"preferences"' "A12 preferences card"
fi

bash scripts/check_assistant_immutable.sh
echo "=== Phase 1: PASS ==="
