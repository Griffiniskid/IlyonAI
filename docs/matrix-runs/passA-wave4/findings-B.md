# Matrix Pass A — Wave 4 — Category B findings

`SUMMARY: CLOSED=0 STILL=22 MUTATED=1 NEW=2 P0_REMAINING=10 P1_REMAINING=20`

## Priority checks

### B14 t4 — P0-B-NEW-01 (CoT scratchpad leak) — STILL OPEN
The fix did NOT close this. `final.content` ships 700+ chars of raw scratchpad: "Thus we need to decide weights. The user didn't specify weighting preference. Default to even split unless user explicitly asked for risk-weighted bias. … However the default even split would allocate across all 8 pools … I think it's acceptable. … We'll set … Now compute blended APY …"

Specifically `_STRATEGY_SCRATCHPAD_LEAD_RE` was supposed to cover "DEFAULT to" / "However we" / "We'll set" / "Probably we" — **every one of those appears verbatim**. Either regex isn't `re.I`, or chokepoint isn't wired into `emit_final`.

Fix: verify `_STRATEGY_SCRATCHPAD_LEAD_RE` is `re.I` and that `emit_final` actually calls `_strip_scratchpad(content)` before yielding `event: final`. Add unit test with this exact 705-char content.

### B09 t4 — P0-B-NEW-02 (executable:false cached pool → real signed tx) — MUTATED (worse)
Yearn/USDC/base in B09 t1 is `"executable":false`. B09 t4 step 2 emits full ERC-20 approval calldata. **MUTATED**: steps 1 + 5 now target hallucinated morpho-blue markets `ADPUSDC` + `CSYUSDC` (not in t1 opportunities) and ship byte-identical USDC approval calldata.

Fix: exec_plan builder must reject any `target` slug not in current-turn `defi_opportunities`.

## STILL (22 of 23)

P0: BSC WBETH BNB-price (B01/B02/B10/B15), `executable:false → blocker:null` (B02/B03/B04/B06/B11/B12/B13/B14), silent cross-chain substitution (B13/B08), duplicate calldata across distinct morpho markets (B09 + hallucinated slugs), hallucinated PT-USDC maturity (B10), hallucinated Pendle YT-USDe 30Jun2027 (B15), hyper-APY accepted (B03 286%, B06 168%, B11 203%, B12 215%, B13 101%, B14 41%), narrative recommends pool not in allocation (B11 100% WETH-KELLYCLAUDE @ 970%), plan/narrative N=N contradiction.

P1: 13 templated `verb:"Supply" asset:"USDC"` on non-USDC pools, requires_signature:false while plan ships steps, placeholder total_usd vs real-$ steps, hallucinated cross-turn registry, footer N=N self-contradiction, truncated tool-args display, sentinel false-flags audited protocols (Aave V3 ethereum tagged "Unaudited"), broken step indexing (B11 t4 steps 1,2,4,5 — 3 missing), canned stub data (B11 t3 hardcoded 12.00%/$250M), `blocker:null` vs `""` inconsistency, `combined_tvl:"$0"` despite per-position TVL > $0.

## NEW (2)

### N-B-W4-01 (P0) — Hallucinated morpho-blue market slugs ADPUSDC / CSYUSDC (B09 t4)
Step 1 + step 5 ship real signed approval calldata for slugs that were NEVER in t1 opportunities. Distinct from P0-B-05 (PT-USDC) because this is on the deterministic-adapter path with real calldata.
Fix: exec_plan builder must reject any `target` slug not in current-turn `defi_opportunities.items[*].symbol`.

### N-B-W4-02 (P1) — Sub-table override of allocation in final.content (B11 t4)
Narrative renders a SECOND allocation table after canonical one (100% WETH-KELLYCLAUDE @ 970%). Front-end will render two competing tables.
Fix: strip any markdown table after first `## Allocation` heading in `final.content`.

## Verdict
0/15 chains clean. Scratchpad-strip CHOKEPOINT verified NOT firing — highest-priority re-fix. Largest single-fix leverage: t4 reuse-prior-pools reducer (closes 4 P0s + 4 P1s).
