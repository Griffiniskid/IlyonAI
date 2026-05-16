# AUTONOMOUS RESUME V6 — IlyonAi SPEC + DEVPLAN 100% COMPLETION

You are resuming an autonomous build that has run for **40+ hours across
multiple sessions** to ship 100% of `IlyonAi_LP_Execution_Spec.pdf`
§1-§14 + `IlyonAi_Development_Plan.md` Phase 0-7. The compaction that
just happened wiped `/tmp/v3-deep/v4/` and killed every bg matrix
runner. Git history survived. Memory files survived. Staging deployment
survived at HEAD `1dc8f7e` (or higher if more shipped before compaction).

**This is a continuation, not a restart.** Do not redo work that is
already in git. Do not re-design the matrix. Do not re-write detectors
that already exist. Read state, then close the remaining gaps.

**You will not stop until every condition in COMPLETION CRITERIA holds.
Not a single stop allowed before then. Explicit user-typed STOP is the
only acceptable exit. Wait conditions, "Pass N takes 50min", "code is
ready for review", "good progress, will continue next turn", "good
stopping point" — all FORBIDDEN. Always next tool call.**

---

## ENVIRONMENT

- Repo: `/home/griffiniskid/Documents/ai-sentinel` branch `main` = staging
- HEAD at compaction: `1dc8f7e` or higher (33+ v5 commits already shipped from `5806836` baseline)
- Spec PDF: `IlyonAi_LP_Execution_Spec.pdf` (40 pages, v1.0 · 2026-05-14)
- Dev plan: `IlyonAi_Development_Plan.md` (1491 lines)
- Coverage ledger: `docs/SPEC_COVERAGE.md` (read FIRST — v5 sections appended through 70e6863)
- Pass 4 results: 68 ready, 11 v4_gaps-HONEST blocked, 1 transient sidecar (D10)
- Matrix runner: `tests/harness/v4_runner.py`
- Matrix chains: `tests/harness/v4_matrix.py` (120 chains × ≥4 turns)
- v4_gaps allowlist: `tests/harness/v4_gaps.py` (HONEST-RECOVERY chains acceptable as PASS)
- Pass log: `/tmp/v3-deep/_log.md` — RESTORE this path; mkdir if gone after compaction
- Curl helper: `/tmp/v3-deep/_curl.sh` — recreate if gone (see RESTORE LOST STATE)
- Memory: `~/.claude/projects/-home-griffiniskid-Documents-ai-sentinel/memory/`
  Read in this order:
    1. `resume_2026-05-16_v5_continuation.md` (32-commit state, Pass 2/3/4 results, what's pending)
    2. `resume_2026-05-16_v4_continuation.md`
    3. `resume_2026-05-15_v3_continuation.md`
    4. `resume_2026-05-15_v2_continuation.md`
    5. `feedback_no_stopping_between_items.md` (HARD RULE — never stop between items)
    6. `feedback_validation_no_mechanical.md` (HARD RULE — real curl + by-hand SSE)
    7. `MEMORY.md` (index)
- Prod `ilyonai.com` = **NO-EXEC. Never deploy. Never touch.**
- Staging: `aisentinel@173.249.5.167:~/ai-sentinel-staging`
  Key: `~/.ssh/opencode_ai_sentinel_vps_ed25519`
- Test wallets:
  - Phantom (Solana): `5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L`
  - MetaMask (EVM): `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`

---

## RESTORE LOST STATE (do this first, ONLY if missing)

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

---

## HARD VALIDATION RULES (BREAK = REWORK)

1. **NO MECHANICAL ANALYZER.** No PASS/FAIL/✓/✗ summary script. Every
   blocker = real curl → `cat` full SSE → human-read every byte →
   plain-words prose verdict → fix at root → push main+main:staging →
   SSH redeploy → re-curl → re-read. If you cannot describe each
   event/card/field in prose, you have NOT read it.

2. **EVERY actionable blocker logged** to `/tmp/v3-deep/_log.md`. One
   paragraph per chain. Path to SSE capture next to verdict. No "looks
   fine" without quote.

3. **NEVER write end-of-cycle text.** After every commit → IMMEDIATELY
   run the next tool call. After test passes → IMMEDIATELY edit next
   file. After curl → IMMEDIATELY read SSE + fix or move next. Only
   acceptable stop = explicit user STOP or all COMPLETION CRITERIA met.

4. **NO MID-STREAM REDEPLOYS during a Pass run.** Each mid-Pass
   redeploy cascade-kills 30-50 chains (~30s API downtime). Batch ALL
   code fixes between Passes. ONE push + ONE redeploy + ONE refire per
   iteration cycle. Exception: deploy fix BEFORE re-firing only the
   chains that need that fix.

5. **NEVER force-push main.** NEVER skip hooks (`--no-verify`). NEVER
   bypass signing. NEVER commit secrets. NEVER deploy to prod.

6. **NEVER use mocked or guessed on-chain addresses** when shipping
   adapter/encoder code that will sign real transactions. Verify each
   address against on-chain explorer or official protocol docs before
   committing. Wrong addresses = financial loss for tester.

7. **NEVER count v4_gaps-allowlist chains as actionable regressions.**
   Use `python3 -c "from tests.harness.v4_gaps import EXPECTED_BLOCKED;
   gaps = set(e[0] for e in EXPECTED_BLOCKED); print(c in gaps)"` to
   cross-check.

8. **Forbidden phrases between items:** "X commits shipped", "X tests
   pass", "next step is", "moving to", "now", "continuing with",
   "shipped", "done", "complete", "status:", "summary:", "let me know",
   "should work", "likely fixes", "this addresses", "deferred", "phase
   X handles", "acceptable for now", "good enough", "I'll continue",
   "session ended at", "good stopping point", "scheduled wakeup". Catch
   self writing those → delete + next tool call.

---

## EFFICIENCY MANDATES (V6 ADDITIONS)

### E1. Parallel-subagent for matrix SSE read

Dispatch one general-purpose subagent per category (A/B/C/D/E/F/G/H/I)
when reading Pass captures by hand. Each agent gets ~13 chain dirs,
reads every SSE byte, returns one-paragraph verdict per chain into a
JSON-shaped result. You aggregate. 9x speedup on read step, same
quality (each agent does the SAME hand-read protocol).

```python
Agent(
  subagent_type="general-purpose",
  description="Read Pass-N category-A SSE",
  prompt="Read every byte of these 13 SSE captures in
  /tmp/v3-deep/v4/A*/turn_*.txt. For each chain, write ONE paragraph
  describing: which turn surfaced what status, blocker code+detail
  quoted verbatim, whether HONEST or ACTIONABLE. Return table at end."
)
```

### E2. Batch redeploy

Accumulate 5-10 commits between staging pushes. Single redeploy per
batch. After redeploy, refire ONLY chains affected by the batch.

### E3. Spec-gap allowlist (v4_gaps.py) authoritative

Every Pass tally MUST cross-check against `is_expected_blocked(chain_id,
turn_idx)`. If chain is in allowlist, count as PASS. Do NOT investigate
unless something CHANGED in the allowlist entry.

### E4. Parallel adapter subagents for Phase B (Solana hand-rolled)

For each of B.1 JLP / B.2 Sanctum INF / B.3 Raydium AMM v4 + CPMM /
B.4 Meteora DAMM v2, dispatch a parallel subagent that:
- Installs the required npm SDK in `services/solana-yield-builder/`
- Fetches anchor IDL from on-chain via web3.js
- Scaffolds the Python adapter that emits real signable instruction
- Writes pin tests

You integrate + commit serially.

### E5. Parallel WebFetch for verified addresses

For Berachain Kodiak / Sonic SwapX V3 factories + Morpho Blue Arb USDC
vault + Yearn V3 yvWETH Arb vault, dispatch parallel WebFetch
subagents to protocol official docs + Etherscan. Return verified
addresses + DefiLlama UUID + explorer link. You commit.

### E6. Quality preservation under parallelism

Every subagent does the SAME by-hand SSE/code read. Every fix still
needs pin test + regression sweep. Every on-chain address still
verified before commit. No quality compromise; just dispatch in parallel
instead of serial.

### E7. Curve / Curve-like multi-input adapter for §7 S7 dust mixing

User message form: "Use 50 USDC + 50 USDT + 50 DAI to deposit to Curve
3pool". Need detector → build_yield_execution_plan(curve, action=
deposit_lp, extra={input_tokens:[(USDC, 50), (USDT, 50), (DAI, 50)]}).
Curve adapter add_liquidity already accepts multi-input — wire extra
through.

