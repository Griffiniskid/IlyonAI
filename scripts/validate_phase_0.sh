#!/usr/bin/env bash
set -euo pipefail

echo "=== Phase 0: Foundations ==="

echo "Z1: Sentinel agent-health endpoint"
curl -fsS "http://localhost:8080/api/v1/agent-health" | tee /tmp/z1.json
grep -q '"feature_agent_v2": *true' /tmp/z1.json || { echo "Z1 FAIL"; exit 1; }
echo

echo "Z2: AGENT_BACKEND=wallet routes to wallet assistant"
AGENT_BACKEND=wallet curl -fsS -X POST "http://localhost:3000/api/v1/agent" \
  -H "content-type: application/json" \
  -d '{"message":"hi","session_id":"phase0-z2"}' | head -c 500 > /tmp/z2.txt
grep -q "session_id" /tmp/z2.txt || { echo "Z2 FAIL"; exit 1; }
echo

echo "Z3: AGENT_BACKEND=sentinel routes to sentinel SSE"
AGENT_BACKEND=sentinel curl -fsS -N -X POST "http://localhost:3000/api/v1/agent" \
  -H "content-type: application/json" \
  -d '{"message":"hi","session_id":"phase0-z3"}' \
  | head -c 1500 > /tmp/z3.sse
grep -q "event: thought" /tmp/z3.sse || { echo "Z3 FAIL — no SSE thought frame"; exit 1; }
grep -q "event: done" /tmp/z3.sse || { echo "Z3 FAIL — no SSE done frame"; exit 1; }
echo

echo "Z4: Immutable guard"
bash scripts/check_assistant_immutable.sh

echo "=== Phase 0: PASS ==="
