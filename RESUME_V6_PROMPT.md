# AUTONOMOUS RESUME V6 — IlyonAi SPEC + DEVPLAN 100% COMPLETION

Continuation of /loop autonomous build. V5 shipped 21 commits (`9c0bd17` →
`9dd5c35`). 8 financial-loss bug class catches via Pass 2 hand-read.

## STATE AT HANDOFF

- Repo: `/home/griffiniskid/Documents/ai-sentinel` branch `main` = staging
- HEAD: `9dd5c35` (will be higher if more shipped before compaction)
- Spec PDF: `IlyonAi_LP_Execution_Spec.pdf` v1.0 40 pages
- Dev plan: `IlyonAi_Development_Plan.md` 1491 lines
- Coverage ledger: `docs/SPEC_COVERAGE.md` — v5 section appended
- Pass 1 inventory: `docs/V4_MATRIX_PASS1_SUMMARY.md` + `_INVENTORY.md`
- Pass 2 state: 120/120 captured (with mid-stream redeploy cascade kills),
  20-30 zero-byte chains, 65-70 ready chains, 10-15 blocked (mostly
  v4_gaps allowlist)
- v4_gaps allowlist: `tests/harness/v4_gaps.py` documents HONEST-RECOVERY
  chains expected to BLOCK with typed recovery (V5 acceptable)
- Live log: `/tmp/v3-deep/_log.md` (recreate on session restart — /tmp wiped)
- Curl helper: `/tmp/v3-deep/_curl.sh` (recreate on session restart)
- Memory dir: `~/.claude/projects/-home-griffiniskid-Documents-ai-sentinel/memory/`
  Read order: `resume_2026-05-16_v5_continuation.md`,
  `resume_2026-05-16_v4_continuation.md`, `feedback_no_stopping_between_items.md`,
  `feedback_validation_no_mechanical.md`, `MEMORY.md`
- Prod `ilyonai.com` = **NO-EXEC. Never deploy. Never touch.**
- Staging: `aisentinel@173.249.5.167:~/ai-sentinel-staging`
  Key: `~/.ssh/opencode_ai_sentinel_vps_ed25519`
- Test wallets: `0xaaaa...` MetaMask, `5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L` Phantom

## RESTORE LOST STATE (after session restart)

```bash
mkdir -p /tmp/v3-deep/v4
test -f /tmp/v3-deep/_log.md || echo "RESUME-V6 $(date -Iseconds)" > /tmp/v3-deep/_log.md
cat > /tmp/v3-deep/_curl.sh <<'EOF'
#!/bin/bash
set -e
OUT="$1"; MSG="$2"; SID="${3:-resume-$(date +%s)-$RANDOM}"
EVM="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SOL="5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L"
curl -sS -N -m 90 -X POST 'https://staging.ilyonai.com/api/v1/agent' \
  -H 'Content-Type: application/json' \
  -d "$(jq -nc --arg m "$MSG" --arg sid "$SID" --arg evm "$EVM" --arg sol "$SOL" \
        '{message:$m, session_id:$sid, evm_wallet:$evm, solana_wallet:$sol}')" \
  > "$OUT" 2>&1
echo "WROTE: $OUT ($(wc -c <"$OUT") bytes)"
EOF
chmod +x /tmp/v3-deep/_curl.sh
```

## HARD RULES (V5 carried forward)

1. NO MECHANICAL ANALYZER. Every blocker = real curl → cat SSE →
   human-read every byte → plain-words prose verdict → fix at root.
2. NO MID-STREAM REDEPLOYS during Pass — cascade kills captures. Batch
   ALL commits then ONE redeploy then NEW Pass.
3. NEVER force-push main. NEVER skip hooks. NEVER bypass signing.
4. NEVER guess on-chain addresses. Verify via official docs/explorer.

## WHAT V5 SHIPPED (sealed; do not redo)

21 commits closing 8 financial-loss bug class catches:

1. Pure-refine messages must not hijack prior top defi_opp item (A09)
2. Aave V3 chain-word captured as asset (H13/G05) — BASE→base+USDC
3. Lifecycle proto strip trailing receipt/asset words (D07) —
   yearn-usdc-vault → yearn
4. Per-protocol canonical-chain default for lifecycle (D04) — PCS V2 → bsc
5. Balancer native gas-token alias (C07) — ETH ↔ WETH pool lookup + leg
6. Bridge-action lazy_resume refusal (E01/E02) — composed_plan owns bridge
7. _LP_PROTO_FIRST_RE for §7 S1/S2/S3 protocol-first forms (H01/H02/H03/C12)
8. Lazy_resume accepts amount override 'Confirm 50' (G05)

