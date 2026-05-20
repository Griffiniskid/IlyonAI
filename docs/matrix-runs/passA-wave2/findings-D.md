# findings-D — matrix Pass A wave 2, category D (lifecycle: close / withdraw / migrate)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 1 (6 real P0 + 10 P1 + 4 P2).
**Verdict**: REGRESSIONS + NEW. P0=8, P1=11, P2=4.

## DELTA vs wave 1

| Wave-1 ID | Wave-2 status |
|-----------|---------------|
| D-P0-01 test-wallet FP | **CLOSED** (sanitizer correctly accepts `0xaaaa...`) |
| D-P0-02 close_position validator | **STILL** (D01 t3 same invalid_amount) |
| D-P0-03 claim+withdraw bundle | **STILL** (D03 t2-t4) |
| D-P0-04 slug allowlist / chain-kind | **STILL** (D11 t3 `via-secondary-market-on-jupiter` chain_id 1) |
| D-P0-05 DAG-walk balance preflight | **STILL** (D09 t3 false INSUFFICIENT_BALANCE on wrap-then-deposit) |
| D-P0-06 adapter wrapper | **STILL** (D14 t1 raw JS `_bn` error) |
| D-P0-07 unstake verb router | **STILL** (D10 t4 freeform Marinade) |
| D-P1-01 card flag vs footer | **STILL** (D10/11/12/13 t1) |
| D-P1-03 8-pool reasoning | **CLOSED** |
| D-P1-04 D07 contradiction | **CLOSED** (t2 now TOOL_TIMEOUT not "suddenly ready") |
| D-P1-05 withdraw(0)→MAX_UINT256 | **PROMOTED to P0 / WIDER** → D-P1-14 |
| D-P1-06..10, D-P2-01..04 | All **STILL** |

## NEW in wave 2

### D-P0-08 — Aave borrow/repay verb routed to `action=supply`
D08 entire chain (borrow→repay cycle); t1/t2 timeout, t3/t4 emit Aave supply plans. No borrow/repay action ever reaches build_yield_execution_plan. Same shape as D-P0-03 (claim+withdraw) and D-P0-07 (unstake) — third missing verb in spec §13. Fix: verb router maps "borrow/take loan/refinance" → action=borrow and "repay/pay back" → action=repay.

### D-P1-11 — Continuation surface re-emits blocked card_id as if it were the plan
D11 t4 and D15 t4 re-emit prior blocked card with `BLOCKER_NOT_RESOLVED` boilerplate. UI clients auto-rendering `card_ids[0]` show a "plan" card whose contents are blocked. Fix: continuation handler must suppress re-emission or stamp `status=blocked`.

### D-P1-12 — D13 t1 allocation final text truncated mid-sentence
Final ends `… | 824.3% | HIGH |\n 167.\n\n_⚠ 5 of 5 …`. Card/text drift — stray APY-column fragment escapes its row.

### D-P1-13 — Legacy `execution_plan` (not v3) emits `requires_signature:false` on signable Stake/Supply
D10/11/12/13 t1: card_type=execution_plan with requires_signature:false despite verb=Stake/Supply with adapter_id set. Fix: `requires_signature = any(step.transaction or step.adapter_id is not None)`.

### D-P1-14 (PROMOTED from D-P1-05 to P0) — `withdraw(amount=0)` silently rewritten to MAX_UINT256 (drain risk)
Wave-1 narrowed to Yearn; wave-2 evidence now spans 2 adapters with live calldata:
- D07 t3 Yearn: calldata `0xb460af94 ffff…ffff` while description "Withdraw 0 USDC"
- D09 t2 Aave WTG3: `withdrawETH(…, type(uint256).max, 0xaaaa…)` while description "Withdraw 0 ETH"

User signs "0 withdraw" → contract drains entire position. **Worst-case lifecycle UX bug.**
Fix: reject amount_in==0 at validator OR force description "Withdraw ALL (max)" when calldata is MAX_UINT256, OR carry explicit `withdraw_all:true` to UI.

## Counts

- CLOSED: 3 (D-P0-01 test-wallet, D-P1-03, D-P1-04)
- STILL: 11
- NEW: 4 (D-P0-08, D-P1-11, D-P1-12, D-P1-13) + 1 promoted (D-P1-14)
- P0=8, P1=11, P2=4

## Wave-2 top-fix priority

1. D-P1-14 drain risk (most dangerous live bug)
2. D-P0-02 close_position validator carve-out
3. D-P0-05 DAG-walk preflight
4. D-P1-10 TOOL_TIMEOUT (1 chain → 8 chains widened)
5. D-P0-04 slug allowlist + chain-kind
6. D-P0-08 verb router for borrow/repay
7. D-P0-03 claim+withdraw verb router
8. D-P0-07 unstake/liquid_unstake router
9. D-P0-06 adapter-build error wrapper
10. D-P1-11 continuation re-emit guard
