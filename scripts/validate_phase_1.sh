#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Phase 1 Validation: Universal Sentinel Scoring + Routing Guard ==="

echo "[1/5] Checking wallet assistant immutability..."
bash scripts/check_assistant_immutable.sh

echo "[2/5] Running scoring tests..."
PYTHONPATH="$(pwd)" pytest tests/scoring/ -v --tb=short

echo "[3/5] Running sentinel wrap tests..."
PYTHONPATH="$(pwd)" pytest tests/agent/test_sentinel_wrap.py -v --tb=short

echo "[4/5] Running frontend type-check..."
cd web && npm run type-check

echo "[5/5] Running frontend unit tests..."
npm test -- --run tests/e2e/execution-plan-v2.test.tsx tests/api/assistant-route-proxy.test.ts

echo ""
echo "✅ Phase 1 validation passed"
