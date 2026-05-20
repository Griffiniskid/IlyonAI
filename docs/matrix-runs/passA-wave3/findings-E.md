# findings-E — matrix Pass A wave 3, category E (cross-chain composed plans)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 2 (3 P0 + 5 P1).
**Verdict**: REGRESSION ON SENTINEL, NO COMPOSED-PLAN PROGRESS — 0/15 working composed plans (still); 4 WALLET_CHAIN_MISMATCH (E03/E08/E11/E15) holds CLOSED; BUG-E-001 parser regression unchanged; BUG-E-003 MUTATED; BUG-E-004 hallucinations EXPANDED.

## Per-chain summary

| Chain | Wave-3 verdict |
|---|---|
| E01 | STILL P0 BUG-E-001 t1 (debridge-dln pool_link); canned-refusal t2-t4 |
| E02 | STILL P0 BUG-E-001; NEW E-004 t2 ("deterministic plan is ready…0.5% slippage"); STILL E-004 t3 |
| E03 | **CLOSED → WALLET_CHAIN_MISMATCH** t1; **NEW E-004 t2 full bridge how-to**; **NEW E-004 t3 LI.FI how-to** |
| E04 | STILL TOOL_TIMEOUT t1; **NEW E-004 t2**; t3 single-chain Optimism (BUG-E-001) |
| E05 | t1 single-chain Arbitrum (BUG-E-001); **STILL E-004 t2 ("Bridge fee ≈0.45%")** |
| E06 | t1 **STILL BUG-E-010 raw chain-of-thought leakage**; **NEW TOOL_TIMEOUT t3** |
| E07 | STILL P0 BUG-E-001; **STILL BUG-E-003 MUTATED**: composed plan status=`ready` with bridge `transaction:null` AND no COMPOSED_PLAN_INCOMPLETE_TX blocker (err_envelope normalizer missed this path) |
| E08 | **CLOSED → WALLET_CHAIN_MISMATCH** + clean freeform |
| E09 | t1 single-chain Arbitrum Morpho clean (real `0x7c574174…8B3Ed`); **EXPECTED_BLOCKED stays RETIRED** |
| E10 | STILL P0 BUG-E-001; **STILL E-004 t2 ("Executing the plan: Bridge … via deBridge")** |
| E11 | **CLOSED → WALLET_CHAIN_MISMATCH** + clean |
| E12 | t1 single-chain Polygon + STILL BUG-E-005 (MATIC ≈ $0.0897) |
| E13 | t1 single-chain + STILL BUG-E-005; **NEW E-004 t3 ("Bridge route: Ethereum → deBridge DLN → Polygon")** |
| E14 | t1 single-chain Avalanche + STILL BUG-E-005 (AVAX ≈ $9.08) |
| E15 | **CLOSED → WALLET_CHAIN_MISMATCH** t1; **STILL E-004 t3/t4 ("Bridge 0.1 WETH … via Across or Hop")** |

## P0 STILL (3)

- **BUG-E-001 parser drops cross-chain (10/15 chains, two patterns)**:
  - Pattern A: "via deBridge" → `protocol=debridge-dln, action=supply` → pool_link (E01, E02, E07, E10)
  - Pattern B: planner ignores `extra.source_chain` → dst-only ExecutionPlanV3 (E04, E05, E09, E12, E13, E14)
- **BUG-E-003 MUTATED on E07 t4** — same `transaction:null` BUT card now status=`ready`, bridge step `ready`, dst step `pending` with PENDING_DST_FILL, totals zeroed, **no blockers entry**. err_envelope normalizer (ADAPTER_QUOTE_REQUIRED/ADAPTER_BUILD_FAILED) did NOT intercept this code path — composed plan now claims signable while bridge tx is literally null.
- **BUG-E-004 freeform hallucinations EXPANDED**. Wave 1: 8/7. Wave 2: 6/5. **Wave 3: 11 turns / 8 chains** — canned-refusal gate catches naked-context turns but consistently fails when prior chat context names a bridge or LP target.

## P0 CLOSED (carried)

- BUG-E-002 senderAddress=guest holds CLOSED (E03/E08/E11/E15 emit WALLET_CHAIN_MISMATCH).

## P1 (4 STILL + 2 NEW = 6)

- BUG-E-005 STILL (MATIC $0.0897, AVAX $9.08 oracles wrong)
- BUG-E-007 STILL (subsumed by BUG-E-001)
- BUG-E-008 STILL (190.132 USDC mock leak)
- BUG-E-009 STILL (WALLET_CHAIN_MISMATCH used where WALLET_NOT_CONNECTED would be)
- **BUG-E-010 STILL → escalate to P0** (E06 t1 35+ lines of raw reasoning leak bytewise reproduces from wave 2; sanitizer never fires for allocation-distribute path)
- **NEW BUG-E-011 (P1)** — composed_plan err_envelope normalizer is silent on the BUG-E-003 path. Wrap `composed_plan.build_steps()` post-bridge-stitch, not the adapter call sites.
- **NEW BUG-E-012 (P1)** — canned-refusal gate over-fires on naked side. E01 t2/t3/t4 emit the SAME paragraph claiming "Please sign the transaction in your connected wallet; once signed the Execution Plan will move from draft to executed" — refusal itself becomes a hallucination (no plan exists).

## TOOL_TIMEOUT

Wave 1: 0. Wave 2: 7/4. **Wave 3: 2 turns / 2 chains** (E04 t1, E06 t3). Net improvement.

## EXPECTED_BLOCKED

- E09 stays RETIRED (Morpho vault `0x7c574174…8B3Ed` resolves to real ERC-4626 `0x6e553f65` deposit).
- E11 still legit-but-moot.

## Counts

| Metric | Wave 1 | Wave 2 | Wave 3 |
|---|---|---|---|
| Fully-working composed plans | 0 | 0 | **0** |
| WALLET_CHAIN_MISMATCH triggered | 0 | 4 | **4** |
| TOOL_TIMEOUT | 0 | 7/4 | **2/2** |
| Sentinel violations | 8/7 | 7/6 | **11/8** (REGRESSION) |
| EXPECTED_BLOCKED retired | — | 1 | **1** |
| P0 open | 4 | 3 | **3** |
| P1 open | 4 | 5 | **6** |

## Verdict

REGRESSION on sentinel violations (11/8 vs wave-2 7/6). BUG-E-001 parser unchanged (wave-3 fix wrong layer). BUG-E-003 mutated worse. Highest-impact next: BUG-E-001 parser + BUG-E-011 composed_plan post-stitch normalizer + BUG-E-004 stronger sentinel gate.
