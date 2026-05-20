# findings-F — matrix Pass A wave 2, category F (typed-recovery blockers)

**Scope**: `docs/matrix-runs/passA-wave2/F01..F10/turn_*.txt` — 10 chains, 40 turns.
**Baseline**: `docs/matrix-runs/passA-wave1/findings-F.md` (5 P0 + 6 P1 + 2 P2).
**Verdict**: **MAJOR PROGRESS** — 2 of 5 P0s closed by the blocker normalizer; 3 P0s + 6 P1s persist; 1 NEW P0 regression on F06 t1; 1 NEW P2 on F03 wallet-probe timeouts.

## CLOSED (2)

- **P0-F-01** (F01 t1 `pool_not_found` → canonical `UNSUPPORTED_ADAPTER`). Normalizer worked. Recovery copy still wrong (P1-F-02) but typed code now in KNOWN_BLOCKER_CODES.
- **P0-F-02** (F02 t1 `unsupported_chain` → `WALLET_CHAIN_MISMATCH`). Normalizer worked + BONUS: card carries a fully-populated `recovery` object (`action:"ASK_USER"`, posture, 4 buttons, rationale). First F-row with a bespoke recovery payload.

## STILL OPEN

- **P0-F-03** (F06 timeouts) — t1 NOW timing out too (regressed); t4 still freeform fallback. No typed blocker / no card on timeout path.
- **P0-F-04** (F04 t1 wrong typed code on EXPECTED_BLOCKED row) — emits `UNSUPPORTED_ADAPTER` instead of expected `PENDING_EPOCH_ENTRY + NEEDS_FRONTEND_SDK`. Pendle-mint intent routes to generic "no DefiLlama match" path.
- **P0-F-05** (F09 `quote_unavailable` lowercase, no card) — `simulate_swap`'s `err_envelope` at `swap_simulate.py:150` never builds a card. The normalizer chokepoint is at `ExecutionPlanV3.add_blocker`; err_envelope path bypasses it entirely. **NEEDS A SIBLING CHOKEPOINT** at the err_envelope boundary.
- **P1-F-01..P1-F-06** all still open (empty affected_step_ids, recovery posture mismatch, F10 no card, F05 inconsistent allocation, F04 silent drop, err_envelope normalizer gap).
- **P2-F-01, P2-F-02** unchanged.

## NEW

- **NEW-P0-F-01 — F06 t1 regression: 7ms→45s timeout.** Wave 1 was ready in 7ms; wave 2 hits TOOL_TIMEOUT 45006ms with `chain:ethereum, protocol:curve, action:supply, asset_in:USDC, amount_in:100`. Curve/Enso adapter path now flakier than wave 1. **Independent of the 3 fix-wave changes.**
- **NEW-P2-F-01 — F03 t1/t2 wallet-balance probe timeouts (curl 90s).** Different turn-order from wave 1. Transport-layer hang on `get_wallet_balance`. Wallet stack unhealthy.

## Cross-cutting summary

**Normalizer chokepoint at `ExecutionPlanV3.add_blocker` works**: F01, F02 typed-code halves both CLOSED.
**Normalizer does NOT cover the err_envelope-only path**: `simulate_swap` (F09) + `build_swap_tx` (F10) return error envelopes directly to the agent loop — the agent surfaces the code in prose, no card constructed. **Sibling fix**: chokepoint at the err_envelope wrapper / observation handler that maps lowercase → canonical UPPER_SNAKE same as ExecutionPlanV3.add_blocker.

Recovery enrichment gap (`enrich_blocker_with_recovery` at the emitter) persists as predicted: BUG-F-02 / P1-F-02 wrong "Pool removed" rationale leaks into F01 t1, F04 t1, F07 t1 `detail` fields. F02 t1 alone got correct bespoke `recovery` payload because the `WALLET_CHAIN_MISMATCH` typed detector ships its own enrichment.

EXPECTED_BLOCKED rows: F04 t1 ships wrong typed code (Pendle-mint intent routes to generic "no DefiLlama match" branch); EXPECTED_BLOCKED gate only checks `status:blocked`, not typed-code semantic match.

## Counts

| Severity | Wave 1 | Closed | Still | NEW | Wave 2 total |
|----------|--------|--------|-------|-----|--------------|
| P0       | 5      | 2      | 3     | 1   | 4            |
| P1       | 6      | 0      | 6     | 0   | 6            |
| P2       | 2      | 0      | 2     | 1   | 3            |
| **All**  | **13** | **2**  | **11**| **2** | **13**     |

**Verdict**: FINDINGS — partial fix-wave success. Normalizer-at-plan-boundary works. err_envelope sibling chokepoint needed. F06 regression Curve/Enso flakiness independent of changes.