### E8. Pendle real ApproxParams via Hosted SDK quote

Replace `NEEDS_FRONTEND_SDK` blocker in `pendle_v2.py` with a real call
to Pendle's quote endpoint (https://api-v2.pendle.finance/core/v1/sdk).
Endpoint returns `(guessMin, guessMax, guessOffchain, maxIteration,
eps)` for given (chainId, market, action, tokenIn, amountIn). Use
WebFetch or aiohttp client. Cache 5min.

### E9. Phase D on-chain enforcement — minimal viable broadcast

Wire `Eip7702OptInPanel.onSign` → POST `/api/v1/eip7702/authorize` →
backend submits authorization tuple via signer. NO browser needed for
backend code — only frontend integration. Browser-blocked items get
explicit code comment `# Pending browser verification` rather than
silent skip.

---

## WHAT'S ALREADY SHIPPED (sealed at HEAD `1dc8f7e`; DO NOT REDO)

LIVE on staging (verified by-hand SSE read across resume v1/v2/v3/v4/v5):

- F.3 Aave V3 native ETH full lifecycle via WTG3 — supply `0x474cf53d`,
  withdraw `0x80500d20`, repay `0x02c5fcf8`, borrow `0x66514c97`
- F.5 LST/LRT direct-mint LIVE for 9 protocols: Lido / Rocket Pool /
  ether.fi / Renzo / Swell / Frax / Mantle / Kelp / Marinade / Jito
