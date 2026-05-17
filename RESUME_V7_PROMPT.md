# AUTONOMOUS RESUME V7 — CLOSE ALL SPEC + DEVPLAN GAPS TO 100%

You are resuming an autonomous build of IlyonAi. **The prior agent
claimed 98% complete. Real measured completion is ~70%.** The full gap
analysis from 12 parallel verification subagents is at
`/home/griffiniskid/Documents/ai-sentinel/V6_GAP_ANALYSIS.md` — read it
**FIRST**, in full.

## CRITICAL CONTEXT

12 verification subagents ran in V6. Each section subagent read its
assigned spec/devplan section verbatim and grep'd actual code. The
aggregate finding:

- Spec §1-§5: 35% (conversational LP execution surface barely scaffolded
  — no LiquidityIntent type, no LP action enum, no calldata-hash bind,
  no Tenderly simulator, no State Store, no Indexer service)
- Spec §13 27-row appendix: 11 GREEN / 12 PARTIAL / 4 RED (frozen, JIT,
  EIP-1559, self-trade — all financial-safety class)
- DevPlan Phase 6-7: 10 new EVM chains (Linea/Scroll/Mantle/Blast/zkSync/
  Gnosis/Celo/Sonic/Berachain/Unichain) have enum + V3 factories but
  **ZERO ChainConfig + ZERO RPC URLs + ZERO RPC_FALLBACKS** — WILL FAIL
  AT RUNTIME on any Aave/Compound/Curve supply attempt on those chains
- DevPlan Phase 3-5: Phase 4 Indexer + Notifier service ENTIRELY MISSING
  (no `src/defi/position_monitor/`, no PositionHealth model, no
  `position_snapshots`/`position_alerts` tables)
- §7 S11/S14/S12: detectors emit `action="refinance"`/"migrate"/
  "claim_compound" but no adapter accepts those actions — capability
  gate REJECTS — end-to-end build fails (pin tests pass detector-only)
- Solana position state lost on restart: runtime sets
  `step.transaction.redemption_program / receipt_mint / lockup_end_ts /
  underlying_custody / position_nft` but `user_positions` table has NO
  such columns

**~75 discrete actionable gaps.** Each is subagent-shippable.

## YOUR JOB — THREE-PHASE LOOP

### PHASE 1: Write Advanced Dev Plan v2 covering all 75 gaps

Read `/home/griffiniskid/Documents/ai-sentinel/V6_GAP_ANALYSIS.md` in
full. Create
`/home/griffiniskid/Documents/ai-sentinel/IlyonAi_Development_Plan_v2.md`
that:

