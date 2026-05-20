# Matrix Pass A — Wave 6 — Category B findings

`SUMMARY: CLOSED=4 STILL=15 MUTATED=2 NEW=5 P0_REMAINING=9 P1_REMAINING=12`

## CLOSED (4)
- **N-B-W4-02 B11 t4 sub-table override** "100% ETH-PITCH @ 513.6%" — `_SECOND_ALLOCATION_HEADING_RE` truncation worked.
- **N-B-W5-02 B13 t4 empty 2nd `## Allocation` heading** — same fix.
- **B10 t4 hallucinated PT-USDC maturities** — now contextual fallback refusal.
- **B11 N=N narrative contradiction** — single 5-row table matches narrative.

## STILL (15)

### P0
- **B09 ADPUSDC + CSYUSDC hallucinated morpho-blue slugs** — byte-identical USDC approval calldata shipped.
- **B01/B02/B10/B15 BSC WBETH BNB-price** — 4 chains, 5× over-allocation on signature.
- **B02/B03/B04/B06/B11/B12/B13/B14 t4 executable:false → blocker:null** — saturn/zeebu/curve-llamalend/camelot-v3/etc. all ship steps with null blocker.
- **B09 duplicate calldata across distinct morpho markets**.
- **B series hyper-APY t4** — B03 270%, B04 80%, B06 174%, B11 200%, B12 270%, B14 42%.
- **N-B-W4-01 / N-B-W5-03 B09 t4 step 2 Yearn USDC base real approval despite executable:false**.

### P1
- Templated `verb:"Supply" asset:"USDC"` on non-USDC pools.
- `requires_signature:false` while plan ships 4-5 steps.
- Placeholder `total_usd:"$1,000"`.
- Sentinel false-flags audited protocols.
- Broken step indexing.
- `combined_tvl:"$0"` on B14 t4.
- `blocker:null` vs `""` inconsistency.
- **N-B-W5-01 B12 LRT_ONLY constraint silently dropped**.

## MUTATED (2)
- **B13 silent cross-chain substitution** — now surfaced to user but exec_plan still ships unsupported steps.
- **B15 t4 Pendle YT-USDe 30Jun2027** — cards eliminated, hallucination moved to plain markdown narrative text (bypasses card sanitizer).

## NEW (5)
- **N-B-W6-01 (P0) B15 t4 Pendle YT-USDe narrative hallucination** — text-form `**Execution Plan – Buy YT‑USDe 30Jun2027**` with 3 numbered steps.
- **N-B-W6-02 (P1) B14 t4 SOL-price-resolution failure** — narrative asks for SOL price but card has $1,000 placeholder.
- **N-B-W6-03 (P1) B11 t4 aerodrome-slipstream dropped from exec_plan** — pool has `executable:true` but step index 3 missing.
- **N-B-W6-04 (P1) Card/narrative contradiction B06/B12/B13 t4** — card shows 5-position plan, narrative says "I'm unable".
- **N-B-W6-05 (P1) B07 t4 zero-APY pools ranked top-5**.

## Verdict
0/15 chains clean. Body-scan second-heading worked but slug-allowlist + BSC pricing + LRT_ONLY constraint reducer all untouched. Highest single-fix leverage: exec_plan builder slug-allowlist + executable:false gate (closes 5+ P0).