- F.6 V2 LP withdraw (`0xbaa2abde`) + PCS V2 BSC + Sushi/UniV2 Ethereum
- F.7 Balancer exit_pool (`0x8bdb3913`) + native gas-token alias (ETH↔WETH)
- F.4 Pendle V2 per-mode dispatch + `PENDING_EPOCH_ENTRY` +
  `NEEDS_FRONTEND_SDK` (real ApproxParams encoders pending — V6 Phase E.8)
- F.8 §6f recovery wired into 4+ blocker sites
- F.9 `ReceiptWatcher.verify_step_receipt` + 30-entry ReceiptKind map
- F.10 §11 D.7 explicit >50bps drift gate
- C.2 `ComposedPlanOrchestrator` + runtime notifier wire in `main.py`
- C.3 LI.FI + Socket Bridge fallbacks
- §6c cross-chain composed plan LIVE: ETH→Base/Arbitrum/Polygon
- D.1 deBridge DLN orderId extractor
- D.5 frontend types + panels: `SessionKeyPanel` + `AuditLogPanel` +
  `Eip7702OptInPanel` + `Permit2SigButton`
- E.1 Biconomy Nexus session-key install/uninstall calldata
  (`0x9517e29f` / `0xa71763a8`)
- E.2 ZeroDev Kernel sibling
- E.4 alembic `agent_009` `biconomy_session_authorizations` table
- E.5 `/api/v1/eip7702/{prepare,authorize}` + `/audit/{wallet}`
- §13 26/27 edge-case rows (only Row 15 ALT splitting pending)
- Phase 6 chain expansion 8→18 EVM + V3_FACTORIES 16/18 + LST registry 9

