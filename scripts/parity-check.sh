#!/usr/bin/env bash
#
# Local vs Production parity check. Catches the class of bug where the CODE is
# identical but ENV/CONFIG differs (e.g. AGENT_BACKEND=sentinel on prod made all
# swaps fail while local=hybrid worked). Run after every deploy.
#
#   bash scripts/parity-check.sh
#
# Two checks:
#   1) ENV PARITY  — hashes behaviour-driving env vars in each running tier
#      (web / api / assistant) on local + prod and flags any MUST-MATCH key that
#      differs. Per-env keys (URLs, ports, DB, Redis, secrets) are allow-listed.
#   2) BEHAVIOUR PARITY — fires the same requests at BOTH through the WEB path
#      (the user's real path, not the api directly) and diffs the outcomes.
#
# Exit non-zero if any parity check fails.
set -uo pipefail

PROD_HOST="${PROD_HOST:-ilyonai}"
PROD_DIR="${PROD_DIR:-/home/aisentinel/ai-sentinel}"
LOCAL_WEB="${LOCAL_WEB:-http://localhost:3000}"
PROD_WEB="${PROD_WEB:-https://ilyonai.com}"
SSH=(ssh -o ConnectTimeout=15 -o BatchMode=yes "$PROD_HOST")
FAIL=0
say(){ printf '\n=== %s ===\n' "$*"; }

# Behaviour-driving keys that MUST be identical across local & prod (per tier).
# (Anything NOT listed here is treated as per-env and ignored — URLs, ports,
#  DB/Redis, secrets, NODE_ENV, model *keys* that are intentionally per-account.)
MUST_MATCH_WEB="AGENT_BACKEND"
MUST_MATCH_API="AI_MODEL AI_PROVIDER OPENAI_MODEL OPENAI_MINI_MODEL GROK_MODEL FEATURE_AGENT_V2 FEATURE_DEFI FEATURE_SENTINEL CACHE_TTL JUPITER_API_BASE"
# NB: AGENT_BACKEND is a WEB-only routing var (route.ts); the assistant never
# reads it, so it's intentionally absent on prod's assistant — do not flag it.
MUST_MATCH_ASSIST="CACHE_TTL"

hash_env_local(){ # $1=key  (local reads repo .env for api/assistant, web/.env.local for web)
  local file=".env"; [ "$2" = web ] && file="web/.env.local"
  local v; v=$(grep -m1 -E "^$1=" "$file" 2>/dev/null | cut -d= -f2-)
  printf '%s' "$v" | shasum -a 256 | cut -c1-12
}
hash_env_prod(){ # $1=key $2=svc  (prod reads the container runtime env)
  "${SSH[@]}" "cd $PROD_DIR && docker compose exec -T $2 printenv $1 2>/dev/null" 2>/dev/null | tr -d '\r\n' | shasum -a 256 | cut -c1-12
}

check_tier(){ # $1=svc $2=keys
  say "ENV parity: $1"
  for k in $2; do
    local lh ph; lh=$(hash_env_local "$k" "$1"); ph=$(hash_env_prod "$k" "$1")
    if [ "$lh" = "$ph" ]; then printf '  ok      %s\n' "$k"
    else printf '  DIFFER  %s   local=%s prod=%s\n' "$k" "$lh" "$ph"; FAIL=1; fi
  done
}
check_tier web "$MUST_MATCH_WEB"
check_tier api "$MUST_MATCH_API"
check_tier assistant-api "$MUST_MATCH_ASSIST"

# ── Behaviour probes through the WEB path (route.ts), same body on both ──
W="7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"   # test Solana wallet
probe(){ # $1=label $2=body  → prints a compact outcome signature
  local out
  out=$(curl -sN --max-time 90 -X POST "$3/api/v1/agent" -H 'Content-Type: application/json' -d "$2" 2>/dev/null \
        | grep -aoiE 'analyze_token_full_sentinel|sentinel_token_report|solana_swap_proposal|swapTransaction|No deterministic|not recognized|agent_v2_disabled' \
        | sort -u | tr '\n' ',')
  printf '%s' "${out:-<empty>}"
}
behaviour(){ # $1=label $2=body
  say "BEHAVIOUR parity: $1"
  local l p; l=$(probe "$1" "$2" "$LOCAL_WEB"); p=$(probe "$1" "$2" "$PROD_WEB")
  printf '  local: %s\n  prod : %s\n' "$l" "$p"
  if [ "$l" = "$p" ]; then printf '  ok (same outcome)\n'; else printf '  DIFFER <<<\n'; FAIL=1; fi
}
behaviour "analyze bare token" "{\"message\":\"262o7xFCzVWxxVZmjPCBMCKtunieXARcZoyGmrkvpump\",\"session_id\":\"par-an-$RANDOM\"}"
behaviour "swap SOL->USDC"      "{\"query\":\"swap 0.2 SOL to USDC\",\"user_address\":\"$W\",\"chain_id\":101,\"session_id\":\"par-sw-$RANDOM\"}"

say "RESULT"
if [ "$FAIL" = 0 ]; then echo "PARITY OK — local and prod match on all checked params + behaviours."; else echo "PARITY FAILED — see DIFFER lines above. Fix the mismatched env on prod and re-run."; fi
exit "$FAIL"
