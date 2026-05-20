# Matrix Pass A — Wave 7 — Category H findings

`SUMMARY: CLOSED=3 STILL=8 MUTATED=3 NEW=4 P0_REMAINING=6 P1_REMAINING=3`

## CLOSED (3)
- **NEW-W6-01 H02 t2/t3 freeform swap-leg fabrication** — chokepoint fires.
- **P0-H-03 H14 backticked Solidity verbs** — H14 t3 refusal (NOTE: pattern migrated to H08 — see NEW).
- **NEW-W6-02 H06 t2 partial-sanitizer cycle**.

## STILL (8)
### P0 (6)
- **P0-H-01 H09 "Top-up confirmed" + GAS_TOPUP table** — H09 t2 emits markdown table; H09 t3 emits literal `Top‑up confirmed.` (with U+2011 NON-BREAKING HYPHEN). Wave-7 Unicode-normalize pass either runs AFTER chokepoint regex OR doesn't canonicalize U+2011→`-` / U+202F→space. Sanitizer never fires.
- **P0-H-04 H12 claim+compound flow absent**.
- **P0-H-05 H11 NFT LP refinance composed plan missing** — `tokenId 12345` echoed but no composed plan.
- **P0-H-06 H15 WALLET_KIND_MISMATCH detector missing** — H15 t1/t3 build Aave V3 supply for Solana wallet user.
- **P0-H-08 H06 + H02 + H01 composed plan status=ready with transaction:null** — generalized to 3 card types: execution_plan_v3 (H06), execution_plan (H01), pool_deposit_v3→execution_plan_v3 chain (H03).

### P1 (3)
- **P1-H-03 H04 + H09 deBridge misrouted as pool_link**.
- **P1-H-04 intent parser FP residue / APY band inverted** — H11 t1 `min_apy:0.5, max_apy:0.48`.
- **NEW-03 H08 mixed-chain spender leak + bare 40-hex** — H08 t2 leaks Base USDC token + **Ethereum-mainnet** Aave V3 Pool spender (wrong chain) + literal `**Calldata:** approve(address spender, uint256 amount)` template. 0 tool calls.

## MUTATED (3)
- **MUTATED-N01 NEW-01 chain-name-as-asset** — H08 t1 STILL parses `asset_in:"BASE"`. H13 fixed at parse time but H08 still broken — parser branches on protocol field.
- **MUTATED-N02 composed-plan transaction:null** — confirmed on 3 card types (one bug, three surfaces).
- **MUTATED-N03 (RE-OPEN) P1-H-02 JLP composition hallucination** — wave-6 marked CLOSED; wave-7 H05 t2 re-emits full markdown table with `USDC ~50%, USDT ~20%, SOL ~15%, ETH ~10%`. Brittle wave-6 closure.

## NEW (4)
- **NEW-W7-01 (P0) `build_yield_execution_plan` 45s TOOL_TIMEOUT race** — H07 t1, H08 t4, H13 t1 all hit timeout AFTER observation reports `ok:true`. 3/15 scenarios.
- **NEW-W7-02 (P0) H08 t2/t3 freeform Aave-V3 supply calldata recipe** — direct successor to P0-H-03 (migrated H14→H08). Headers `**Supply 50 USDC on Aave V3 (Base)** – approve already done`, `**Confirm partial approve top‑up**` precede 40-hex addresses + Solidity template. Chokepoint missed: U+202F/U+2011 Unicode + new header shapes.
- **NEW-W7-03 (P1) APY rendering bug — small APYs divided by 100** — H14 t1 `apy:0.36103` (=36.1%) rendered as `APY 0.4%`. Inconsistent unit-coercion between fraction-form and percent-form upstreams.
- **NEW-W7-04 (P0) H15 t2 `usd_value:4.99e+30` for spark token + spam-token dust list** — same USD overflow as F02 t3.

## Verdict
Wave-7 sanitizer broadening landed for H02 (Swap leg / Split confirmed) and H14 (backticked Solidity). Three closures. But Unicode normalize did NOT actually run on freeform body OR didn't include U+2011 (non-breaking hyphen) — P0-H-01 + NEW-W7-02 both blocked on this.

Composed-plan downgrade rule still unshipped; now confirmed on 3 card types. JLP composition closure was brittle, re-fired.

Wave-8 must:
1. Unicode-fold sanitizer input BEFORE regex match (add U+2011/U+2013/U+2014 to normalize set).
2. Ship composed-plan downgrade rule (`transaction:null AND status != "blocked"` → force `status:"blocked"`).
3. Extend chokepoint with `**Supply N TOKEN on PROTOCOL`, `**Confirm partial approve`, `**Calldata:**`, `approve(address, uint256)`, bare 40-hex.
4. Re-close JLP composition.
5. Trace H08 parser regression.
6. Fix APY fraction-vs-percent renderer.
7. Cap usd_value + spam-token filter.
8. Investigate `build_yield_execution_plan` 45s SLO race (ok:true + TOOL_TIMEOUT failure mode).