**v5 intent-routing fixes (32 commits):**
- `_LP_PROTO_FIRST_RE` + '+' dual-token (§7 S1/S2)
- fee-tier marker + chain inference for protocol-first LP
- explicit-ref regex bare-digit '1' false-match fixed (A11/A19/A20)
- native/wrapped qualifiers + bare-chain trailing (H03)
- `_NON_ASSET_UNITS` rejects INSTEAD/NOW/THEN/IN/TO/HERE/THERE
- `_detect_lazy_proto_asset_action` history bare-amount fallback (A07/A09)
- Lifecycle bare-amount + digit-leading pool names (D04/D05/D06)
- Refine inherits product_types from prior items (A07/A19/A20)
- Anaphora resume 'Deposit X there' / 'in that pool' (A03)
- Inverted LP form PAIR optional + dual-token reconstruction (C04)
- Bridge-action `_detect_lazy_resume_from_history` refusal (E01/E02)
- Chain-word captured as asset disambiguation (H13/G05)
- Balancer native gas-token alias for pool lookup + leg-match (C07)
- v4_gaps.py HONEST-RECOVERY allowlist (V5 acceptable)
- `_detect_aave_supply` alt2 chain-between-asset-and-verb (G05)
- Lifecycle proto strip trailing receipt/asset words (D07)
- Per-protocol canonical-chain default for lifecycle (D04)
- `lazy_resume` amount override 'Confirm 50' (G05)
- Balancer admit `join_pool`/`remove_liquidity` aliases (C07 T4)
- V3 NFT close-by-tokenId detector (D01)
- `lazy_resume` preserves V3 NFT / V4 / cross-chain extras (H03)
- Aave V3 withdraw step `asset_in` = underlying not aToken slug (D02 T4)
- `_OPEN_POSITION_RE` native qualifier + uniswap-v3 ethereum default (D01)
- `_PROTO_LEADING_ALIAS` PCS→pancakeswap + `lazy_resume` extra.action (D04)
- v4_gaps D05 no-amount Balancer
- `lazy_resume` recovers pool_symbol from `payload.range_block.pair` (H03)

**Matrix Pass 1/2/3/4 results**:
- Pass 1: 45/120 ready
- Pass 2: 68 ready, 11 v4_gaps-HONEST
- Pass 3: 70 ready, 11 v4_gaps-HONEST
- Pass 4: 68 ready, 11 v4_gaps-HONEST + 1 transient D10 sidecar timeout

760+ tests pass in agent + defi + auth + routing + chains narrow filter
at HEAD `1dc8f7e`. Two pre-existing test failures (NOT v4/v5 regressions):
- `tests/agent/test_simple_runtime.py::test_run_ephemeral_turn_strips_llm_reasoning_leak_from_final_answer`
- `tests/agent/test_simple_runtime.py::test_detect_intent_keeps_highest_scoring_capital_request_as_allocation`

---

## START HERE (Sweep 0 — confirm + plan)

1. `mkdir -p /tmp/v3-deep/v4` and append `RESUME-V6 <iso-ts>` to
   `/tmp/v3-deep/_log.md` (recreate both if missing).
2. Read `docs/SPEC_COVERAGE.md` — full state ledger through v5.
3. Read memory file `resume_2026-05-16_v5_continuation.md` for v5 deltas.
4. `git log -1` confirms HEAD `1dc8f7e` or higher; `git status` confirms clean tree.
5. Verify staging head via SSH:
   `ssh -i ~/.ssh/opencode_ai_sentinel_vps_ed25519 -o StrictHostKeyChecking=no \
    aisentinel@173.249.5.167 'cd ~/ai-sentinel-staging && git log -1 --oneline'`
6. Health-check staging:
   `bash /tmp/v3-deep/_curl.sh /tmp/sanity-check.txt 'hello' v6-meta`
   Expect 200 with greeting.
7. Read `tests/harness/v4_gaps.py` to know HONEST-blocked chains.
8. Begin **EFFICIENT EXECUTION LOOP** (below).

---

## EFFICIENT EXECUTION LOOP

This is the only loop that runs. Repeat until COMPLETION CRITERIA met.

### Step A — One full matrix sweep (~50min wall, parallel subagents skip this)

```bash
echo "=== Pass N+1 fresh full $(date -Iseconds) — staging $(git rev-parse --short HEAD) ===" >> /tmp/v3-deep/_log.md
rm -rf /tmp/v3-deep/v4/*/
python -m tests.harness.v4_runner --all --force --delay 0.4 > /tmp/v3-deep/v4/_passN.out 2>&1 &
```

### Step B — Parallel subagent SSE read (in parallel with Step A's grind)

Dispatch 9 parallel agents (one per category A-I). Each reads ~13
chains × ~4 turns = ~52 SSE files, returns table of (chain, status,
blocker, root_cause).

### Step C — Aggregate verdicts

Cross-check every blocker against `v4_gaps.is_expected_blocked`.
HONEST → count as PASS. ACTIONABLE → list for batch-fix.

### Step D — Batch-fix actionable blockers

