#!/usr/bin/env bash
#
# One-command deploy to staging or production. Run from the repo root on the
# operator machine (it SSHes to the VPS). Git-based: fetches origin/main on the
# target box, checks it out, rebuilds Docker, then auto-recovers the two failure
# modes we've actually hit (unlabeled-orphan container name conflict; web left
# in "Created" -> 502) and verifies the public URL + Sentinel end-to-end.
#
# Usage:
#   bash scripts/deploy.sh staging
#   bash scripts/deploy.sh prod --confirm
#   bash scripts/deploy.sh prod --confirm --ref origin/some-branch
#
# Safety:
#   * prod requires --confirm (live funds box).
#   * prod creates branch+tag backup/prod-<date> from current HEAD first and
#     ABORTS if prod has commits the target ref lacks (won't overwrite
#     production-only work). Override with --force only if you mean it.
#   * Secrets (.env, deploy/**/{app,compose,assistant}.env, *.db, web/.env.local)
#     are gitignored, so the checkout never touches them. postgres/redis are not
#     in any build, keep their data volumes.
#
# NOTE: a cold build (web npm ci + next build) can take ~50 min. If you invoke
# this from an agent harness, run it in the background and poll, or run it in a
# real terminal.
set -euo pipefail

ENVNAME="${1:-}"; shift || true
FLAG_CONFIRM=0; FLAG_FORCE=0; REF="origin/main"
while [ $# -gt 0 ]; do
  case "$1" in
    --confirm) FLAG_CONFIRM=1 ;;
    --force)   FLAG_FORCE=1 ;;
    --ref)     REF="${2:?--ref needs a value}"; shift ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
  shift
done

case "$ENVNAME" in
  staging)
    HOST=ilyonai-staging; DIR=/home/aisentinel/ai-sentinel-staging; PROJECT=ilyonai-staging
    URL=https://staging.ilyonai.com; WEBPORT=13000; APIPORT=18080; IS_PROD=0 ;;
  prod)
    HOST=ilyonai;         DIR=/home/aisentinel/ai-sentinel;         PROJECT=ai-sentinel
    URL=https://ilyonai.com;        WEBPORT=3000;  APIPORT=8080;  IS_PROD=1 ;;
  *) echo "usage: bash scripts/deploy.sh <staging|prod> [--confirm] [--force] [--ref REF]"; exit 2 ;;
esac

SSH=(ssh -o ConnectTimeout=20 -o BatchMode=yes "$HOST")
TOKEN="262o7xFCzVWxxVZmjPCBMCKtunieXARcZoyGmrkvpump"   # known DANGEROUS Sentinel test mint
DATE="$(date +%Y-%m-%d)"
say(){ printf '\n=== %s ===\n' "$*"; }

if [ "$IS_PROD" = 1 ] && [ "$FLAG_CONFIRM" != 1 ]; then
  echo "PROD is the live funds box. Re-run with --confirm:"
  echo "  bash scripts/deploy.sh prod --confirm"
  exit 1
fi

say "deploy $ENVNAME  (host=$HOST dir=$DIR ref=$REF)"

# ── remote: backup (prod) -> reconcile guard -> checkout -> build -> recover ──
"${SSH[@]}" "DIR='$DIR' PROJECT='$PROJECT' REF='$REF' ENVNAME='$ENVNAME' DATE='$DATE' WEBPORT='$WEBPORT' IS_PROD='$IS_PROD' FORCE='$FLAG_FORCE' bash -s" <<'REMOTE'
set -uo pipefail
cd "$DIR" || { echo "FATAL: no $DIR"; exit 10; }

echo "current: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)"
git fetch origin --prune --tags --quiet
TGT=$(git rev-parse "$REF") || { echo "FATAL: ref $REF not found"; exit 11; }
echo "target:  $REF @ $(git rev-parse --short "$TGT")"

