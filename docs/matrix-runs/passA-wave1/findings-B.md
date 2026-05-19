# findings-B — matrix Pass A wave 1, category B (strategy composition)

**Scope**: `docs/matrix-runs/passA-wave1/B01..B15/turn_*.txt` — 15 chains × 4 turns = 60 transcripts.
**Verdict**: FINDINGS. **0/15 chains clean.** 11 P0 + 17 P1.

## Per-cluster root causes (Wave-2 fix priority)

| Cluster | Affected chains | Severity | Hypothesis |
|---|---|---|---|
| BSC WBETH stake uses BNB price | B01, B02, B10, B15 t1 | P0 | Price oracle keyed on chain's gas token instead of asset |
| `verb:"Supply" asset:"USDC"` for every pool | B03, B04, B06, B11, B12, B13, B14 t4 | P1 | Plan template doesn't read pool.product_type |
| `executable:false` → plan step with `blocker:null` | B04, B06, B09, B12 t4 | P0 | Plan builder ignores opportunity executable flag |
| Sanitizer leak of chain-of-thought | B06, B11, B14 t4 | P0 | LLM scratchpad concatenated into final.content |
| Hallucinated pool/contract names | B09, B10, B11, B12, B15 | P0 | Freeform fallback invents product metadata; same fake registry reused across turns |
| `requires_signature:false` with active plan steps | B03, B04, B06, B11, B12, B13, B14 | P1 | Plan-card flag decoupled from per-step blocker |
| Raw curl/TOOL_TIMEOUT leak | B02 t2, B08 t2 | P1 | Freeform fallback lacks SSE timeout handling |
| Silent cross-chain substitution (mantle→mainnet) | B07 t3 | P0 | "substitute at execution time" rewrites chain without surfacing |
| Placeholder `total_usd:"$1,000"` with real-$ plan steps | B03, B04, B06, B11, B12, B13 t4 | P1 | Plan emits with placeholder dollars rather than refuse |

## P0 findings (11)

### P0-B-01 — BSC WBETH staking uses BNB price (~$619) instead of ETH price
- **Chains**: B01 t1, B02 t1, B10 t1, B15 t1.
- **Math**: 0.242 ETH for $150 → $619/ETH (BNB price). Same step on ETH mainnet: 0.065 ETH for $200 → $3,076/ETH (correct).
- **Spec**: amount-derivation correctness.

### P0-B-02 — `executable:false` adapter passes through to signed plan step with `blocker:null`
- **Chains**: B04 t4 (gmx-v2-perps), B06 t4 (pharaoh-v3), B09 t4 (yearn-finance/base), B12 t4 (zeebu).
- **Quote (B04)**: defi_opportunities item `"executable":false,"unsupported_reason":"gmx-v2-perps on arbitrum: Direct execution disabled for this pool type."` → plan step 5 `{"verb":"Supply","amount":"200","asset":"USDC","target":"WBTC.B-USDC · gmx-v2-perps","blocker":null}`.
- **Spec ref**: unsupported items MUST surface a blocker.
- **Root cause**: plan builder does not consult `opportunities.items[i].executable`/`unsupported_reason`.

### P0-B-03 — Massive sanitizer leak (~50 lines of internal reasoning in final.content)
- **Chains**: B06 t4, B11 t4, B14 t4 (worst).
- **Quote (B06)**: `"We need to follow the instruction: \"Previously surfaced pools (use ONLY these; the user said 'those pools')\". The user request: \"Execute the Lido leg\". We need to allocate across the same pools surfaced in prior turn — do NOT search for new pools…"`
- **Root cause**: when LLM reply exceeds soft limit the sanitizer concatenates raw scratchpad onto user-facing content.

### P0-B-04 — Silent cross-chain substitution (mantle→mainnet) with no disclosure
- **Chain**: B07 t3.
- **Quote**: allocation rank 2 `{"protocol":"aave-v3","asset":"WETH","chain":"mainnet"…}` while defi card had same asset on `chain:"mantle"` with `unsupported_reason:"No direct adapter for aave-v3 on mantle; closest executable alternative will be substituted at execution time."`
- **Root cause**: "substitute at execution time" rewrites chain silently without surfacing in any card. User signs on wrong chain.

### P0-B-05 — Calldata reused across distinct morpho-blue markets (ADPUSDC vs CSYUSDC)
- **Chain**: B09 t4.
- **Quote step 1 (ADPUSDC) + step 5 (CSYUSDC)**: identical `to:"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"`, `data:"0x095ea7b3000000000000000000000000be53a109b494e5c9f97b9cd39fe969be68bf6204000000000000000000000000000000000000000000000000000000000bebc200"`, `spender:"0xbe53a109b494e5c9f97b9cd39fe969be68bf6204"`.
- Both "markets" approve same 200 USDC to same spender. Pool symbols `ADPUSDC` and `CSYUSDC` do not appear in any defi_opportunities → likely hallucinated market names too.

