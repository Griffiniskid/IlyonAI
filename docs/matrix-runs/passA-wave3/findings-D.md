# findings-D — matrix Pass A wave 3, category D (lifecycle)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 2 (8 P0 + 11 P1 + 4 P2).
**Verdict**: NET REGRESSION +2 P0. CLOSED=2 + PARTIAL=1 + STILL=16 + NEW=2. **P0=9, P1=12, P2=4** (was 8/11/4).

## CLOSED (2)

- **D-P1-12** D13 t1 truncated APY column ("167." fragment) — final shows clean table.
- **D-P1-02** D02 t3 freeform-fallback misclaim "ready" — now emits real execution_plan_v3.

## PARTIAL (1)

- **D-P1-14 drain risk** — Aave Pool WTG3 USDC description now reads "Withdraw ALL USDC" (D02 t3/t4 fixed). **STILL drain-risk on 2/3 paths**: (a) D07 t2 Yearn calldata `0xb460af94 ffff…ffff` + description "ERC-4626 withdraw(0)", (b) D09 t2 Aave WTG3 native `withdrawETH(…, ffff…ffff, …)` + summary "Withdraw 0 ETH". **Remains P0.**

## STILL (16)

- D-P0-02 close_position validator + verb router (D01 close NFT → supply; D04 remove pcs → supply; D12 close whirlpool → withdraw on slug `orca-usdc-`)
- D-P0-03 claim+withdraw / remove_liquidity verb router
- D-P0-04 slug allowlist + chain-kind (D09 weth9-wrap → v2 link; D11 `via-secondary-market-on-jupiter` chain_id=1 for Solana stake; D12 `orca-usdc-` trailing dash)
- D-P0-05 DAG-walk balance preflight (D09 t3 still "Need 0.05 WETH, wallet has 0 WETH")
- D-P0-06 adapter-build error wrapper (D14 `_bn`; D15 obligation/lendingMarket leak)
- D-P0-07 unstake/liquid_unstake router (D10 liquid-unstake mSOL → freeform; D11 unwind jitoSOL → freeform)
- D-P0-08 borrow/repay verb router (D08 entire chain still routes → supply)
- D-P1-01 card-flag vs reasoning-footer drift (D10/11/12/13 t1)
- D-P1-11 continuation re-emits blocked card (D11 t4, D15 t4)
- D-P1-13 legacy execution_plan requires_signature:false on signable Stake/Supply
- D-P1-06..10 (timeouts elapsed 39-61s on D03/D06/D08/D11/D13 — 8+ chains)
- D-P2-01..04

## NEW (2)

### D-P0-09 NEW — Withdraw intent silently relabeled "deposit" inside adapter error
D15 t3: user "withdraw 50 USDC from kamino-lend", tool args `action=withdraw`, blocker text reads "kamino-lend **deposit** could not be built (Kamino REST unreachable…)". Either kamino-lend adapter dispatches both supply+withdraw through deposit builder OR error string is hardcoded "deposit". Plus raw internal account-list leak (D-P0-06 + D-P0-08 combined).

### D-P1-15 NEW — D09 t3 step index numbering starts at 0
DAG planner injects wrap pre-step at index=0 instead of renumbering. Final text renders "Step 0 — approve" then "Step 1 — supply". UI expects 1-indexed.

## Counts

- CLOSED: 2
- PARTIAL: 1 (drain-risk Aave USDC closed, Yearn + Aave-native-ETH still LIVE)
- STILL: 16
- NEW: 2
- **P0=9, P1=12, P2=4** (was 8/11/4 — net regression +2 P0 due to D-P0-09)

## Wave-3 top-fix priority

1. **D-P1-14 drain risk** — Yearn ERC-4626 + Aave native ETH paths still LIVE
2. **D-P0-09 NEW** kamino withdraw silently mislabeled "deposit" + raw account-list leak
3. **D-P0-08** borrow/repay verb router
4. **D-P0-07** unstake/liquid_unstake router
5. **D-P0-03** claim+withdraw / remove_liquidity router
6. **D-P0-02** close_position validator + verb router
7. **D-P0-04** slug allowlist
8. **D-P0-05** DAG-walk preflight
9. **D-P0-06** adapter wrapper
10. **D-P1-11** continuation re-emit guard
11. **D-P1-13** legacy execution_plan requires_signature flag
