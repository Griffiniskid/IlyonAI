# Matrix Pass A — Wave 5 — Category E findings

`SUMMARY: CLOSED=3 STILL=6 MUTATED=2 NEW=1 P0_REMAINING=5 P1_REMAINING=4`

## CLOSED (3)
- **BUG-E-001 Pattern B** — E03/E08/E11/E15 t1 all parse `extra.source_chain` and emit structured WALLET_CHAIN_MISMATCH blocker; composed-plan stitch returns in ≤2s (no 45s SLO regression observed).
- **BUG-E-002 deBridge guest-guard** — holds.
- **BUG-E-013 fabricated submitted-tx (E10 t2)** — now returns canonical refusal. `_FREEFORM_TX_STATE_HALLUCINATION_RE` working on `submitted|broadcast|track its progress on BaseScan`.

## STILL (6)

### BUG-E-001 Pattern A (P0)
6 turns still produce `pool_link` linking to DefiLlama: E01 t1, E02 t1, E07 t1, E07 t2, E10 t1, E10 t4 (variant with `protocol:"weth9-wrap"`).

### BUG-E-003 composed plan status=ready with bridge transaction=null (P0)
E07 t4 final card: `status:"ready", blockers:[], steps:[{action:"bridge", status:"ready", transaction:null}, {action:"deposit_lp", status:"pending", blocker_codes:["PENDING_DST_FILL"], transaction:null}]`. Wave-3 NEW post-stitch normalizer never landed.
Fix: in `composed_plan.finalize`, if any step `status=="ready" ∧ transaction is None`, demote plan to `blocked` + inject `COMPOSED_PLAN_INCOMPLETE_TX`.

### BUG-E-008 mock balance constant 190.132 USDC (P1)
E05 t1/t3, E14 t1/t4 — same hard-coded balance across two chains.

### BUG-E-009 WALLET_CHAIN_MISMATCH vs WALLET_NOT_CONNECTED semantic (P1)
Every Pattern-B blocker uses `code:"WALLET_CHAIN_MISMATCH"` with `title:"Wallet not connected"` — semantically mismatched.

### BUG-E-014 stale card re-emit on resume (P1, MASSIVELY EXPANDED)
8 of 15 chains hit this in t4: E03/E04/E05/E06/E09/E12/E13/E14. `elapsed_ms:0, steps:2` confirms zero preflight rerun. Wave-4 noted 2 chains; wave-5 has 8 — REGRESSION.

### BUG-E-015 junk-token Uniswap V4 pools executable:true (P1)
E08 t2 / E15 t2: `WETH-GITLAWB` + `ETH-POD` (132-158% APY); E14 t3 `KIMBO-COQ-TECH-NOCHILL-WAVAX-USDC-GEC` (7-token degen pool, $11k TVL).

## MUTATED (2)

### BUG-E-004 freeform sentinel hallucinations (P0, partial mitigation)
Sanitizer closed ~5/11: E02 t2/t4, E05 t3, E10 t2, E15 t3 now refuse. Remaining (~7 P0 turns):
- E02 t3: `"slippage band for the Arbitrum Gateway bridge is 0.5%… approve and sign"` — fabricated slippage + plan promise.
- E03 t2: 4-step LI.FI how-to.
- E03 t3: `"I'll generate the exact LI.FI bridge transaction"`.
- E04 t2: `"deBridge DLN is the bridge used to move USDT"`.
- E05 t2: fabricated bridge fees `"Protocol fee: ~0.10% ≈ 0.20 USDC"`.
- E08 t3: `"Once connected, I'll generate a signable plan to: 1. Bridge… 2. Deposit"`.
- E11 t3: `"I'll generate the signed bridge + deposit plan"`.
- E13 t3: `"Bridge route: Ethereum → deBridge DLN → Polygon (DAI, 100 DAI)"`.

Sanitizer regex misses: `slippage band|bridge fee|protocol fee|generate (a|the) (signable )?plan|I'?ll generate|Bridge route:|how-to step lists with "Connect wallet"+"Bridge via"+"Approve"+"Supply"`.

### BUG-E-010 raw CoT leak in final.content (P0, regex insufficient)
E06 t1 STILL leaks: final.content begins with properly-formatted markdown allocation table + "Total $150 across 5 positions — blended APY ~80.3%", THEN appends 50+ lines of scratchpad: `"We need to allocate $150 across the same pools listed (7 pools)…"` ending with `"Now compute blended APY: weighted average = sum(APY)/7"`. Body-scan regex strips lead/trail but not prose-after-structured-block.
Fix: extend `_BODY_SCRATCHPAD_STRONG_RE` to truncate at first first-person scratchpad marker (`We need to|We'll |Let's |The user request|Now compute|I'll choose`) AFTER markdown table/list closes.

## NEW wave-5 (1)

### BUG-E-017 (P0) — Pattern A variant: source_chain DROPPED → single-chain supply on dst
- E04 t1: ETH → OPT USDT → parses `{"chain":"optimism","protocol":"aave-v3"}` NO `extra.source_chain` → Aave V3 Supply Optimism only.
- E12 t1: ETH → POL USDT → same pattern.
- E13 t1: ETH → POL DAI → same.
- E14 t1: ETH → AVAX USDC → same.

Parser inconsistency is `aave-v3`-protocol-specific (correlates with destination chain having native aave-v3). Financial-loss risk: user expects bridge+supply, gets supply-only plan.

Fix: same `"X via Y from Z to W"` lexeme detector as wave-4 BUG-E-001 must run BEFORE protocol-fastpath.

## Highest-impact wave-6 moves
1. Broaden `_FREEFORM_TX_STATE_HALLUCINATION_RE` to catch `slippage band|bridge fee|protocol fee|gas estimate|generate (a|the) (signable )?plan|I'?ll generate|Bridge route:|^\d+\.\s+(Connect|Bridge|Approve|Supply|Deposit)` → kills 7 P0 leaks.
2. Extend `_BODY_SCRATCHPAD_STRONG_RE` to truncate at first first-person scratchpad line AFTER a markdown structural block → kills BUG-E-010.
3. Planner-front lexeme parser must stamp `extra.source_chain` BEFORE protocol-fastpath → kills NEW BUG-E-017 + original BUG-E-001 Pattern A.
4. `COMPOSED_PLAN_INCOMPLETE_TX` post-stitch normalizer → kills BUG-E-003.
5. Session-resume path re-run preflight → kills mass-regressed BUG-E-014.
