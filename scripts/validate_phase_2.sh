#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Phase 2 Validation: Multi-Step Planner + Executor ==="

echo "[1/4] Running planner tests..."
PYTHONPATH="$(pwd)" pytest tests/agent/test_planner.py -v --tb=short

echo "[2/4] Running step executor tests..."
PYTHONPATH="$(pwd)" pytest tests/agent/test_step_executor.py -v --tb=short

echo "[3/4] Running step status card tests..."
cd web && npm test -- --run tests/e2e/step-status-card.test.tsx tests/e2e/use-execution-plan.test.ts tests/e2e/use-agent-stream-status.test.tsx

echo "[4/4] Running frontend type-check..."
npm run type-check

echo ""
echo "✅ Phase 2 validation passed"
