# Phase D D1 — Tester-Ready Gate Status (mid-session checkpoint)

**Date**: 2026-05-21
**HEAD**: `2072bfd` (post Phase C wave C2-α + partial β)
**Matrix run**: `docs/matrix-runs/passA-waveD1/` (132 chains × 532 turns)
**Playwright run**: `docs/playwright-runs/20260521_151949/`

## 7-Gate Status

| Gate | Status | Detail |
|------|--------|--------|
| 1 Backend smoke | **AMBER** | Re-run probe truncated to 8 lines; 2 visible findings: (1) I02-currency-token-cap LEAKED — false positive (user_message field echoed by tool ObservationFrame; static_sweep already strips this, smoke probe needs the same strip); (2) I02-policy-signed: curl rc=28 60s timeout on Compound V3 session-key install probe. Real probe outcome unclear due to output buffering. |
| 2 Backend matrix 3x | **RED** | 1 of 3 clean passes attempted at SHA `2072bfd`. D1 surfaced 1 real regression + 1 false-positive (see below). NOT 3 consecutive clean. |
| 3 Runtime invariants | **GREEN** | `docs/matrix-runs/invariant-violations.log` exists, `drain()` chokepoint live (per Phase C batch H verification). |
| 4 Playwright N/N | **AMBER** | Last clean baseline 31/31 at SHA `cbff349`. D1 re-run got 23/31 — 8 failures all rooted in concurrent-matrix-load contention (502/500 on /api/v1/agent + composer-not-interactive timeouts). Sequential re-run needed. |
| 5 Anvil fork | **GREEN (with known-issue allowlist)** | 51/61 plans PASS, 10 remaining failures all "upstream-allowance-required" pattern (Enso shortcut / V3 NFT mint), no structural calldata bugs. |
| 6 11-batch re-audit | **AMBER** | Phase C v1 audit complete (`docs/audit-runs/phase-c-v1-summary.md`). 2 P0 closed (Sign hard-refuse + invariant_violation renderer); 3 P1 closed (ChainRegistry 10 chains, 7 CardRenderer cases, F07/F10 matrix codes); 7 P1 deferred + P2 backlog. Not 0/0/0. |
| 7 SPEC_COVERAGE + BUG_LEDGER | **AMBER** | Receipts up to Phase C v2; Phase D findings + remaining P1s not yet ledgered. |

## D1 Matrix regression findings

### REAL regression — H05_S5_xchain_diff_token turn 4
**File**: `docs/matrix-runs/passA-waveD1/H05_S5_xchain_diff_token/turn_4.txt`

**Final frame content** (excerpt):
> "Bridge transaction submitted on Ethereum (tx 0x3f…a9). **Once confirmed**, the USDT will arrive on Solana and the deposit to JLP will be executed (tx 0x7b…c2). Monitor both hashes on their respective explorers..."

This is the exact hallucination pattern wave-9 was meant to close — the agent confabulates "Bridge transaction submitted" with fake truncated tx hashes (`0x3f…a9`, `0x7b…c2`) and a "Once confirmed" promise WITHOUT emitting a signable `execution_plan_v3` card. The wave-9 sanitizer (BUG-E-013 fix) was supposed to strip "Once confirmed" tx-state hallucinations.

**Root cause hypothesis**: the sanitizer pattern in `src/agent/simple_runtime.py::_strip_freeform_tx_state_hallucinations` matches "Once confirmed" but only when card_ids is non-empty (a gate that was added in wave-12 to avoid stripping legitimate "Once confirmed" CTAs on real execution_plan cards). In this case `card_ids:[]` BUT the message still has fake tx hashes — the sanitizer skips it. Need to either drop the card_ids gate for this specific phrase pattern, OR add a separate ALWAYS-ON detector for "tx 0x[hex]…[hex]" + "Once confirmed" combo with `card_ids:[]`.

**Severity**: P0 — user reading this thinks the bridge is mid-execution when nothing was actually signed.

### FALSE POSITIVE — E01_eth_to_base_aave turn 3
**File**: `docs/matrix-runs/passA-waveD1/E01_eth_to_base_aave/turn_3.txt`
**Content**: "I can't confirm the **slippage band** without a deterministic Sentinel tool producing the calldata. Please use an explicit verb form such as `Bridge 100 USDC from Ethereum to Base via deBridge`..."

This is a DEFENSIVE refusal message — agent correctly refusing to fabricate slippage values, asking for an explicit verb. The probe's `must_not_contain` regex matches "slippage band" anywhere in the body, triggering a false positive. Fix: tighten the E02 probe to require slippage_band followed by a numeric (e.g. `slippage band [0-9]`) so refusals don't false-match.

## Remaining work to reach all-7-gates-GREEN (tester-ready)

### Backend
1. **H05 hallucination fix**: extend `_strip_freeform_tx_state_hallucinations` to catch "tx 0x[hex]…[hex]" + "Once confirmed" combo when `card_ids` is empty.
2. **E02 probe regex tighten**: require digit after `slippage band` to avoid refusal-text false matches.
3. **3 fresh consecutive clean matrix passes** at the new SHA after the above fixes (D2/D3/D4 — 90 min minimum).
4. **Smoke probe output buffering**: investigate why post_deploy_smoke output gets truncated to 5-8 lines on bg runs.

### Frontend / Phase C P1 deferred
5. **D.5 session-key per-action cap** (P1-C-005) — add `spend_cap_single_tx_usd` field to `SessionKeyPolicy`.
6. **§13 row 25 V4 pool-not-init** (P1-C-009) — emit `POOL_NOT_INITIALIZED` blocker with init-or-refuse CTA from V4 adapter.
7. **§13 row 27 wrong-spender preflight** (P1-C-010) — diff-check `step[i].transaction.target` vs `step[i+1].transaction.target` when step[i].action == "approve".
8. **§3.1 LiquidityIntent wire-up** (P1-C-006) — architectural refactor, large; defer to follow-up wave.
9. **§6d B-path source-token heuristic wire-up** (P1-C-007) — small wiring change in `build_yield_execution_plan.py`.
10. **Coinbase Wallet SDK** (P1-C-008) — `npm i @coinbase/wallet-sdk` + adapter impl.

### Validation infra
11. **Phase C v3 re-audit** after 5-10 land — re-dispatch 11 batches.
12. **Phase D integrated retest** with sequential gates (matrix → Playwright → smoke, NOT parallel — concurrency caused 8 false failures in D1 Playwright).

## Tester-ready estimated remaining

- Backend H05 fix + 3 matrix passes: ~3 hr
- Phase C P1 closures (5-10 above): ~2 hr  
- Phase C v3 re-audit (11 parallel subagents): ~30 min wall time, hands-off
- Phase D integrated retest sequentially: ~1 hr
- Final commit + tag + spec coverage update: ~15 min

**Total: ~6-7 additional hours.**

## What IS reliably green right now

- Backend matrix-fix loop fully closed at `9edaf83` (the `spec-complete` baseline — 3 clean passes verified)
- Backend wallet-assistant portfolio concurrent-dedupe + cache (`40c6878`)
- Frontend logo + CoinGecko proxy + balance-card-symbol filter (`cbff349`)
- Frontend Sign-gate hard-refuse + invariant_violation renderer + 6 more CardRenderer cases (`6f91bf8`)
- ChainRegistry 17 EVM + Solana wiring (`2072bfd`)
- Anvil fork-mainnet replay 51/61 plans (no structural bugs)
- Playwright 31/31 at peace-time (no concurrent backend load)

The agent + plan-builder + most card types are tester-acceptable. The remaining work is the H05 narration regression + the deferred Phase C P1 list.
