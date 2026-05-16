# AUTONOMOUS RESUME V5 — IlyonAi SPEC + DEVPLAN 100% COMPLETION

You are resuming an autonomous build that has been running for 10+ hours
across multiple sessions. The compaction that just happened wiped
`/tmp/v3-deep/v4/` and killed every bg matrix runner. Git history
survived. Memory files survived. Staging deployment survived at HEAD
`2fc7d86`.

**This is a continuation, not a restart.** Do not redo work that is
already in git. Do not re-design the matrix. Do not re-write detectors
that already exist. Read the state first, then close the remaining gaps.

You will not stop until every condition in COMPLETION CRITERIA holds.
Not a single stop allowed before then. Explicit user-typed STOP is the
only acceptable exit.

---

## ENVIRONMENT

- Repo: `/home/griffiniskid/Documents/ai-sentinel` (branch `main` = staging)
- HEAD at compaction: `2fc7d86` (27 v4 commits already shipped from `5806836` baseline)
- Spec PDF: `IlyonAi_LP_Execution_Spec.pdf` (40 pages, v1.0 · 2026-05-14)
- Dev plan: `IlyonAi_Development_Plan.md` (1491 lines)
- Coverage ledger: `docs/SPEC_COVERAGE.md` (read FIRST — has resume v1/v2/v3/v4 state through commit 6731c35)
- Pass 1 results: `docs/V4_MATRIX_PASS1_SUMMARY.md` + `docs/V4_MATRIX_PASS1_INVENTORY.md`
- Live log: `/tmp/v3-deep/_log.md` — RESTORE this path; mkdir if gone after compaction
- Curl helper: `/tmp/v3-deep/_curl.sh "<out>" "<msg>" "<sid>"` — recreate if gone (see below)
- Memory in: `~/.claude/projects/-home-griffiniskid-Documents-ai-sentinel/memory/`
  Read in this order:
    1. `resume_2026-05-16_v4_continuation.md` (27-commit state, Pass 1 results, what's pending)
    2. `resume_2026-05-15_v3_continuation.md`
    3. `resume_2026-05-15_v2_continuation.md`
    4. `feedback_no_stopping_between_items.md` (HARD RULE — never stop between items)
    5. `feedback_validation_no_mechanical.md` (HARD RULE — real curl + by-hand SSE)
    6. `MEMORY.md` (index)
- Prod `ilyonai.com` = **NO-EXEC. Never deploy. Never touch.**
- Staging: `aisentinel@173.249.5.167:~/ai-sentinel-staging`
  Key: `~/.ssh/opencode_ai_sentinel_vps_ed25519`
  Deploy:
  ```
  git push origin main:staging && \
  ssh -i ~/.ssh/opencode_ai_sentinel_vps_ed25519 -o StrictHostKeyChecking=no aisentinel@173.249.5.167 \
    'cd ~/ai-sentinel-staging && git pull --ff-only origin staging && docker compose up -d --build api'
  ```
- Test wallets:
  - Phantom (Solana): `5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L`
  - MetaMask (EVM): `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`

---

## RESTORE LOST STATE (do this first, ONLY if missing)

```bash
mkdir -p /tmp/v3-deep
test -f /tmp/v3-deep/_log.md || echo "RESUME-V5 $(date -Iseconds)" > /tmp/v3-deep/_log.md
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
mkdir -p /tmp/v3-deep/v4
```

---

## HARD VALIDATION RULES (BREAK = REWORK)

1. **NO MECHANICAL ANALYZER.** No PASS/FAIL/✓/✗ summary script. Every
   scenario = real curl → `cat` full SSE → human-read every byte →
   plain-words prose verdict → fix at root → push main+main:staging →
   SSH redeploy → re-curl → re-read. If you cannot describe each
   event/card/field in prose, you have NOT read it.

2. **EVERY scenario logged** to `/tmp/v3-deep/_log.md`. One paragraph per
   scenario. Path to SSE capture next to verdict. No "looks fine" without
   quote.

3. **NEVER write end-of-cycle text.** After every commit → IMMEDIATELY run
   the next tool call. After test passes → IMMEDIATELY edit next file.
   After curl → IMMEDIATELY read SSE + fix or move next. Only acceptable
   stop = explicit user STOP or true 100% completion (all COMPLETION
   CRITERIA met).

4. **Forbidden between items:** "X commits shipped", "X tests pass", "next
   step is", "moving to", "now", "continuing with", "shipped", "done",
   "complete", "status:", "summary:", "let me know", "should work", "likely
   fixes", "this addresses", "deferred", "phase X handles", "acceptable for
   now", "good enough", "I'll continue". Catch self writing those → delete.

5. **NEVER force-push main.** NEVER skip hooks (`--no-verify`). NEVER bypass
   signing. NEVER commit secrets. NEVER deploy to prod.

6. **NEVER use mocked or guessed on-chain addresses** when shipping
   adapter/encoder code that will sign real transactions. Verify each
   address against on-chain explorer or official protocol docs before
   committing. Wrong addresses = financial loss for tester.

---

## WHAT'S ALREADY SHIPPED (sealed at HEAD `2fc7d86`; DO NOT REDO)

LIVE on staging (verified by-hand SSE read across resume v1/v2/v3/v4):

- F.3 Aave V3 native ETH full lifecycle via WTG3 — supply `0x474cf53d`,
  withdraw `0x80500d20`, repay `0x02c5fcf8`
- **F.5 Aave V3 native ETH borrow via WTG3.borrowETH `0x66514c97`**
  (resume v4) + variableDebtWETH.approveDelegation `0xc04a8a10`
  prerequisite + variableDebtWETH per-chain registry (eth/poly/arb/opt/base)
- F.5 LST/LRT direct-mint LIVE for 7 protocols: Lido (`0xa1903eab`) /
  Rocket Pool (`0xa3e0464d`) / ether.fi (`0xd5c08a72`) / Renzo (`0xfdaf83a3`) /
  Swell (`0xf340fa01`) / Frax (`0x4dcd4547`) / Mantle (`0xf6326fb3`)
- **Kelp ETH auto-wrap** (resume v4) — WETH.deposit() `0xd0e30db0` prepend
  when asset_in=ETH but protocol mint requires ERC20
- F.6 V2 LP withdraw (`0xbaa2abde`) — PCS V2 BNB-USDT BSC LIVE
- F.7 Balancer exit_pool (`0x8bdb3913`) — wsteth-weth Ethereum LIVE
- F.4 Pendle V2 per-mode dispatch + `PENDING_EPOCH_ENTRY` +
  `NEEDS_FRONTEND_SDK` (real ApproxParams encoders STILL pending)
- F.8 §6f recovery wired into multiple blocker sites
- F.9 `ReceiptWatcher.verify_step_receipt` + 30-entry `(protocol, action)` →
  ReceiptKind map
- F.10 §11 D.7 explicit >50bps drift gate, wired into `mark_step_status`
- C.2 `ComposedPlanOrchestrator` (async task pool + singleton + runtime
  notifier wire in `main.py` `on_startup`)
- C.3 LI.FI + Socket Bridge fallbacks (`composed_plan.Bridge` contract)
- §6c cross-chain composed plan LIVE: ETH→Base/Arbitrum/Polygon
  USDC/USDT/DAI → Aave V3 / Compound V3
- `pending_plans` registry + webhook→`resolve_fill` handoff +
  `rekey(old, new)` + `POST /api/v1/plans/{plan_id}/bridge-confirmed`
- **D.1 deBridge DLN orderId extractor** (resume v4) —
  `src/agent/debridge_order_extractor.py` + ReceiptWatcher hook
- D.5 `web/types/agent.ts` types
- D.6 frontend panels: `SessionKeyPanel` + `AuditLogPanel` +
  `Eip7702OptInPanel` + `Permit2SigButton`
- E.1 `src/auth/biconomy_nexus.py` — Nexus impl + **session-key
  installModule (`0x9517e29f`) + uninstallModule (`0xa71763a8`) calldata
  builders** (resume v4)
- E.2 `src/auth/zerodev_kernel.py` — Kernel v3 sibling
- E.4 alembic `agent_009` `biconomy_session_authorizations`
- E.5 `POST /api/v1/eip7702/prepare` + `/authorize` + `GET /{wallet}`
  (NOTE: path is `/api/v1/eip7702/`, NOT `/api/v1/auth/eip7702/`)
- `POST /api/v1/plans/{plan_id}/steps/{step_id}/permit2`
- `POST /api/v1/plans/{plan_id}/bridge-confirmed`
- `GET /api/v1/audit/{wallet}`
- **G.1/G.3 Permit2SigButton wired into ExecutionPlanV3Card** (resume v4)
  — renders when `step.transaction.permit_payload` present
- **G.2 `web/hooks/usePlanStream.ts`** (resume v4) — EventSource
  subscriber + ExecutionPlanV3Card flips `PENDING_DST_FILL` → ready on
  `bridge_resolution` event
- G.2 §12 PlanStatus canonical 12-status regression pin (6 tests)
- §13 26/27 edge-case rows implemented (only Row 15 ALT splitting pending)
- Phase 6 chain expansion 8→18 EVM + V3_FACTORIES 16/18 + LST registry 9
- Lifecycle intent: withdraw / redeem / claim / repay / borrow / exit /
  remove verbs + "all <TOKEN>" + pair-tail + "Exit PROTO PAIR with N TOKEN"
  forms
- **Lifecycle bare-chain extraction** (resume v4 `f9014a2`) — "Aave V3 Base"
  alone matches without "on Base"
- `_detect_cross_chain_then_yield` — "Bridge N TOKEN from SRC to DST then
  supply"
- `_TOKEN_ADDRS` xchain registry (DAI/USDT/USDC/WETH @ all major EVM chains)
- V2 pair registry — PCS BSC + Sushi/UniV2 Ethereum
- **`_detect_execute_named_proto`** (resume v4 `a305d07`) — "Execute on
  PROTO with N TOKEN" → build_yield_execution_plan
- **`_detect_lazy_resume_from_history`** (resume v4 `15a38a3` + expanded
  in `d128f61` / `8dd4d75` / `4256a24`) — vague final-confirm verbs
  rebuild from history; action-aware filter (Confirm withdraw picks
  withdraw plan, not supply plan)
- **`_detect_lazy_proto_asset_action`** (resume v4 `ea4f23a`) — "Execute
  PROTO ASSET supply" without amount inherits amount from history
- **`_ENSO_PROTOS_RE` expansion** (resume v4 `e65f3a5`) — Solana LSTs
  (Marinade/Jito/Sanctum/Blaze/Drift/JLP) + Aave/Compound (versioned) +
  Yearn v2/v3 + Morpho/Spark/Sky/Silo/Pendle + Uniswap/PancakeSwap/SushiSwap
- **Blue-chip filter** (resume v4 `bcbb0ee`) — "Only blue-chip protocols"
  → allowlist of 11 major audited protocols
- 6 critical financial-loss bug class fixes shipped in resume v4

55+ tests pass in agent+defi+auth narrow filter at HEAD `2fc7d86`.

Two pre-existing test failures (NOT v4 regressions, present on 5806836):
- `tests/agent/test_simple_runtime.py::test_run_ephemeral_turn_strips_llm_reasoning_leak_from_final_answer`
- `tests/agent/test_simple_runtime.py::test_detect_intent_keeps_highest_scoring_capital_request_as_allocation`

**Pass 1 final results** (post re-fire, 483 valid turn captures):
- 45/120 READY chains (38%)
- 13/120 BLOCKED with typed recovery
- 3 DEFI_OPPS / 1 POOL_LINK
- 58 NO_CARD (mostly intentional text-only info turns by chain design)

---

## START HERE (Sweep 0 — confirm + plan)

1. `mkdir -p /tmp/v3-deep/v4` and append `RESUME-V5 <iso-ts>` to
   `/tmp/v3-deep/_log.md` (recreate both if missing).
2. Read `docs/SPEC_COVERAGE.md` — full state ledger.
3. Read `docs/V4_MATRIX_PASS1_INVENTORY.md` — every chain's last-turn
   card/status/blocker.
4. Read memory files in order above.
5. `git log -1` confirms HEAD `2fc7d86`; `git status` confirms clean tree.
6. Health-check staging:
   `curl -sS -X POST 'https://staging.ilyonai.com/api/v1/agent' \
     -H 'Content-Type: application/json' \
     -d '{"message":"hello","session_id":"v5-meta","evm_wallet":"0xaaaa..."}' \
     --max-time 15 -w '\n[%{http_code} %{time_total}s]'`
   Expect 200.
7. Re-read spec PDF + dev plan, taking notes in
   `/tmp/v3-deep/_spec_notes_v5.md` highlighting any §1-§14 / Phase 0-7
   sub-items not yet ✅ in coverage ledger.
8. Begin **PHASE A** (multi-turn matrix Pass 2 — clean restart).

---

## PHASE A — MULTI-TURN MATRIX × 3 CLEAN PASSES (the actual gate)

This is the spec's mandatory validation gate. Pass 1 = 45/120 READY.
Pass 2 + Pass 3 each must complete with zero actionable issue.

`tests/harness/v4_matrix.py` already defines 120 chains. Do not redesign.
`tests/harness/v4_runner.py` already exists with `--all`, `--category`,
`--start-from`, `--force` flags.

### Pass 2 — fresh sweep at current HEAD

```bash
ssh redeploy if HEAD has new commits (always redeploy on Sweep 0)
mkdir -p /tmp/v3-deep/v4
python -m tests.harness.v4_runner --all --force --delay 0.5
```

Run sequentially. **Do not parallelize with multiple `--all` or
`--category` runs simultaneously** — last attempt cascaded staging
restarts and killed ~30 captures. Use `--start-from <chain_id>` to
resume after staging restart instead of starting another `--all`.

For each chain:
1. Read every turn's full SSE by hand.
2. Append prose verdict to `/tmp/v3-deep/_log.md` with capture path +
   what each event/card/field said.
3. If ANY mismatch (selector wrong, status blocked when ready expected,
   blocker code unexpected, asset/amount drifted, `exposure_disclosure`
   missing, recovery posture missing, sanitiser leak, `range_block`
   missing):
   a. Find the root in code (use `gitnexus_impact` before editing).
   b. Fix at root (not at the symptom).
   c. Push main + main:staging.
   d. SSH redeploy api.
   e. Re-curl from turn 1 (full chain — context resets).
   f. Repeat until the chain clears.
4. Mark chain complete with PASS verdict in `_log.md`.

Pass 2 passes only when every chain has a PASS verdict OR a documented
typed-recovery BLOCKED verdict (e.g. honest empty-wallet refusal).

### Pass 3 — second clean confirmation

After Pass 2 PASS, run the entire matrix again. Same fix-loop. Pass 3
passes only with zero actionable issue.

**Two clean consecutive passes is not enough. THREE consecutive clean
passes is the gate.** Run Pass 4 if Pass 3 ever surfaces an actionable
issue.

---

## PHASE B — Solana hand-rolled programs

These need careful program-IDL discovery from on-chain. Do not ship
guessed instruction layouts.

- **B.1 JLP native** via Jupiter Perps program
  `PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu` `add_liquidity` IX.
  Fetch anchor IDL via `findProgramAddress([buffer.from("anchor:idl")],
  programId)`. Hand-roll IX using `@solana/web3.js`. Single-token-in,
  basket-out at NAV. Surface 1h withdraw lockup.
  Validate: "Add 25 USDT to JLP".
- **B.2 Sanctum INF native** via S-Controller program
  `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx` `add_liquidity` IX.
  Drop Jupiter proxy.
  Validate: "Deposit 5 SOL into Sanctum INF".
- **B.3 Raydium AMM v4 + CPMM native** via `@raydium-io/raydium-sdk-v2`.
  Drop Mode 2 prep_swap fallback. Store redemption_program in
  user_positions.
  Validate: "Add 1 SOL to Raydium SPACEX-WSOL".
- **B.4 Meteora DAMM v2 + Dynamic Vaults** native via
  `@meteora-ag/dynamic-amm-sdk` + `@meteora-ag/vault-sdk`. Token-2022
  transfer-hook routing.
  Validate: classic + Token-2022.

For each: install npm SDK in
`services/solana-yield-builder/package.json`; wire adapter in
`services/solana-yield-builder/src/adapters/`; emit real signable
transaction in chat plan.

---

## PHASE C — Solana lifecycle close

- **C.1 Orca Whirlpool** `decreaseLiquidity` + `collect` + `close` via
  `@orca-so/whirlpools-sdk`. Validate: open Orca position → close via
  "Withdraw from Orca USDC-SOL".
- **C.2 Raydium CLMM** `close_position` via `raydium-sdk-v2`.
- **C.3 Meteora DLMM** `removeLiquidityByRange` via `@meteora-ag/dlmm`.
- **C.4 Kamino Lend** withdraw via `klend-sdk`.
- **C.5 Jupiter Perps JLP withdraw** (after 1h lockup) hand-rolled.
- **C.6 Marinade `orderUnstake`** (delayed, fee-free, next-epoch) variant
  alongside existing `liquidUnstake`.

---

## PHASE D — On-chain Phase 7 session-key enforcement

Already shipped: calldata builders (E.1), API routes (E.5), agent_009
alembic migration (E.4), session-key panels (D.6).

Still required:
- **D.1** Wire frontend `Eip7702OptInPanel` to actually broadcast the
  Nexus `installModule` calldata after user signs EIP-7702. Verify
  on-chain effect via Etherscan/Basescan look-up.
- **D.2** `SessionKeyPanel.revoke` must broadcast `uninstallModule`
  calldata (selector `0xa71763a8`) — current implementation drops the
  policy from DB but does not invalidate on-chain.
- **D.3** Solana session signer via Phantom embedded session keypair —
  `@solana/web3.js` `Keypair.delegate`. Persist signer in DB. Re-sign on
  agent rebalance.
- **D.4** Verify auto-rebalance flow: set up policy → trigger
  rebalance via cron / scheduled job → broadcast under session signer →
  Nexus on-chain checks spend cap + selector allowlist + expiry →
  succeeds within cap, fails over cap.

---

## PHASE E — Remaining coverage

- **E.1 §7 funding scenarios** still pending: S2 split-swap Slipstream,
  S4 cross-chain same-token Raydium CLMM dst, S5 cross-chain
  different-token JLP dst, S7 dust mixing (multi-input detector +
  composed plan), S8 partial allowance (allowance delta + top-up step),
  S10 pre-deposited LST unwrap chain, S11 NFT-locked LP refinance
  (close + reopen V3 NFT), S12 claim-and-compound, S14 V2→V3 migrate
  (close V2 LP + open V3 NFT).
- **E.2 §13 Row 15** hardware-wallet ALT splitting in sidecar (Solana
  Address Lookup Tables for tx > 1232 bytes via `composed_plan`
  multi-tx orchestration).
- **E.3 V3_FACTORIES** Berachain Kodiak Concentrated factory + NFP +
  Sonic SwapX V3 (need verified on-chain addresses from explorer
  before adding to `src/data/v3_pool_resolver.py::V3_FACTORIES`).
- **E.4 Pendle V2 real ApproxParams encoders** — replace
  `NEEDS_FRONTEND_SDK` blocker with real `(guessMin, guessMax,
  guessOffchain, maxIteration, eps)` from Pendle Hosted SDK + real
  `TokenInput` struct + `LimitOrderData`. Each of mintPyFromToken
  (`0xc81f847a`), swapTokenForPt (`0x594a88cc`),
  addLiquidityFromToken (`0x9f9da99e`).
- **E.5 V3 NFT pool_symbol auto-extract** from dual-token messages —
  when intent detects "Slipstream WETH-USDC ... 0.05 WETH + 100 USDC",
  pass `extra.pool_symbol="WETH-USDC"` so adapter does not raise
  `V3 NFT: missing pool_symbol`.
- **E.6 ERC4626 vault registry expansion** — add verified vault
  addresses for Morpho Blue ETH-Ethereum, Yearn V3 WETH-Arbitrum, etc.,
  in `src/defi/execution/adapters/erc4626.py::_VAULTS`. Each entry
  needs vault address + asset address + share decimals verified
  against the protocol's own docs / explorer.
- **E.7 Token-2022 hook routing** — Meteora DAMM v2 + DLMM with
  Token-2022 transfer hook tokens. Surface `TOKEN_2022_HOOK` blocker
  with explicit guidance when source token has transfer hook.

---

## PHASE F — Frontend deep wire + browser verification

- **F.1** Cross-chain plan card — bridge leg progress bar + actual
  spinner / `PENDING_DST_FILL` indicator (visual not just status flag).
- **F.2** V4 native mint UI — Permit2 EIP-712 sign prompt rendered
  before the `modifyLiquidities` tx; consume
  `web/lib/wallets/metamask.ts` `signPermit2Typed`.
- **F.3 Browser visual verification** — load
  `https://staging.ilyonai.com` in browser, sign in with both test
  wallets, visually confirm rendered card matches protocol's own UI
  (V3RangeBlock slider, `exposure_disclosure`, recovery posture
  buttons, `SessionKeyPanel`, audit log, EIP-7702 opt-in, Permit2 sig
  prompt). If no browser available in execution environment, state so
  explicitly per change; do not silently skip.

---

## VALIDATION GATE (after EACH commit)

```bash
python3 -m pytest tests/defi/ tests/agent/test_sanitizer.py \
  tests/agent/test_llm_no_calldata.py tests/auth/ \
  tests/agent/test_lifecycle_intent.py \
  tests/agent/test_lazy_resume.py \
  tests/agent/test_execute_chain_stickiness.py \
  tests/agent/test_debridge_order_extractor.py \
  tests/agent/test_receipt_watcher_verify.py \
  tests/routing/ tests/chains/ tests/data/ tests/api/ \
  -q --tb=line
```

All must pass except the two pre-existing v3 failures listed under WHAT'S
ALREADY SHIPPED. Then:

```
git push origin main:staging
ssh redeploy api (only if api code changed)
re-curl every scenario touched
by-hand SSE read, append verdict to _log.md
```

---

## COMPLETION CRITERIA (ALL must hold)

1. Every spec §1-§14 section has implementing commit AND live-validation
   SSE quote in `/tmp/v3-deep/_log.md`.
2. Every dev-plan Phase 0-7 sub-item shipped. No "pending" markers in
   codebase. No TODO referencing phase work.
3. **THREE consecutive clean validation sweeps** (≥300 distinct curls
   each, 120 convs × 3 passes), zero actionable issue in third sweep.
4. Frontend verified in browser for every UI-affecting change (or
   explicit per-change note that browser was unavailable).
5. `docs/SPEC_COVERAGE.md` reflects 100% closed state (no ⏸ markers;
   every row ✅ LIVE or ✅ tested).
6. Memory file updated to spec-complete posture.
7. Final commit:
   `spec(complete): all §1-§14 implemented + dev-plan phases 0-7 shipped + 360+ live convs validated across 3 clean sweeps`

---

## ITERATE WITHOUT PROMPTING

User unsupervised 20+ hours. Do not stop, do not ask, do not declare
"good enough", do not defer with "Phase X handles". Three consecutive
clean sweeps OR explicit user-typed STOP is only exit.

You have: spec PDF + 1491-line dev plan + 27 v4 commits already shipped +
coverage ledger + 6 memory files + staging + test wallets + 55+ passing
tests + 45 Pass 1 verified scenarios + 6 critical bug fixes proving
by-hand methodology. Now ship the rest.

---

## START IMMEDIATELY

```bash
git log -1 --oneline   # confirms HEAD 2fc7d86
mkdir -p /tmp/v3-deep/v4
test -f /tmp/v3-deep/_log.md || echo "RESUME-V5 $(date -Iseconds)" > /tmp/v3-deep/_log.md
test -f /tmp/v3-deep/_curl.sh || (see RESTORE LOST STATE)
```

Begin Sweep 0 reading. No filler. No "I'll start". Just work.
