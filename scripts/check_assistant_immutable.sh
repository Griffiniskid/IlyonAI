#!/usr/bin/env bash
set -euo pipefail

BASE_TAG="${ASSISTANT_IMMUTABLE_BASE:-checkpoint/pre-scoring-merge-brainstorm-20260429-133016}"
BASE_REF="refs/tags/$BASE_TAG"
TARGET_DIR="IlyonAi-Wallet-assistant-main/"

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "ERROR: immutable base '$BASE_TAG' does not exist" >&2
  exit 1
fi

changed="$(git diff --name-only "$BASE_REF" -- "$TARGET_DIR")"
if [ -n "$changed" ]; then
  echo "ERROR: wallet assistant files changed since $BASE_TAG" >&2
  printf '%s\n' "$changed" >&2
  exit 1
fi

echo "OK: wallet assistant is unchanged since $BASE_TAG"
