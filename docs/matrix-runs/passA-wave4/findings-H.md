# Matrix Pass A — Wave 4 — Category H findings

`SUMMARY: CLOSED=3 STILL=10 MUTATED=2 NEW=3 P0_REMAINING=8 P1_REMAINING=8`

## CLOSED (3)

- **P0-H-NEW-01 H02 t4 cardinal** — t4 specific instance closes via sentinel-gate refusal. **But MUTATED to t2** (see below).
- **P0-H-02 H10 t2 Lido wrong-selector calldata** — refuses cleanly with 0 tool calls; no `0x2e1a7d4d` hallucination.
- **P1-H-06 prose "Please connect EVM wallet" on H05 t1** — now emits proper `execution_plan_v3 status:blocked + WALLET_CHAIN_MISMATCH`. (Still leaks in H05 t3 freeform prose.)

## MUTATED (2)

### MUTATED-01 — H02 cardinal hallucinated tx hash MOVED t4 → t2 (P0)
**H02 t2**: `"Current tx: 0x3a9f…c1e2 (Base) – Pending (~12 s confirmation)"` — same fabricated hash. Turn has 3 thought events, ZERO tool events, `card_ids:[]`. Sentinel-gate refusal fires on t4 (3 thoughts + 0 tool calls) but NOT on t2.
Fix: `StreamCollector.emit_final` pre-emit content scanner — when `tool_count==0` and no signable card, regex-block `0x[0-9a-fA-F]{4,}…[0-9a-fA-F]{4,}`, `Pending`, `confirmed`, `submitted`, `Top-up`. Current widened `_STRATEGY_SCRATCHPAD_LEAD_RE` only handles lead-strings.

### MUTATED-02 — H15 wallet-balance infra RE-OPENED (P0)
Wave 3 CLOSED. Wave 4: t1 TOOL_TIMEOUT 45s; t2 90s curl timeout 601 bytes; t3 90s 0 bytes; t4 `rate_limited`.
Fix: `get_wallet_balance` upstream + SSE flush bug; verify 45s/90s SLO guards.

## STILL (10)

### P0 (6)
- **P0-H-01** H09 GAS_TOPUP_REQUIRED detector absent — freeform table top-up plan with 0 tool calls + fabricated "~0.001 ETH (~$2)".
- **P0-H-03** H14 V2→V3 migration not bundled — freeform names Solidity functions in inline code without tool backing.
- **P0-H-04** H12 claim+compound flow absent.
- **P0-H-05** H11 NFT LP refinance composed plan missing — punts to Uniswap UI.
- **P0-H-06** H15 WALLET_KIND_MISMATCH detector missing (Solana wallet user calling EVM build).
- **P0-H-08** H06 cross-chain composed plan `status:"ready"` with `transaction:null` — same root as BUG-E-003.

### P1 (4)
- **P1-H-01** H07 dust-mixing untested (Curve t1+t4 TOOL_TIMEOUT 45s).
- **P1-H-02** H05 t2 JLP composition hallucination "SOL ≈ 45%, ETH ≈ 20%…".
- **P1-H-03** H04 deBridge bridge misrouted as `pool_link` titled "Debridge-Dln · Supply".
- **P1-H-04** intent-parser strips chain/wallet hints; APY band inverted (min>max); FP residue `0.08000000000000002`.

### EXPECTED_BLOCKED carry-overs
- H07_S7 dust_mixing not blocked (build times out).
- H08_S8 partial_allowance not blocked (parser regression — see NEW-01).

## NEW (3)

### NEW-01 (P0) — H08/H13 parser REGRESSION: chain-name-as-asset re-opened
H08 t1, H13 t1/t2 all parse `Supply 100 USDC to Aave V3 on Base` as `asset_in:"BASE", chain:"base"` → `ADAPTER_BUILD_FAILED: no token metadata for BASE on base`. Wave-3 fix has come undone.
Fix: re-apply wave-3 parser fix + add unit test pinning the regression.

### NEW-02 (P1) — H07/H13 Curve/Aave build latency regression
H07 t1+t4, H13 t4, H15 t1, H15 t2 90s, t3 90s. Wave-3 had single-turn 45s outliers; wave-4 multi-turn on canonical happy-path adapters.
Fix: profile `build_yield_execution_plan` for Curve eth + Aave base USDC paths.

### NEW-03 (P1) — H08 t3 wrong-chain Aave spender leak via freeform
Token `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` (Base USDC) paired with spender `0x794a61358D6845594F94dc1DB02A252b5b4814aD` (Ethereum Aave Pool). Mixed-chain calldata in freeform; 0 tool calls.
Fix: extend chokepoint to block any `0x[0-9a-fA-F]{40}` address pattern in freeform finals with 0 tool calls when prior turn referenced different chain.

## Verdict
Wave-4 chokepoint scratchpad-strip CLOSED H02 t4 narrowly but defect MUTATED to t2 with identical hash. Regex anchors lead, doesn't body-scan tx-hash patterns. H15 infra fully regressed. Parser regression re-opened on H08/H13. §7 detectors (S6/S9/S10/S11/S12/S14/S15) completely unchanged.

Wave-5 absolute priorities:
1. Body-scan chokepoint for tx-hash patterns + "approve(..." templates.
2. Restore H15 wallet-balance infra.
3. Re-pin parser fix.
4. §7 detector blitz for S6/S9/S10/S11/S12/S14/S15.
