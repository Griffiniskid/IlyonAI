# Matrix Pass A — Wave 6 — Category E findings

`SUMMARY: CLOSED=4 STILL=10 MUTATED=1 NEW=3 P0_REMAINING=6 P1_REMAINING=5`

## CLOSED (4)
- **BUG-E-010 E06 t1 raw CoT after structured block** — body-scan extension working.
- **BUG-E-013 fabricated submitted-tx** — holds.
- **BUG-E-002 deBridge guest-guard** — holds.
- **BUG-E-004 partial** — 4 of 7 hot turns CLOSED: E02 t3, E03 t3, E05 t2, E11 t3.

## STILL (10)

### P0
- **BUG-E-001 Pattern A** — 6 turns produce pool_link instead of bridge plan.
- **BUG-E-003 composed plan status=ready with bridge tx=null** — E07 t4 unchanged.
- **BUG-E-004 freeform residual** — 4 STILL: E03 t2 (LI.FI how-to), E04 t2 (bare bridge claim), E08 t3 ("I'll create a ready-to-sign plan" variant evades regex), E13 t3 (`**Bridge route:**` markdown-bold prefix breaks anchor).
- **BUG-E-017 source_chain DROPPED — EXPANDED** — 8 turns: aave-v3 (E04/E12/E13/E14) + morpho-blue NEW (E09).

### P1
- **BUG-E-008 mock balance 190.132 USDC** — E05/E14.
- **BUG-E-009 WALLET_CHAIN_MISMATCH vs WALLET_NOT_CONNECTED**.
- **BUG-E-014 stale card re-emit on resume** — 9 of 15 chains (8→9 regression).
- **BUG-E-015 junk Uniswap V4 pools executable:true**.

## MUTATED (1)
- **BUG-E-004** — 3 CLOSED, 4 STILL with evasion shapes.

## NEW (3)

### NEW-1 (P0) — E01 t2/t3/t4 freeform "Execution Plan state-machine" narration
"Please sign the transaction in your connected wallet; once signed the Execution Plan will move from `draft` to `executed` and the bridge will proceed." Three back-to-back turns. Sanitizer fires on neither pattern.
Fix: regex `(Execution Plan|plan) will (move|transition|go) from .*(draft|pending).* to .*(executed|signed)` and `bridge will proceed`.

### NEW-2 (P0) — BUG-E-004 sanitizer regression on E02 t2/t4
Wave-5 marked CLOSED; wave-6 has both leaking again: "Please approve and sign the transaction in your wallet to bridge 200 USDC from Ethereum to Arbitrum via deBridge (Arbitrum Gateway) with 0.5 % slippage". Wave-6 patch added "Arbitrum Gateway" + "0.5 % slippage" patterns — neither fires.
Root cause: ` ` (NARROW NO-BREAK SPACE) inside "200 USDC", "0.5 %", "0.5 % slippage" defeats `\b` boundaries / literal space regex chars.
Fix: pre-normalize ` ` → ` ` before sanitizer pass.

### NEW-3 (P0) — BUG-E-017 expanded to morpho-blue
E09 t1/t3 (ETH→ARB Morpho 250 USDC) parses as `{chain:"arbitrum", protocol:"morpho-blue"}` with NO `extra.source_chain`. Protocol-fastpath bypass now also trips on morpho-blue.

### NEW-4 (P1) — Sanitizer scope misses ExecutionPlanV3 step descriptions
E07 t4 step 1 description embeds `"slippage band 25-50 bps"` — sanitizer scans `final.content` only, not card-payload step descriptions.

## Highest-impact wave-7 moves
1. Pre-normalize ` ` → ` ` before sanitizer regex pass → re-closes E02 t2/t4 + E13 t3.
2. Add regex for `Execution Plan will (move|transition|go) from .* to .*(executed|signed)` + `bridge will proceed` + `I'll create a ready-to-sign plan` + `I can generate a signable Execution Plan` + bare `X is the bridge used to`.
3. Planner lexeme parser must stamp `extra.source_chain` BEFORE protocol-fastpath for ALL protocols → closes BUG-E-001 Pattern A (6) + BUG-E-017 (8) including morpho-blue.
4. Deploy `COMPOSED_PLAN_INCOMPLETE_TX` post-stitch normalizer → closes BUG-E-003.
5. Run sanitizer over `payload.steps[].description` → closes NEW-4.
6. Session-resume preflight rerun → closes BUG-E-014 (now 9 chains).