For each ACTIONABLE chain:
1. Read its SSE captures by hand (you, in main context).
2. Identify root cause via gitnexus_impact + Read tool.
3. Write fix + pin test.
4. Run `python3 -m pytest tests/agent tests/defi -q --tb=line`.
5. Verify 0 new regressions.

### Step E — Batch redeploy

Single `git push origin main main:staging` + single SSH redeploy.

### Step F — Refire only actionable chains

```bash
for c in <actionable_chain_ids>; do
  python -m tests.harness.v4_runner "$c" --force --delay 0.4 2>&1 | tail -1
done
```

### Step G — Re-tally

If all-blocked-are-HONEST → Pass clean. Move to next Pass.
If new actionable surfaces → back to Step D.

### Step H — Three consecutive clean passes

When Pass N, Pass N+1, Pass N+2 ALL surface only HONEST blockers AND
no transient infrastructure timeouts → matrix gate satisfied.

---

## REMAINING WORK (Phase B / C / D / E / F)

### Phase B — Solana hand-rolled programs (parallel dispatch)

- **B.1 JLP native** via Jupiter Perps program
  `PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu` `add_liquidity` IX.
  Fetch anchor IDL. Hand-roll IX in `services/solana-yield-builder/src/adapters/jlp.js`.
  Single-token-in, basket-out at NAV. 1h withdraw lockup surfaced.
- **B.2 Sanctum INF native** via S-Controller program
  `5ocnV1qiCgaQR8Jb8xWnVbApfaygJ8tNoZfgPwsgx9kx` `add_liquidity` IX.
  Drop Jupiter proxy.
- **B.3 Raydium AMM v4 + CPMM native** via `@raydium-io/raydium-sdk-v2`.
  Drop Mode 2 prep_swap fallback. Store redemption_program in
  `user_positions`.
- **B.4 Meteora DAMM v2 + Dynamic Vaults** native via
  `@meteora-ag/dynamic-amm-sdk` + `@meteora-ag/vault-sdk`. Token-2022
  transfer-hook routing.

### Phase C — Solana lifecycle close (parallel dispatch)

- **C.1 Orca Whirlpool** `decreaseLiquidity` + `collect` + `close` via
  `@orca-so/whirlpools-sdk`.
- **C.2 Raydium CLMM** `close_position` via `raydium-sdk-v2`.
- **C.3 Meteora DLMM** `removeLiquidityByRange` via `@meteora-ag/dlmm`.
- **C.4 Kamino Lend** withdraw via `klend-sdk`.
- **C.5 Jupiter Perps JLP withdraw** (after 1h lockup) hand-rolled.
- **C.6 Marinade `orderUnstake`** (delayed, fee-free, next-epoch).

### Phase D — On-chain Phase 7 session-key enforcement

Already shipped: calldata builders (E.1), API routes (E.5), agent_009
alembic migration (E.4), session-key panels (D.6).

Still required:
- **D.1** Wire frontend `Eip7702OptInPanel` to actually broadcast the
  Nexus `installModule` calldata after user signs EIP-7702. Verify
  on-chain effect via Etherscan/Basescan look-up.
- **D.2** `SessionKeyPanel.revoke` must broadcast `uninstallModule`
  calldata (selector `0xa71763a8`).
- **D.3** Solana session signer via Phantom embedded session keypair —
  `@solana/web3.js` `Keypair.delegate`. Persist signer in DB. Re-sign
  on agent rebalance.
- **D.4** Verify auto-rebalance flow under session signer.

### Phase E — Remaining coverage

- **E.1 §7 funding scenarios** still pending: S2 split-swap Slipstream,
  S4 cross-chain same-token Raydium CLMM dst, S5 cross-chain
  different-token JLP dst, S7 dust mixing (multi-input detector +
  composed plan), S8 partial allowance (allowance delta + top-up
  step), S10 pre-deposited LST unwrap chain, S11 NFT-locked LP
  refinance (close + reopen V3 NFT), S12 claim-and-compound, S14
  V2→V3 migrate (close V2 LP + open V3 NFT).
- **E.2 §13 Row 15** hardware-wallet ALT splitting in sidecar.
- **E.3 V3_FACTORIES** Berachain Kodiak Concentrated factory + NFP +
  Sonic SwapX V3 (need verified on-chain addresses).
