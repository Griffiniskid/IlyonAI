#!/usr/bin/env bash
# Thin wrapper: deploy origin/main to STAGING (staging.ilyonai.com).
#   bash scripts/deploy-staging.sh            # deploy origin/main
#   bash scripts/deploy-staging.sh --ref origin/feature-x
exec "$(cd "$(dirname "$0")" && pwd)/deploy.sh" staging "$@"
