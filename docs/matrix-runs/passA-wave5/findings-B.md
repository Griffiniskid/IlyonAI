# Matrix Pass A — Wave 5 — Category B findings

`SUMMARY: CLOSED=1 STILL=21 MUTATED=2 NEW=3 P0_REMAINING=9 P1_REMAINING=18`

## CLOSED (1)

### P0-B-NEW-01 — B14 t4 CoT scratchpad leak
Body-scan worked. Final.content clean: canonical alloc table + one-line BNB-price ask + standard unsupported-adapter footer. Zero hits on wave-4 scratchpad phrases.

## STILL (21)

### P0 (8)
- **P0-B-NEW-02 B09 t4 hallucinated morpho-blue slugs** (ADPUSDC + CSYUSDC) ship byte-identical USDC approval calldata; neither slug in t1 opportunities.
- **B01/B02/B10/B15 BSC WBETH BNB-price** — t1 sizes 0.121-0.484 ETH at BSC chain for $75-$300 → 6× over-allocation if user signs (BSC-WBETH is BNB-priced, not ETH-priced).
- **B02/B03/B04/B11/B12/B13/B14 t4 executable:false → blocker:null** — every t4 ships steps for unsupported pools with `blocker:null`.
- **B13 silent cross-chain substitution** — Sanctum INF Solana leg silently swapped to gmtrade FX pools.
- **B09 duplicate calldata across distinct morpho markets** (ADPUSDC + CSYUSDC byte-identical approval).
- **B10 t4 hallucinated PT-USDC maturities** (Maple/Sky/Binance-Staked mapped to fake "30 Jun 2025"/"31 Dec 2025" etc.).
- **B15 t4 hallucinated Pendle YT-USDe 30Jun2027** with full 3-step plan + risk framing.
- **B series hyper-APY t4** (7/8 with cards have blended_apy > 50%: B03 286%, B06 150%, B11 184%, B12 215%, B13 102%).

### P1 (13)
- Templated `verb:"Supply" asset:"USDC"` on non-USDC pools (13 occurrences).
- `requires_signature:false` while plan ships 3-5 steps (9 t4 occurrences).
- Placeholder `total_usd:"$1,000"` (8/8 t4 cards).
- Sentinel false-flags audited protocols ("Unaudited" for Aave V3 / Sky / Maple / Rocket-pool).
- Broken step indexing — B02 t4 `[1,3,4,5]` (missing 2); B11 t4 `[1,2,4]` (missing 3,5); B01 t4 `[1,3,4,5]` (missing 2).
- `combined_tvl:"$0"` on B14 t4 despite positions summing to $360K (Solana adapter bug).
- `blocker:null` vs `""` inconsistency.
- N=N narrative contradiction (B11 t4 says "5 positions" then renders single 100% table).

## MUTATED (2)

### N-B-W4-02 (P1) — Sub-table override in narrative
B11 t4 now ships TWO `## Allocation` tables: canonical 5×20% blended 184.4% + second `100% uniswap-v4 ETH-PITCH @ 513.6%` (different pool than wave-4's WETH-KELLYCLAUDE).
Fix: body-scan must truncate everything after the first `## Allocation` markdown table, not just CoT lead-ins.

### N-B-W4-01 (P0) — Yearn USDC base ships real approval despite executable:false (B09 t4 step 2)
B09 t1 explicitly marks yearn-finance/base `executable:false`; t4 step 2 ships real USDC approve to Yearn V3 vault `0xbeef010f…`. Same defect class as ADPUSDC/CSYUSDC but on a slug that DOES exist in t1.

## NEW wave-5 (3)

### N-B-W5-01 (P1) — B12 LRT_ONLY constraint silently dropped
B12 test category is `B12_lrt_only`; t4 allocation returns 5 non-LRT pools (saturn / uniswap-v3 SERV-WETH / curve / zeebu / uniswap WETH-ASTEROID). No blocker, no warning.
Fix: reuse-prior-pools reducer must re-apply original constraint filter.

### N-B-W5-02 (P1) — B13 t4 empty `## Allocation` table emitted
After canonical table, narrative emits SECOND `## Allocation` heading with separator only and no rows, followed by empty `## Reasoning` / `## Blended outcome` / `## Next steps`. Front-end renders broken empty table.

### N-B-W5-03 (P0) — B09 t4 step 2 yearn approval despite executable:false (see N-B-W4-01 above; this is the specific calldata path).

## Verdict
1/15 chains clean (B14 scratchpad fixed). Body-scan worked for raw CoT but does NOT strip second-table override (B11/B13). Highest single-fix leverage: exec_plan builder gate on `executable:false` (closes 4 P0s + 3 P1s).
