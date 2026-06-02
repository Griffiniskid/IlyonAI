#!/usr/bin/env bash
# Thin wrapper: deploy origin/main to PRODUCTION (ilyonai.com — live funds box).
# Requires --confirm. Backs up + refuses to overwrite prod-only commits.
#   bash scripts/deploy-prod.sh --confirm
exec "$(cd "$(dirname "$0")" && pwd)/deploy.sh" prod "$@"
