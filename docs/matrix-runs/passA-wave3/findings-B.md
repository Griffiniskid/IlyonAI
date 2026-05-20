# findings-B — matrix Pass A wave 3, category B (strategy composition)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 2 (9 P0 + 14 P1; 0/15 clean).
**Wave 3 fix**: err_envelope normalizer (no expected impact on B).
**Verdict**: REGRESSION. **P0=11 (+2), P1=20 (+6), 0/15 clean.**

## CLOSED (0)

Nothing. Every wave-2 finding reproduces — as forecast.

## STILL-PRESENT (23, all carry-over)

### P0 (9/9)
- P0-B-01 BSC WBETH BNB-price (B01/B02/B10/B15 t1: $619/ETH on BSC vs $3,076/ETH mainnet)
- P0-B-02 `executable:false` → `blocker:null` (B02 t4, B03 t4, B04 t4, B06 t4, B11 t4, B12 t4, B13 t4 — broadened further)
- P0-B-03 silent cross-chain substitution (B08 t1 monad/hyperliquid; B13 t1 unitas/solana — "closest executable alternative substituted at execution time")
- P0-B-04 duplicate calldata across distinct morpho markets (B09 t4 steps 1 + 5 byte-identical)
- P0-B-05 hallucinated PT-USDC maturity (B10 t2/t3/t4)
- P0-B-06 hallucinated Pendle YT-USDe ladder (B15 t2/t3)
- P0-B-07 hyper-APY accepted (B03 286%, B06 314%, B11 218%, B12 369%, B13 104%)
- P0-B-08 narrative recommends pool not in allocation (B11 t4 inserts 2nd table assigning 100% to WETH-KELLYCLAUDE @ 952.8%; B12 t1 narrative invents LRT basket)
- P0-B-09 plan/narrative contradiction (B06 t4 + B13 t4 "5 of 5 cannot be signed" while card carries adapter_id; B11 t4 tx_count:5 + 5-pool alloc but exec_plan emits indices 1,4,5 only)

### P1 (13/13 + 1 wave-2 NEW carry-over)
- Templated `verb:"Supply" asset:"USDC"` for non-USDC pools
- `requires_signature:false` while exec_plan ships unblocked steps
- Placeholder `total_usd:"$1,000"` + real-$ steps
- Raw curl 90s timeout leaks (B03 t1)
- Silent cross-chain substitution latent
- Hallucinated cross-turn registry (B09/B10/B13/B15)
- P1-B-NEW-01 footer self-contradiction N=N

## NEW (8)

### P0 (2)

**P0-B-NEW-01 — Massive CoT scratchpad leak in final.content (B14 t4)**
60+ line internal monologue: `"We need to allocate only the pools listed in the data block. The user request: \"Execute the Jito leg\"… However we must follow the instruction… I think we should… We'll set… Now compute blended APY…"`. Same failure class wave-2 declared CLOSED (P0-B-03 50-line leak) reintroduced in worse form. err_envelope normalizer covers tool-error payloads only; leak is on the success path through allocate/exec_plan composition.

**P0-B-NEW-02 — Cached `executable:false` pool gets real signed tx (B09 t4 step 2)**
Yearn-finance/USDC/base flagged `executable:false, adapter_id:null` in turn-1 card. Turn-4 reuse-prior-pools branch emits step 2 with full ERC-20 approval calldata: `to=0x8335…2913 (base USDC), data=0x095ea7b3…be53a1…0bebc200, spender=0xbeef010f9cb27031ad51e3333f9af9c6b1228183`. Executable-false gate bypassed at exec-plan emission via cached stub.

### P1 (6)

- **P1-B-NEW-02** Truncated tool-args display in `thought`: B05 t1 ends `"stablecoin_."`; B07 t1 ends `"ranking_objective": "const."`.
- **P1-B-NEW-03** Sentinel false-flags audited protocols: B07 t3 every Aave V3 ethereum entry tagged "Unaudited" + "<180 days live"; B11 t3 Uniswap V3 USDC/WETH same.
- **P1-B-NEW-04** Broken step indexing: B11 t4 emits steps with `index:1, 4, 5` — 2 and 3 absent while tx_count:5 and alloc table 5 positions.
- **P1-B-NEW-05** Fake/canned stub data from find_liquidity_pool: B11 t3 Uniswap V3 USDC/WETH ethereum returns hard-coded `apy:"12.00%"` and `tvl:"$250,000,000"`.
- **P1-B-NEW-06** Inconsistent blocker `null` vs `""`: B01/B02/B10/B15 t1 alloc_step_2 + alloc_step_5 have `blocker:""`; other steps `blocker:null`.
- **P1-B-NEW-07** `combined_tvl:"$0"` despite per-position TVL > $0: B14 t4 alloc positions report $213K/$21K/$33K/$11K/$80K (sum ~$361K) yet combined_tvl is "$0".

## Cross-cutting root cause: t4 reuse-prior-pools branch

6 chains (B02/B03/B04/B06/B11/B12/B13) show the t4 "distribute across previously surfaced pools" reducer is the single largest concentration of regressions in B:
- replays cached `defi_opportunities` from prior turn
- synthesizes 5-position equal-weight allocation regardless of risk profile / asset class
- emits `verb:"Supply" asset:"USDC"` for every step
- sets `requires_signature:false` while shipping unblocked steps
- appends contradictory "N of N cannot be signed" footer
- blended_apy is naïve unweighted mean (yields 286%/314%/369% nonsense)
- never re-validates `executable:false` from cached card

**Highest-leverage fix in category B**: single fix in this reducer closes P0-B-02, P0-B-07, P0-B-08, P0-B-09 + 4 wave-2 P1s.

## Verdict

REGRESSION. Wave-3 normalizer had no effect on B (forecast confirmed). +2 P0, +6 P1, 0 closed, 0/15 clean. P0-B-NEW-01 (scratchpad leak) ships internal model reasoning to end-users; P0-B-NEW-02 (executable:false cached bypass) asks users to sign real spender grants for pools flagged un-routable seconds earlier.

**Counts**: P0=11 (+2), P1=20 (+6), CLOSED=0, STILL=23, chains clean=0/15.
