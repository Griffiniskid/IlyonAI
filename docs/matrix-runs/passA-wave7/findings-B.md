# Matrix Pass A — Wave 7 — Category B findings

`SUMMARY: CLOSED=1 STILL=18 MUTATED=3 NEW=4 P0_REMAINING=8 P1_REMAINING=13`

## CLOSED (1)
- **B11 t4 sub-table override** + **B13 t4 empty 2nd `## Allocation`** — held.

## STILL (18)
### P0
- **B09 t4 ADPUSDC + CSYUSDC hallucinated morpho-blue slugs** — byte-identical USDC approval calldata.
- **B09 t4 Yearn USDC base approval despite executable:false** — chain_id 8453, real spender.
- **B01/B02/B10/B15 t1 BSC WBETH BNB-price** — 5× over-allocation.
- **B02/B03/B04/B12 t4 executable:false → blocker:null** — saturn/zeebu/curve-llamalend/camelot-v3/gmx-v2-perps.
- **B series hyper-APY t4** — B03 270%, B04 80%, B11 184%, B12 270%, B14 42%.
- **B12 t4 LRT_ONLY constraint silently dropped**.

### P1
- Templated Supply USDC on non-USDC pools.
- requires_signature:false while plan ships steps.
- Placeholder $1,000.
- Sentinel false-flags audited protocols.
- Broken step indexing.
- combined_tvl:$0 on B14.
- blocker:null vs "" inconsistency.
- **N-B-W6-02 B14 t4 SOL-price-resolution failure** + **N-B-W6-03 B11 t4 aerodrome dropped** + **N-B-W6-04 card/narrative contradiction**.

## MUTATED (3)
- **B13 silent cross-chain substitution** — worse: 5-position Solana alloc on hallucinated gmtrade FX pools (USDCHF-USDC 167.6%, USDCAD-USDC 105.8%, USDJPY-USDC 95.5%).
- **B15 t4 Pendle YT-USDe** — wave-7 broadened Pendle schedule regex but missed header-less single-paragraph form.
- **N-B-W6-05 B07 t4 zero-APY top-5** — 2 of 5 still zero-APY.

## NEW (4)
- **N-B-W7-01 (P0) B13 t4 gmtrade FX-pair pools treated as stablecoin lending** — 3/5 positions are FX-perp markets with `verb:"Supply" asset:"USDC"` exec steps. Constraint filter let forex pairs through.
- **N-B-W7-02 (P1) B06/B09/B12 90s curl timeouts** — 3 turns hit upstream timeout.
- **N-B-W7-03 (P1) B11 t4 tx_count:4 vs alloc:5 mismatch**.
- **N-B-W7-04 (P1) B01/B02/B10 t1 step 2 SUSDS blocker:"" while others null** — serialization inconsistency.

## Verdict
0/15 chains clean. Wave-7's broadened sanitizer didn't catch single-paragraph Pendle text-form. Slug-allowlist + BSC pricing + LRT_ONLY constraint reducer all untouched.