if [ "$IS_PROD" = 1 ]; then
  CUR=$(git rev-parse HEAD)
  git branch "backup/prod-$DATE" "$CUR" 2>/dev/null || true
  git tag    "backup/prod-$DATE" "$CUR" 2>/dev/null || true
  B=$(git rev-parse --short "refs/heads/backup/prod-$DATE" 2>/dev/null || echo MISSING)
  T=$(git rev-parse --short "refs/tags/backup/prod-$DATE" 2>/dev/null || echo MISSING)
  echo "backup branch=$B tag=$T  (rollback target = current HEAD $(git rev-parse --short "$CUR"))"
  [ "$B" = MISSING ] || [ "$T" = MISSING ] && { echo "FATAL: backup ref missing — abort"; exit 12; }
  AHEAD=$(git rev-list --count "$REF..$CUR")
  if [ "$AHEAD" -gt 0 ] && [ "$FORCE" != 1 ]; then
    echo "ABORT: prod HEAD has $AHEAD commit(s) NOT in $REF — deploying would overwrite production-only work:"
    git log --oneline "$REF..$CUR" | head -20
    echo "Investigate (merge/cherry-pick) or re-run with --force if you really mean to overwrite."
    exit 13
  fi
fi

echo "--- checkout $REF ---"
if [ "$IS_PROD" = 1 ]; then
  git checkout -B main "$REF"            # prod is the main worktree
else
  git checkout -f --detach "$REF"        # staging is a linked worktree: detach to avoid branch conflict
fi
echo "now at: $(git rev-parse --short HEAD)  ($(git log -1 --format=%s | cut -c1-60))"

echo "--- docker compose up -d --build ---"
set +e
docker compose up -d --build 2>&1 | tail -20
RC=${PIPESTATUS[0]}
set -e
echo "compose rc=$RC"

echo "--- recover: drop any UNLABELED orphan squatting a service name (name-conflict fix) ---"
for svc in api web assistant-api solana-yield-builder; do
  name="${PROJECT}-${svc}-1"
  cid=$(docker ps -aq -f "name=^/${name}$" 2>/dev/null)
  if [ -n "$cid" ]; then
    proj=$(docker inspect "$cid" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null)
    mounts=$(docker inspect "$cid" --format '{{len .Mounts}}' 2>/dev/null)
    if [ -z "$proj" ] && [ "${mounts:-0}" = 0 ]; then
      echo "  removing unlabeled stateless orphan $name ($cid)"
      docker rm -f "$cid" >/dev/null || true
    fi
  fi
done

echo "--- start any Created / finish recreate ---"
docker compose up -d 2>&1 | tail -10

echo "--- wait for web :$WEBPORT ---"
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:${WEBPORT}/" 2>/dev/null || true)
  echo "  try $i: :$WEBPORT -> ${code:-noconn}"; [ "$code" = 200 ] && break; sleep 3
done

echo "--- final ps ---"
docker compose ps --format "table {{.Service}}\t{{.Status}}"
echo "box web  -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://localhost:${WEBPORT}/ 2>/dev/null || echo ERR)"
REMOTE
RC=$?
[ "$RC" -ne 0 ] && { echo "REMOTE step failed (rc=$RC) — nothing deployed past the guard. See output above."; exit "$RC"; }

# ── external verification (public URL + Sentinel) ──
say "verify $URL"
HOME_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$URL/" || echo ERR)
echo "homepage -> $HOME_CODE"
echo "Sentinel analysis:"
curl -sN --max-time 90 -X POST "$URL/api/v1/agent" \
  -H 'Content-Type: application/json' \
  -d "{\"message\":\"$TOKEN\",\"session_id\":\"deploy-verify-$DATE\"}" 2>/dev/null \
  | grep -aoiE 'analyze_token_full_sentinel|grade|DANGEROUS|No deterministic|agent_v2_disabled|Bad Gateway' | sort | uniq -c || true

OK=1
[ "$HOME_CODE" = 200 ] || OK=0
if [ "$OK" = 1 ]; then say "DEPLOY OK ($ENVNAME) — $URL returns 200"; else say "VERIFY FAILED — homepage=$HOME_CODE (investigate)"; fi

if [ "$IS_PROD" = 1 ]; then
  say "rollback (if needed)"
  echo "  ssh $HOST 'cd $DIR && git reset --hard refs/tags/backup/prod-$DATE && docker compose up -d --build'"
fi
exit $(( OK == 1 ? 0 : 1 ))