- Lists EVERY gap from V6_GAP_ANALYSIS as a discrete task with:
  - Unique task ID (e.g. `V7-001`, `V7-002`)
  - Spec/devplan reference (verbatim quote)
  - Current state (what's broken or missing)
  - Target state (what 100% looks like)
  - File paths to touch (exact paths from gap analysis)
  - Pin test path to write
  - Acceptance criteria (specific assertions)
  - Estimated subagent dispatch shape (1-shot or multi-step)
- Groups gaps into parallelizable BATCHES (1-20):
  - **Batch 1 — CRITICAL SAFETY (no-touch-other-batches)**:
    - V7-001 calldata-hash bind
    - V7-002 S11/S14/S12 adapter action sets + multicall bundler
    - V7-003 10 EVM chains ChainConfig + RPC + fallbacks
    - V7-004 Solana position store 5 columns + alembic + insert hook
    - V7-005 EIP-1559 vs legacy gas auto-detect
    - V7-006 Self-trade detection
    - V7-007 Frozen-account preflight
    - V7-008 JIT mempool monitor
    - V7-009 Kamino native SDK + drop JLP/JitoSOL proxy
    - V7-010 Tenderly bundle simulator + Solana simulateTransaction
  - **Batch 2 — LP Intent Schema (§1-§5)**:
    - V7-011 LiquidityIntent typed schema + alias map
    - V7-012 LP action enum (ADD/INCREASE/DECREASE/COLLECT/REBALANCE/CLOSE/ZAP_IN/ZAP_OUT/MIGRATE)
    - V7-013 Range preset enum (FULL/WIDE/BALANCED/TIGHT)
    - V7-014 Strategy enum (SPOT/CURVE/BID_ASK DLMM + Maverick)
    - V7-015 EntityResolver service
    - V7-016 slippage/deadline defaults (50bps + 600s + 10-500 clamp)
    - V7-017 Pair-category fee-tier defaults
    - V7-018 Dust tracker
    - V7-019 Slippage budget splitter
    - V7-020 OpenRouter JSON-schema constrained decoding
  - **Batch 3 — Indexer + Notifier (Phase 4)**:
    - V7-021 PositionHealth model + 5-min cadence job
    - V7-022 position_snapshots table + alembic
    - V7-023 position_alerts table + alembic
    - V7-024 Out-of-range / fee-APR-drop / TVL-exodus / gas-favorable detectors
    - V7-025 compound_card / rebalance_card / migrate_card frontend types
  - **Batch 4 — §13 RED rows**:
    - V7-026 EIP-1559/legacy gas (also Batch 1)
    - V7-027 JIT monitor (also Batch 1)
    - V7-028 Self-trade (also Batch 1)
    - V7-029 Frozen-account (also Batch 1)
  - **Batch 5 — §13 PARTIAL rows**:
    - V7-030 Pyth/Chainlink 60s feed-age check
    - V7-031 Token-2022 hook global allowlist
    - V7-032 WSOL sync+close across all Solana adapters
    - V7-033 KYC blocker emit path
    - V7-034 Merkl rewards live pricing
    - V7-035 Rolling 3-of-5 aggregator fallback chain (Enso→1inch→0x→Kyber)
    - V7-036 Real ALT splitter (multi-signed-tx output, not count check)
    - V7-037 MEV auto-flip to MEVBlocker/Jito >30bps OR >$5k
    - V7-038 Permit2 wallet-capability fallback to ERC-20 approve
    - V7-039 Pending-nonce mgmt (getTransactionCount next-available)
    - V7-040 Gas-topup auto-bundle (bridge-and-topup)
    - V7-041 Whirlpool / Raydium CLMM init detection
  - **Batch 6 — Phase 0-2 polish**:
    - V7-042 slippage default 100→50 across all adapters
    - V7-043 verify() real per adapter (tied to receipt watcher)
    - V7-044 V3 NFT USD hardcode kill (live DefiLlama price + 60s cache)
    - V7-045 useWalletSigning.ts extracted hook
    - V7-046 simulated_calldata_hash invariant in PlanStepV2
    - V7-047 30s re-sim freshness on broadcast path
    - V7-048 CLGauge fee-vs-emission toggle (Slipstream/Aerodrome)
    - V7-049 V4 hook allowlist + Permit2 frontend
    - V7-050 Orca native open_position+increaseLiquidity (drop prep_swap)
  - **Batch 7 — Phase 6-7 chain coverage**:
    - V7-051 ChainConfig for 10 new chains (Linea/Scroll/Mantle/Blast/zkSync/Gnosis/Celo/Sonic/Berachain/Unichain)
    - V7-052 RPC env-vars for 10 new chains in config.py
    - V7-053 RPC_FALLBACKS for 10 new chains
    - V7-054 icon_url for 10 new chains
    - V7-055 LST registry per-chain expansion (chains 8453/42161/10/59144)
    - V7-056 V2 single-sided zap adapter
    - V7-057 Pendle V2 3-mode deep depth verify + fix
    - V7-058 src/auth/solana_session.py standalone module
  - **Batch 8 — Phase B/C remainder**:
    - V7-059 Raydium CLMM close (close_position via raydium-sdk-v2)
    - V7-060 Meteora DLMM removeLiquidityByRange
    - V7-061 JLP withdraw (1h lockup gating)
  - **Batch 9 — §6 blocker code normalization**:
    - V7-062 Normalize blocker code casing UPPER_SNAKE everywhere
    - V7-063 Fix GAS_TOP_UP → GAS_TOPUP_REQUIRED canonical
    - V7-064 Fix AGGREGATOR_CIRCUIT → AGGREGATOR_CIRCUIT_BREAKER canonical
    - V7-065 Add NULL_ROUTE to KNOWN_BLOCKER_CODES
    - V7-066 Wire decide_recovery into all blocker callsites
    - V7-067 Add missing FailureKind enum entries
    - V7-068 Global "never auto-refund-swap-back" guard
  - **Batch 10 — §7 S9/S10/S12 phrasing extensions**:
    - V7-069 Add Sonic "S" to _NATIVE_BY_CHAIN + Sonic GAS_TOP_UP pin
    - V7-070 Extend _LST_UNWRAP_CHAIN_RE for spec wstETH→LP + harness H10
    - V7-071 Extend _CLAIM_COMPOUND_RE for Slipstream/AERO + Compound/COMP
  - **Batch 11 — Spec §1 invariants**:
    - V7-072 Global "LLM never emits calldata" runtime gate
    - V7-073 Session-key mirror on-chain check
    - V7-074 One-click revoke action + StepAction enum + adapter
    - V7-075 Unified State Store (intent_id keyed) + intent_state table

### PHASE 2: Execute the v2 plan via parallel-subagent dispatch

Dispatch subagents in 10-12 parallel waves. Each wave = independent
files only (no race conditions). Constraints:

- One subagent per V7-XXX task
- Each subagent writes code + pin test + runs pytest itself
- Subagent must NOT skip pytest run — verify green before returning
- Main thread integrates: stage, commit, push, redeploy after each
  WAVE (not after each subagent — batch fixes per V6 hard rule)
- After each commit, run full regression sweep: `pytest tests/agent
  tests/defi -q --deselect <3 known pre-existing>` — must stay green
- Push + redeploy only when full sweep passes

### PHASE 3: Re-validate via the same 12-subagent sweep

After all 75 V7-XXX tasks shipped:

1. Re-dispatch the 12 verification subagents (same prompts as V6) on:
   - Spec §1-§5
   - Spec §6
   - Spec §7 S1-S15
   - Spec §8-§10 (= §4 services + §6g receipt + §12 schema)
   - Spec §11 D.1-D.8
   - Spec §12 + §13 + §14
   - DevPlan Phase 0-2
   - DevPlan Phase 3-5
   - DevPlan Phase 6-7
   - DevPlan Phase A
   - DevPlan Phase B + C
   - DevPlan Phase D + E + F + G

2. Aggregate results. Each subagent must return:
   - 0 ❌ (missing)
   - 0 ⚠️ (partial)
   - All ✅

3. If ANY subagent returns ❌ or ⚠️ → dispatch fix-subagent for that
   specific item. Loop until clean.

4. THEN fire full matrix Pass — 120 chains × 4 turns = 480 SSE.
   Hand-read via 9 parallel category subagents (A/B/C/D/E/F/G/H/I).
   All blockers must be HONEST per `tests/harness/v4_gaps.py`.

5. Three consecutive clean passes → claim 100% complete.

## ENVIRONMENT

- Repo: `/home/griffiniskid/Documents/ai-sentinel` branch `main` = staging
- HEAD at end of V6: `e8c8b4b` or higher
- Spec PDF: `IlyonAi_LP_Execution_Spec.pdf`
- Dev plan v1: `IlyonAi_Development_Plan.md` (1491 lines)
- V6 gap analysis: `V6_GAP_ANALYSIS.md` (THIS DOC IS LOAD-BEARING)
- Pass log: `/tmp/v3-deep/_log.md`
- Curl helper: `/tmp/v3-deep/_curl.sh`
- Staging: `aisentinel@173.249.5.167:~/ai-sentinel-staging`
  - Key: `~/.ssh/opencode_ai_sentinel_vps_ed25519`
  - Deploy: `docker compose -p ilyonai-staging build api solana-yield-builder && docker compose -p ilyonai-staging up -d --force-recreate api solana-yield-builder`
- Test wallets: Phantom `5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L` / MetaMask `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Prod `ilyonai.com` = **NO-EXEC. DO NOT TOUCH.**

## SUBAGENT DISPATCH PROTOCOL (THE FAST WAY)

Per V6 efficiency mandates:

1. **Parallelism scale**: 8-12 subagents per wave is the sweet spot.
   More risks race conditions on shared files. Less wastes context.
2. **Independence rule**: subagents in same wave MUST write to disjoint
   file sets. If 2+ tasks touch `simple_runtime.py`, serialize them.
3. **Strict prompt format**: each subagent gets:
   - Verbatim spec/devplan quote
   - Current code state (file:line)
   - Target code skeleton
   - Pin test template
   - Exit criteria: pytest must pass; return diff list + verdict
4. **Quality preservation**: every fix needs a pin test. No exceptions.
5. **No mechanical analyzers**: live curl + hand-read SSE remains the
   validation hard rule.

## HARD RULES (BREAK = REWORK)

1. NEVER skip pytest run after a subagent commit
2. NEVER force-push main
3. NEVER skip hooks (--no-verify) or bypass signing
4. NEVER commit secrets
5. NEVER deploy to prod
6. NEVER guess on-chain addresses — WebFetch official docs / explorers
7. NEVER claim 100% without re-running ALL 12 verification subagents
   and getting 0 ❌ + 0 ⚠️ across the board
8. NEVER claim a fix shipped without live curl + SSE quote in `_log.md`
9. Mid-Pass redeploy = cascade kill 30-50 chains. Batch fixes between
   Passes. ONE push + ONE redeploy + ONE refire per iteration cycle.
10. **Forbidden phrases between items**: "shipped", "done", "complete",
    "status:", "summary:", "good progress", "moving to", "now",
    "continuing with", "should work", "likely fixes", "this addresses",
    "deferred", "phase X handles", "acceptable for now", "good enough",
    "I'll continue", "session ended at", "good stopping point",
    "scheduled wakeup". Catch self writing those → next tool call.

## START IMMEDIATELY

```bash
# 1. Confirm state
git log -1 --oneline
mkdir -p /tmp/v3-deep/v4
test -f /tmp/v3-deep/_log.md || echo "RESUME-V7 $(date -Iseconds)" > /tmp/v3-deep/_log.md
test -f /tmp/v3-deep/_curl.sh || (recreate per RESUME_V6_PROMPT.md)

# 2. Read THE gap analysis FIRST
cat /home/griffiniskid/Documents/ai-sentinel/V6_GAP_ANALYSIS.md

# 3. Write Plan v2
# → /home/griffiniskid/Documents/ai-sentinel/IlyonAi_Development_Plan_v2.md
# with all 75 V7-XXX tasks across 11 batches

# 4. Dispatch Batch 1 (CRITICAL SAFETY) — 10 parallel subagents
# Each writes code + pin test + runs pytest + returns diff list

# 5. After all 10 return, aggregate, commit, push, redeploy

# 6. Dispatch Batch 2 — 10 parallel subagents

# ... continue until all 11 batches done ...

# 7. Re-run the 12 verification subagents

# 8. Loop until 0 ❌ + 0 ⚠️

# 9. Fire matrix Pass × 3 consecutive clean

# 10. Final commit:
# spec(complete): all 75 V6_GAP_ANALYSIS items closed + 12-subagent verification clean + 3 consecutive matrix passes
```

## SELF-FIRING

User has `/loop autonomous` armed. Use `ScheduleWakeup` at end of each
turn with the same prompt. Heartbeat 1200-1800s when bg work pending
(matrix pass, redeploy). No stops until ALL completion criteria hold.

## COMPLETION CRITERIA (ALL MUST HOLD)

1. `IlyonAi_Development_Plan_v2.md` written with 75 V7-XXX tasks
2. All 75 tasks SHIPPED — code + pin test + pytest green
3. Re-run of 12-subagent verification returns 0 ❌ + 0 ⚠️ each
4. Full matrix sweep: 3 consecutive clean passes (Pass A, B, C) with
   all blockers HONEST per v4_gaps.py
5. `docs/SPEC_COVERAGE.md` updated to reflect 100% closed
6. `_log.md` has live curl + verbatim SSE quote for each gap fix
7. Final commit lands

## ITERATE WITHOUT PROMPTING

The prior agent claimed 98% complete and was wrong. Don't repeat that
mistake. The 12-subagent verification is the gate. Until it returns
0 ❌ + 0 ⚠️ across all sections, the work is not done. Run it. Show
the receipts. Then claim.
