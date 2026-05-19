# findings-F — matrix Pass A wave 1, category F (typed-recovery blockers)

**Scope**: `docs/matrix-runs/passA-wave1/F01..F10/turn_*.txt` — 10 chains, 40 turns.
**Verdict**: FINDINGS.

## P0 findings

### P0-F-01 — F01 t1 wrong typed code (`pool_not_found` lowercase, not in KNOWN_BLOCKER_CODES)
- Emit site: `src/agent/tools/execute_pool_position.py:475`. Recovery posture is generic "Pool unavailable" branch from `stuck_balance.py:164-173` — semantically wrong (no pool ever matched, nothing to leave/swap-back).
- Expected: `UNSUPPORTED_ADAPTER`.

### P0-F-02 — F02 t1 wrong typed code (`unsupported_chain` lowercase)
- Emit sites: `src/agent/tools/build_yield_execution_plan.py:614, :640`. The `detect_wallet_mismatch_blocker` detector in `scenario_blockers.py:528-582` IS wired, but the EVM-protocol-on-Solana early-return shorts out BEFORE `scan_scenario_blockers` runs, so the typed detector never sees it.
- Expected: `WALLET_CHAIN_MISMATCH`.

### P0-F-03 — F06 t4 TOOL_TIMEOUT on `build_yield_execution_plan` (45007ms, no card, no typed blocker)
- Same plan in F06 t1 built in 7ms with status:ready. Flaky upstream + no recovery enrichment on timeout path.

### P0-F-04 — F04 t1 wrong typed code on EXPECTED_BLOCKED row
- Emits `pool_not_found` instead of expected `PENDING_EPOCH_ENTRY + NEEDS_FRONTEND_SDK`. The EXPECTED_BLOCKED status covers the gate, not the typed code — frontend cannot distinguish "Pendle awaiting next epoch" from "user typo".

### P0-F-05 — F09 wrong typed code, no recovery, no card
- `simulate_swap` returns `err_envelope(code="quote_unavailable", …)` at `src/agent/tools/swap_simulate.py:150` — lowercase, NOT in KNOWN_BLOCKER_CODES. `NULL_ROUTE` was added to KNOWN_BLOCKER_CODES (`models.py:149`) + `FailureKind` (V7-067) specifically for this chain. No `_recovery` payload, no card. **The typed-recovery pipeline V7-065/V7-067 wired for F09 is unreachable from the simulate_swap callsite.**

## P1 findings

### P1-F-01 — Empty `affected_step_ids` on every emitted blocker
- F03 t1 (INSUFFICIENT_BALANCE), F08 t1 (GAS_TOPUP_REQUIRED). `detect_gas_missing_dst_blocker` at `scenario_blockers.py:258-263` DOES populate correctly; the empty-list emit comes from upstream preflight sites.

### P1-F-02 — F08 t3 recovery posture mismatch
- ADAPTER_BUILD_FAILED (canonical code) but recovery rationale says "Pool removed / paused / cap reached" — wrong branch. `decide_recovery` lacks a typed branch for ADAPTER_BUILD_FAILED, falls through to default ASK_USER with misleading copy. Real gap: missing WrappedTokenGatewayV3 registry entry.

### P1-F-03 — F10 AGGREGATOR_CIRCUIT_BREAKER blocker not surfaced as a card
- Appears only in prose, `card_ids:[]`. `build_swap_tx` returns err_envelope, never produces an `execution_plan_v3` card. Frontends filtering on card_type miss this blocker entirely.

### P1-F-04 — F05 internally inconsistent allocation
- F05 t3: 5 positions all flagged `adapter_id:"deterministic"` and `executable:true` in defi_opportunities, but execution_plan has `transaction:null` on indices 1/2/3/5 while allocation prose claims "4 of 5 cannot be signed automatically".

### P1-F-05 — F04 t4 sky-lending silently dropped from execution plan
- Allocation table has ranks 1..5 but execution_plan only has indices 1, 3, 4, 5 (rank 2 sky-lending dropped) with no blocker explaining why.

### P1-F-06 — Blocker normalizer never sees lowercase upstream codes
- Three codepaths emit lowercase codes (`pool_not_found`, `unsupported_chain`, `quote_unavailable`) that bypass normalization to canonical UPPER_SNAKE before reaching the SSE card payload.

## P2

- **P2-F-01** — F07 t2 8-word echo of user intent (`"Deposit 100 GLITCH-2022 to Meteora DAMM v2"`), no card.
- **P2-F-02** — F05 t4 / F08 t4 continuation pattern: re-emits prior card with `elapsed_ms:0` + canned "BLOCKER_NOT_RESOLVED".

## Cross-cutting root cause

**Three emit sites hand-mint blocker codes as lowercase string literals upstream of `scan_scenario_blockers`:**
- `src/agent/tools/execute_pool_position.py:475` (`pool_not_found`)
- `src/agent/tools/build_yield_execution_plan.py:614, :640` (`unsupported_chain`)
- `src/agent/tools/swap_simulate.py:150` (`quote_unavailable`)

The recovery normalizer / `enrich_blocker_with_recovery` only fires on blockers flowing through `scan_scenario_blockers`, so anything emitted earlier bypasses normalization AND recovery enrichment.

**Fix candidates**:
1. Move early-return emit sites BEHIND `scan_scenario_blockers`, OR
2. Add `_normalize_blocker_code()` at the `ExecutionPlanV3.add_blocker` boundary that maps known lowercase aliases → canonical UPPER_SNAKE and fires `enrich_blocker_with_recovery` for free.

Option 2 is cleaner — single chokepoint that fixes all three callsites + future ones.

## Summary
- Chains reviewed: 10
- Total turns: 40
- P0: 5
- P1: 6
- P2: 2
- Verdict: **FINDINGS** — cross-cutting normalization gap drives 4 of 5 P0s.
