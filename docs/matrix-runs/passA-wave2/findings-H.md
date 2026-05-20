# findings-H — matrix Pass A wave 2, category H (§7 funding scenarios)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 1 (8 P0 + 7 P1; 12/15 §7 detectors missing).
**Verdict**: FINDINGS — most §7 detector gaps persist; M01/M02/normalizer cleared 1 P0 + 1 P1; 2 NEW P1s + intent-parser regression.
**Counts**: P0 STILL=7, CLOSED=1, NEW=0 · P1 STILL=5, CLOSED=1, PARTIAL=1, NEW=2.

## CLOSED (2)

- **P0-H-07** (post-deterministic-timeout cascade hallucinations) — wave 1's dominant pattern (14+ turns hallucinating calldata/gas/fees after a timeout) substantially curtailed across H02/H06/H08/H12/H13. All now refuse with "I can't confirm that action without a deterministic Sentinel tool producing the calldata." BUG-M01 freeform-refuse plumbing confirmed LIVE.
- **P1-H-05** `guest` leak to deBridge → CLOSED. H05 t1 now emits clean `blocked` execution_plan_v3 with `WALLET_CHAIN_MISMATCH` blocker (BUG-E-002 guest-guard working here too).

## STILL (7 P0, 5 P1)

- **P0-H-01** (H09) GAS_TOPUP_REQUIRED detector missing; deBridge misrouted; t2 still hallucinates "$2.10 total gas top-up" prose
- **P0-H-02** (H10) LST→LP intent + prep_swap absent; t2 hallucinates Lido calldata with WRONG selector `0x2e1a7d4d` (real is `requestWithdrawals` on unstETH NFT)
- **P0-H-03** (H14) V2→V3 migration not atomically bundled
- **P0-H-04** (H12) claim+compound flow absent
- **P0-H-05** (H11) NFT LP refinance composed plan missing (all turns prose-only)
- **P0-H-06** (H15) wallet-kind mismatch detector absent (sub-claims unverifiable due to H15 infra collapse)
- **P0-H-08** (H06) cross-chain composed plan still emits unsigned `transaction:null` with `status:"ready"`
- **P1-H-01..04, P1-H-06** all STILL
- **P1-H-07** latency tail — WORSE (wave 1: 41s/40.3s; wave 2: H02 t1 45.07s TOOL_TIMEOUT, H08 t4 45.01s, H13 t4 45.01s, H15 t1 45.01s, H15 t2/t3 90s curl timeout, H10 t3 53.7s)

## NEW (2 P1)

- **P1-H-NEW-01** Intent parser confuses chain name "Base" with asset symbol. Verbatim "Supply 100 to Aave V3 on Base" → `asset_in:"BASE", chain:"base"` → ADAPTER_BUILD_FAILED. **Caused H13 to regress from PASS-SLOW to BLOCKED.**
- **P1-H-NEW-02** H15 wholesale infrastructure collapse (t1 deterministic 45s TOOL_TIMEOUT, t2/t3 SSE never emits a single event line — 90s curl timeout with 0–601 bytes, t4 `{"error":"rate_limited"}`). User would see nothing in chat.

## EXPECTED_BLOCKED

| Test | Wave 1 actual | Wave 2 actual |
|------|---------------|---------------|
| H07_S7 dust_mixing | NOT BLOCKED (Curve 3pool 4-sig built) | **NOT BLOCKED** but different intent fired (single Supply 50 USDC to Curve, 1 sig). Dust-mixing scenario simply not tested. MISMATCH stands. |
| H08_S8 partial_allowance | BLOCKED — confirmed | BLOCKED on different code path (intent-parse bug — `BASE` token). Partial-allowance still untested. |

## Verdict

**FINDINGS** — §7 implementation remains mostly absent or misrouted. M01/M02 fixes are real and partial-win for cross-cutting cascades and blocker shape, but per-scenario detectors (S9 gas top-up, S10 LST→LP, S11 NFT refinance, S12 claim+compound, S14 V2→V3, S15 wrong-wallet, S6 transaction:null) all require dedicated work and were not within scope of M01/M02/blocker normalizer.

The NEW intent-parser regression (chain-name-as-asset) is a notable regression — caused H13 to regress from passing to blocked. Should be fixed before next wave to recover that baseline.
