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

echo "=== Phase 2: Multi-step planner ==="

# B1
post_sse "bridge 1000 USDC from Ethereum to Arbitrum and stake it on Aave" "phase2-b1" > /tmp/b1.sse
require_substring /tmp/b1.sse '"card_type":"execution_plan_v2"' "B1 plan card"
require_substring /tmp/b1.sse '"action":"approve"' "B1 approve injection"
require_substring /tmp/b1.sse '"action":"wait_receipt"' "B1 wait_receipt injection"
require_substring /tmp/b1.sse '"action":"stake"' "B1 stake step"
require_substring /tmp/b1.sse '"risk_gate":"soft_warn"' "B1 soft_warn"

# B2
post_sse "swap 0.5 ETH to USDC then provide liquidity to USDC/USDT on Curve" "phase2-b2" > /tmp/b2.sse
require_substring /tmp/b2.sse '"card_type":"execution_plan_v2"' "B2 plan"
require_substring /tmp/b2.sse '"action":"deposit_lp"' "B2 deposit_lp"

# B5: double-confirm gate
post_sse "stake 50 ETH on Lido" "phase2-b5" > /tmp/b5.sse
require_substring /tmp/b5.sse '"requires_double_confirm":true' "B5 double-confirm"

# B6: hard-block
post_sse "swap 1 ETH to 0x000000000000000000000000000000000000dEaD" "phase2-b6" > /tmp/b6.sse
require_substring /tmp/b6.sse '"plan_blocked"' "B6 plan_blocked event"

# B7: single-step transfer
post_sse "send 100 USDC to 0xabc1230000000000000000000000000000001234" "phase2-b7" > /tmp/b7.sse
require_substring /tmp/b7.sse '"card_type":"transfer"\|"card_type":"execution_plan_v2"' "B7 transfer"

# B8: idle balance resolves
post_sse "stake all my idle ETH on Lido" "phase2-b8" > /tmp/b8.sse
require_substring /tmp/b8.sse '"resolves_from"' "B8 resolves_from present"

# B10: 4-step chain (intentionally just under cap)
post_sse "swap 100 USDC to ETH, then bridge to Arbitrum, then stake on Aave, then deposit LP on Curve" "phase2-b10" > /tmp/b10.sse
require_substring /tmp/b10.sse '"card_type":"execution_plan_v2"' "B10 plan"

bash scripts/check_assistant_immutable.sh
echo "=== Phase 2: PASS ==="