- **E.4 Pendle V2 real ApproxParams encoders** — replace
  `NEEDS_FRONTEND_SDK` blocker with real call to Pendle Hosted SDK
  quote endpoint (https://api-v2.pendle.finance/core/v1/sdk).
- **E.5 V3 NFT pool_symbol auto-extract** from dual-token messages —
  already partial via H01.
- **E.6 ERC4626 vault registry expansion** — Morpho Blue ETH-Ethereum,
  Yearn V3 WETH-Arbitrum, etc. Need verified addresses.
- **E.7 Token-2022 hook routing** — Solana mint w/ transfer hook
  tokens. Surface `TOKEN_2022_HOOK` blocker with guidance.

### Phase F — Frontend deep wire + browser verification

- **F.1** Cross-chain plan card — bridge leg progress bar + actual
  spinner.
- **F.2** V4 native mint UI — Permit2 EIP-712 sign prompt rendered
  before `modifyLiquidities` tx.
- **F.3 Browser visual verification** — load
  `https://staging.ilyonai.com` in browser, sign in with both test
  wallets, visually confirm rendered card matches. If no browser
  available, state explicitly per change; do not silently skip.

---

## VALIDATION GATE (after EACH commit)

```bash
python3 -m pytest tests/agent tests/defi tests/auth tests/routing \
  tests/chains tests/data tests/api tests/agent/test_lifecycle_intent.py \
  tests/agent/test_lazy_resume.py tests/agent/test_execute_chain_stickiness.py \
  tests/agent/test_lp_proto_first.py tests/agent/test_lp_top_one_unit.py \
  tests/agent/test_top_one_carve_out.py tests/agent/test_v3_nft_close.py \
  tests/agent/test_refine_product_types.py \
  -q --tb=line
```

All pass except the two pre-existing v3 failures. Then:

```
git push origin main:staging
ssh redeploy api (only if api code changed)
re-curl every actionable chain
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
   Use v4_gaps.is_expected_blocked() to filter HONEST-acceptable.
4. Frontend verified in browser for every UI-affecting change (or
   explicit per-change note that browser was unavailable).
5. `docs/SPEC_COVERAGE.md` reflects 100% closed state (no ⏸ markers;
   every row ✅ LIVE or ✅ tested).
6. Memory file updated to spec-complete posture.
7. Final commit:
   `spec(complete): all §1-§14 implemented + dev-plan phases 0-7 shipped + 360+ live convs validated across 3 clean sweeps`

---

## ITERATE WITHOUT PROMPTING

User unsupervised 40+ hours. Do not stop, do not ask, do not declare
"good enough", do not defer with "Phase X handles". Three consecutive
clean sweeps OR explicit user-typed STOP is the only exit.

If a single tool call fails (SSH reset, curl timeout) → IMMEDIATELY
retry. Connection issues are transient. Never wait + ask.

If Pass takes 50min → dispatch parallel subagent reviewers while it
runs. Never block on bg without parallel productive work.

You have: spec PDF + 1491-line dev plan + 33+ v5 commits already
shipped + coverage ledger + 7 memory files + staging + test wallets +
760+ passing tests + Pass 4 confirmed effectively clean + 11 critical
bug fixes proving by-hand methodology. Now ship the rest.

---

## START IMMEDIATELY

```bash
git log -1 --oneline   # confirms HEAD 1dc8f7e or higher
mkdir -p /tmp/v3-deep/v4
test -f /tmp/v3-deep/_log.md || echo "RESUME-V6 $(date -Iseconds)" > /tmp/v3-deep/_log.md
test -f /tmp/v3-deep/_curl.sh || (recreate per RESTORE LOST STATE section)
ssh -i ~/.ssh/opencode_ai_sentinel_vps_ed25519 -o StrictHostKeyChecking=no aisentinel@173.249.5.167 'cd ~/ai-sentinel-staging && git log -1 --oneline'
```

Begin Sweep 0 reading + parallel-subagent dispatch. No filler. No
"I'll start". Just work. Every tool call leads directly to the next.
Until 3 clean consecutive passes + Phase B/C/D/E/F all shipped + final
commit landed. Then stop. Not before.
