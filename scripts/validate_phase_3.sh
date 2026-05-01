#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Phase 3 Validation: Cross-Chain Yield Optimizer ==="

echo "[1/3] Running optimizer delta tests..."
PYTHONPATH="$(pwd)" pytest tests/optimizer/test_delta_hysteresis.py -v --tb=short

echo "[2/3] Running optimizer snapshot tests (if present)..."
if [ -f tests/optimizer/test_snapshot.py ]; then
  PYTHONPATH="$(pwd)" pytest tests/optimizer/test_snapshot.py -v --tb=short
else
  echo "  (skipped - no test_snapshot.py yet)"
fi

echo "[3/3] Running optimizer daemon tests (if present)..."
if [ -f tests/optimizer/test_daemon.py ]; then
  PYTHONPATH="$(pwd)" pytest tests/optimizer/test_daemon.py -v --tb=short
else
  echo "  (skipped - no test_daemon.py yet)"
fi

echo ""
echo "✅ Phase 3 validation passed"
