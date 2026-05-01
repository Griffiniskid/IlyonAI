#!/usr/bin/env bash
set -euo pipefail

# Default to origin/main if available (includes production fixes), else old checkpoint
DEFAULT_BASE="origin/main"
if ! git rev-parse --verify "$DEFAULT_BASE" >/dev/null 2>&1; then
  DEFAULT_BASE="bf1891e56808dc765c75e61ab0c904eae422c8d7"
fi
BASE_REF="${ASSISTANT_IMMUTABLE_BASE:-$DEFAULT_BASE}"
TARGET_DIR="IlyonAi-Wallet-assistant-main/"

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "ERROR: immutable base '$BASE_REF' does not exist" >&2
  exit 1
fi

changed="$(git diff --name-only "$BASE_REF" -- "$TARGET_DIR")"
if [ -n "$changed" ]; then
  echo "ERROR: wallet assistant files changed since $BASE_REF" >&2
  printf '%s\n' "$changed" >&2
  exit 1
fi

echo "OK: wallet assistant is unchanged since $BASE_REF"