Plus: anaphora 'there' (A03), lifecycle bare-amount + digit-pool (D04/05/06),
refine inherits product_types (A07/A19/A20), continuation-modifier asset_in
(A01), lazy_proto_asset bare-amount fallback (A07/A09), carve-out
bare-digit (A11/A19/A20), v4_gaps.py allowlist (deferred specs).

## REMAINING WORK (Phase B / C / D / E / F)

**Phase B Solana hand-rolled programs** (1-2 days):
- B.1 JLP via Jupiter Perps `PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu`
  add_liquidity IX — install anchor IDL + hand-roll
- B.2 Sanctum INF via S-Controller `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx`
- B.3 Raydium AMM v4 + CPMM via @raydium-io/raydium-sdk-v2
- B.4 Meteora DAMM v2 + Dynamic Vaults via @meteora-ag SDKs

**Phase C Solana lifecycle close** (1 day):
- C.1 Orca Whirlpool decreaseLiquidity + collect + close (whirlpools-sdk)
- C.2 Raydium CLMM close_position
- C.3 Meteora DLMM removeLiquidityByRange
- C.4 Kamino Lend withdraw (klend-sdk)
- C.5 JLP withdraw (1h lockup)
- C.6 Marinade orderUnstake variant

**Phase D on-chain session-key enforcement** (3-4h, browser-blocked):
- D.1 Wire Eip7702OptInPanel to broadcast Nexus installModule calldata
- D.2 SessionKeyPanel.revoke broadcasts uninstallModule
- D.3 Solana session signer via Phantom embedded keypair
- D.4 Verify auto-rebalance flow under session signer

**Phase E remaining** (1-2 days):
- E.1 §7 S2/S4/S5/S7/S8/S10/S11/S12/S14 funding scenarios
- E.2 §13 Row 15 hardware-wallet ALT splitting
- E.3 V3_FACTORIES Berachain Kodiak + Sonic SwapX (need verified addresses)
- E.4 Pendle V2 real ApproxParams (needs Pendle Hosted SDK)
- E.5 V3 NFT pool_symbol auto-extract — already partial via H01
- E.6 ERC4626 vault registry expansion (verified addrs unavailable
  via public APIs — defer to V7 with explicit DefiLlama paid access)
- E.7 Token-2022 hook routing

**Phase F frontend** (1 day, browser-blocked):
- F.1 Cross-chain bridge progress bar visual
- F.2 V4 native mint Permit2 sign prompt
- F.3 Browser visual verification of all UI changes

## PHASE A — 3 CLEAN MATRIX SWEEPS

V5 prompt mandate: THREE consecutive clean passes through 120-chain
matrix. V6 task: complete Pass 3 + Pass 4 against current staging.

**Important workflow** (cascade-kill lesson):
1. Wait for current Pass to finish.
2. Identify chains never-ready (excluding v4_gaps allowlist).
3. Read by-hand each blocked SSE capture.
4. Batch ALL code fixes.
5. ONE push + ONE redeploy.
6. Refire only the blocked chains (use `--start-from`).
7. Hand-read refired captures.
8. Repeat until matrix gate.

## STARTING TASKS (priority order)

1. Read `tests/harness/v4_gaps.py` to know which chains are expected blocked.
2. Health-check staging: `curl -sS -X POST 'https://staging.ilyonai.com/api/v1/agent' \
     -H 'Content-Type: application/json' \
     -d '{"message":"hello","session_id":"v6-meta-healthcheck",
          "evm_wallet":"0xaaa...","solana_wallet":"5MgZ..."}' --max-time 15`
3. Refire all chains: `python -m tests.harness.v4_runner --all --force --delay 0.5`
4. After done: read every blocked chain by hand. Write prose verdict to
   `/tmp/v3-deep/_log.md`. Identify root causes. Batch fixes.
5. Push + redeploy + refire only blocked chains. Repeat.
6. After Pass 3 fully clean: Pass 4 confirmation.
7. After 3 consecutive clean: write final SPEC_COVERAGE update +
   final commit `spec(complete): all §1-§14 implemented + dev-plan phases 0-7 shipped`

## DO NOT STOP

Continue tool-calling cycle until 3-clean-pass gate met. Explicit user
STOP is only exit. After each commit IMMEDIATELY next tool call.