### P0-B-06 — Hallucinated PT-USDC maturity dates in chain with zero Pendle positions
- **Chain**: B10 t2, t3.
- **Quote**: `"All five PT-USDC tokens in the $1,000 strategy mature on 31 Dec 2025."`
- Reality: turn 1 allocation has NO Pendle PT tokens. Date already past (today 2026-05-20).

### P0-B-07 — Narrative recommends pool not in allocation
- **Chain**: B11 t4.
- **Quote final**: `"the full amount is placed in the pool with the greatest advertised APY (WETH-KELLYCLAUDE at 884.4%)… Sign the transaction for the Uniswap V4 WETH-KELLYCLAUDE pool"` while allocation card lists 5 different pools at 20% each.

### P0-B-08 — Cross-turn hallucinated pool registry (ADPUSDC / ETH-UPEG / ETH-ASTEROID)
- **Chains**: B09 t4, B12 t2/t3.
- **Quote (B12 t2)**: `"available pools (ADPUSDC, RAVE-USDT, ETH-ASTEROID, SERV-WETH, IDAI-IUSDC-IUSDT, ETH-UPEG, ZBU, WBTC-WETH)"`
- None of "ADPUSDC", "ETH-UPEG", "ETH-ASTEROID" exist in upstream defi_opportunities; the same fabricated set is echoed across turns → freeform fallback memorizing a hallucinated registry.

### P0-B-09 — Sanitizer leak ~70 lines (worse than B06)
- **Chain**: B14 t4.
- Narrative says "100% to SOL-JTO"; allocation card lists 5 different Kamino pools at 20% each. Plan/narrative mismatch.

### P0-B-10 — Hallucinated Pendle YT-USDe contract ladder with invented yields
- **Chain**: B15 t2, t3.
- **Quote**: markdown table of YT-USDe contracts with maturities 30 Jun 2025/26/27 and "4-6%, 5-7%, 6-8%" implied yields, no tool call. 30 Jun 2025 already expired.

### P0-B-11 — Bull strategy returns 828% APY hyper-yields (band 0.0, 10000.0 admits)
- **Chain**: B03 t1, t4.
- **Quote**: blended APY claim `~361.3%`. Real yields don't hit 800%. Either sanitizer doesn't refuse implausible APYs or upstream data feed is corrupt.

## P1 findings (17)

(Full list — see body of findings-B.md notes; condensed here)
- **P1-B-01** B02 t2 raw `curl: (28) Operation timed out after 90001ms` leaked into transcript.
- **P1-B-02** B03 t4 `verb:"Supply" asset:"USDC"` for every pool regardless of pool product_type (Uniswap-v3/v4 + Curve + Zeebu all labeled as "Supply USDC").
- **P1-B-03** B03 t4 `requires_signature:false` while plan has 5 unblocked steps.
- **P1-B-04** B07 t1 APY band float-precision leak `(2.0999999999999996, 4.800000000000001)`.
- **P1-B-05** B07 t3 `final.content` truncated mid-table; no execution_plan or sentinel_matrix card.
- **P1-B-06** B08 all turns: multi-turn search-only chain never emits allocation/execution_plan; t2 curl timeout.
- **P1-B-07** B09 t4 plan `elapsed_ms:2, steps:2` while producing 5-step calldata — cached-stub replay bypassing adapter regen.
- **P1-B-08** B05 t1 "stable+low" search 0 matches but no `no_match` blocker, only soft hint.
- **P1-B-09** B05 t4 freeform fallback gives wallet-signing instructions for Aave V3 Polygon USDC (deterministic adapter exists).
- **P1-B-10** B11 t4 execution plan skips index 3 (steps: 1, 2, 4) for 5-position allocation.
- **P1-B-11** B11 t2 "WETH-KELLYCLAUDE" pool at 884% APY surfaced as ready-via-deterministic and recommended — no blacklist on adversarial pool names at APY >500%.
- **P1-B-12** B12 t1 hallucinated "balancer-v2 WBTC-WETH | 6474.3% | $1.70M" in narrative — not in defi_opportunities.
- **P1-B-13** B13 t4 execution_plan step for raydium-amm with empty token symbol (`target:"-USDC · raydium-amm"`).
- **P1-B-14** B14 t4 `combined_tvl:"$0"` while underlying pools have positive TVL (215k/21k/33k/12k/79k).
- **P1-B-15** Plan `total_usd:"$1,000"` placeholder while emitting real $-sized steps (multiple chains).
- **P1-B-16** Plan-card `requires_signature` flag decoupled from per-step blocker calc (multiple chains).
- **P1-B-17** Sanitizer leak of broken upstream symbols / float-precision values into card payloads (multiple).

## Summary
- Chains reviewed: 15
- Total turns: 60
- P0: 11
- P1: 17
- 0/15 clean
- Verdict: **FINDINGS** — most catastrophic category so far. 4 cross-cluster root causes drive 9 of 11 P0s.
