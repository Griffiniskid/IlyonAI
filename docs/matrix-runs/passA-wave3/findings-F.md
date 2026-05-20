# findings-F — matrix Pass A wave 3, category F (typed-recovery blockers)

**Scope**: 10 chains, 40 turns. **Baseline**: wave 2 (4 P0 + 6 P1 + 3 P2).
**Verdict**: **MAJOR PROGRESS** — 2 P0s CLOSED by err_envelope normalizer + 2 wave-2 regressions self-healed. 1 STILL P0, 5 STILL P1, 1 NEW P1.

## CLOSED (4)

- **P0-F-05** F09 t1 `quote_unavailable` → canonical `NULL_ROUTE`. Prose now: `**NULL_ROUTE**: I couldn't find a live USD price for XYZ.` err_envelope normalizer working.
- **P0-F-06** F10 t1 `aggregator_circuit_breaker` → `AGGREGATOR_CIRCUIT_BREAKER`. BONUS recovery copy: `Step failure kind=aggregator_circuit_breaker. Surfacing three user-explicit options. Hard rule: never auto-refund-swap-back.`
- **NEW-P0-F-01 wave 2 (F06 t1 timeout regression)** — SELF-HEALED. Wave 3 t1 returns full Curve Deposit LP plan in 6ms. Independent of fixes.
- **NEW-P2-F-01 wave 2 (F03 wallet-probe timeout)** — SELF-HEALED. Wave 3 multi-chain aggregation completes in 39s. Independent of fixes.

## STILL OPEN

### P0 (1)
- **P0-F-04** F04 t1 wrong typed code on EXPECTED_BLOCKED row. `pendle-mint PT-USDE` still routes to generic `UNSUPPORTED_ADAPTER` instead of `PENDING_EPOCH_ENTRY + NEEDS_FRONTEND_SDK`. Pendle intent detector still missing.

### P1 (5)
- **P1-F-02** wrong "Pool removed / paused / cap reached" recovery rationale leaks WIDER. Now in F01 t1, F04 t1, F07 t1, F08 t3. `enrich_blocker_with_recovery` uses pool-not-found template for every typed code lacking a bespoke enricher.
- **P1-F-03** Empty `affected_step_ids:[]` on every blocker (F01 t1, F03 t1, F04 t1, F07 t1, F08 t1, F08 t3).
- **P1-F-04** F10 t1 no card on AGGREGATOR_CIRCUIT_BREAKER. Typed code correct in prose but `card_ids:[]`. `build_swap_tx` err_envelope path bypasses card construction.
- **P1-F-05** F05 t3 allocation prose leaks template copy + adapter-readiness inconsistency.
- **P1-F-06** F09 t1 no card on NULL_ROUTE. Sibling of P1-F-04.

### P2 (2)
- **P2-F-01** F02 t4 balance_report dumped as raw JSON in content field.
- **P2-F-02** F06 t3 freeform swallows real Enso DNS error (no typed code).

## NEW (1)

- **NEW-P1-F-01** F08 t3 ADAPTER_BUILD_FAILED on AVAX native supply via Aave V3 gateway. Detail: `Aave V3 WrappedTokenGatewayV3 not registered on avalanche.` Real adapter coverage gap — registry missing avalanche entry. Likely 1-line registry fix.

## Cross-cutting

- **err_envelope sibling normalizer landed and works** — both simulate_swap + build_swap_tx lowercase codes now map to canonical UPPER_SNAKE.
- **Card construction at err_envelope boundary still missing** — prose-layer normalization alone; neither swap-side tool builds an ExecutionPlanV3 card. P1-F-04 + P1-F-06.
- **Recovery enricher dispatch missing** — only WALLET_CHAIN_MISMATCH ships bespoke enricher; every other typed code falls back to pool-not-found template.
- **Step-graph linkage to blockers absent** — `affected_step_ids:[]` everywhere.
- **Pendle intent detector still missing**.

## Counts

| Severity | Wave 2 | Closed | Still | NEW | Wave 3 total |
|----------|--------|--------|-------|-----|--------------|
| P0       | 4      | 2 + 1 self-heal | 1     | 0   | 1            |
| P1       | 6      | 0      | 5     | 1   | 6            |
| P2       | 3      | 1 self-heal | 2     | 0   | 2            |
| **All**  | **13** | **4**  | **8** | **1** | **9**     |

**Verdict**: MAJOR PROGRESS — best fix-wave-impact category. Down to 1 P0 (Pendle detector). Remaining 5 P1s all share root: err_envelope path missing card + recovery enricher dispatch.
