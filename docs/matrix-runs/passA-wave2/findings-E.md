# findings-E — matrix Pass A wave 2, category E (cross-chain composed plans)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 1 (4 P0 + 4 P1).
**Verdict**: PROGRESS — 1 P0 CLOSED (BUG-E-002), 3 P0 STILL, 5 P1 (3 STILL + 2 NEW), 7 NEW TOOL_TIMEOUTs.

## Per-chain summary

| Chain | Wave-2 verdict |
|---|---|
| E01 | STILL P0 BUG-E-001; parser regressed — "via deBridge" now collapses protocol=debridge-dln |
| E02 | STILL P0 + STILL hallucination t3 |
| E03 | **CLOSED → WALLET_CHAIN_MISMATCH blocker** |
| E04 | STILL P0 + NEW TOOL_TIMEOUT t1/t3 |
| E05 | STILL P0 + STILL hallucination t2 + NEW TOOL_TIMEOUT t1/t3 |
| E06 | STILL P0 routing + **NEW BUG-E-010 prompt-leak t1** |
| E07 | STILL P0 BUG-E-003 unchanged; parser regressed t1/t2 to debridge-dln |
| E08 | **CLOSED → blocker + freeform clean** |
| E09 | STILL P0 routing; **EXPECTED_BLOCKED RETIRED** (Morpho `0x7c574174…8B3Ed` resolves); NEW TOOL_TIMEOUT |
| E10 | STILL P0 + STILL hallucination t2 |
| E11 | **CLOSED → blocker** |
| E12 | STILL P0 + STILL E-005 (MATIC≈$0.089) + NEW TOOL_TIMEOUT t1/t3 |
| E13 | STILL P0 + STILL E-005 + STILL hallucination t3 |
| E14 | STILL P0 + **NEW E-005 scope (AVAX ≈ $9.09 vs real ~$25-30)** |
| E15 | **CLOSED t1** + STILL hallucination t3/t4 |

## P0 CLOSED (1)

**BUG-E-002 — `senderAddress=guest` to deBridge → CLOSED.** E03/E08/E11/E15 all emit structured execution_plan_v3 with `blockers[0].code=WALLET_CHAIN_MISMATCH`, `recoverable=true`, CTA "Connect an EVM wallet…", zeroed totals. No HTTP 400, no DLN docs URL leak.

## P0 STILL (3)

- **BUG-E-001 parser drops cross-chain (10/15 chains)**. Regression: E01/E02/E07 t1/t2 now parse "via deBridge" as `protocol=debridge-dln, action=supply` → nonsensical pool_link cards.
- **BUG-E-003 E07 t4 bridge transaction:null + missing COMPOSED_PLAN_INCOMPLETE_TX blocker**. Bytewise identical to wave 1.
- **BUG-E-004 freeform hallucinations** — wave-1 8/7, wave-2 6/5 turns (canned-refusal gate catches some naked-context turns but NOT turns with prior chat context). E02 t3, E05 t2, E10 t2, E13 t3, E15 t3/t4 still hallucinate.

## P1 (5)

- **BUG-E-005** STILL + EXPANDED. Gas-topup oracle ~50% real price. MATIC $0.089 (real $0.20), **NEW AVAX $9.09 (real ~$25-30)**.
- **BUG-E-007** STILL (subsumed by BUG-E-001 root).
- **BUG-E-008** STILL (`190.132 USDC` mock balance leaks across chains).
- **NEW BUG-E-009 (P1)**: BUG-E-002 fix uses wrong enum. Sets `code=WALLET_CHAIN_MISMATCH` but the condition is "no wallet connected at all". UI may auto-prompt "Switch network" instead of "Connect wallet". Fix: introduce/use `WALLET_NOT_CONNECTED`.
- **NEW BUG-E-010 (P1, escalate to P0 if reproduces elsewhere)**: Internal chain-of-thought leakage into user-facing `final` on E06 t1. 35+ lines of raw reasoning ("We need to follow instruction…", computed sums, "OUTPUT FORMAT — markdown:" scaffolding).

## NEW: TOOL_TIMEOUT regression
Wave 1: zero. Wave 2: **7 turns / 4 chains** on `build_yield_execution_plan` 45s SLO (E04 t1+t3, E05 t1+t3, E09 t1, E12 t1+t3). All single-chain dst plans on BUG-E-001 fallback path. Possible Enso/RPC contention. **Cross-cutting with G, D, F regressions.**

## EXPECTED_BLOCKED
- **E09 RETIRED** — confirmed Morpho `0x7c574174…8B3Ed` resolves; emits real `0x6e553f65` ERC-4626 deposit calldata.
- E11 still legit-but-moot (short-circuits at WALLET_CHAIN_MISMATCH before vault resolution).

## Counts

| Metric | Wave 1 | Wave 2 |
|---|---|---|
| Fully-working composed plans | 0 | **0** |
| WALLET_CHAIN_MISMATCH triggered (was HTTP 400) | 0 (4 failures) | **4 ✓** |
| TOOL_TIMEOUT events | 0 | **7 turns / 4 chains** |
| Sentinel violations | 8/7 | **7/6** |
| EXPECTED_BLOCKED retired | — | **1 (E09)** |
| P0 open | 4 | **3** |
| P1 open | 4 | **5** |

**Verdict**: STILL BLOCKING. Highest-impact next: BUG-E-001 parser (unblocks 10/15). Cheapest: BUG-E-009 (one-line enum). Highest-trust-risk: BUG-E-004 (gate misses prior-context turns).
