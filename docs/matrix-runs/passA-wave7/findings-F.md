# Matrix Pass A — Wave 7 — Category F findings

`SUMMARY: CLOSED=1 STILL=7 MUTATED=2 NEW=7 P0_REMAINING=4 P1_REMAINING=12`

## CLOSED (1 new)
- **NEW-P0-F-04 F04 t2 fabricated Pendle epoch + 8-month-stale date** — CLOSED. Broadened `_FREEFORM_PROTOCOL_SCHEDULE_RE` fires correctly.

## STILL (7)
### P0
- **P0-F-04 F04 t1 Pendle PT-USDE wrong typed code** — `execute_pool_position(pool="pendle-mint PT-USDE")` routes to generic UNSUPPORTED_ADAPTER template.

### P1
- **NEW-P1-F-08 F02 t3 raw JSON balance dump** — STILL, MUTATED-worse (compounds NEW-P0-F-09 USD overflow).
- **P1-F-02 pool-not-found template leak**.
- **P1-F-03 affected_step_ids:[] on blockers with real steps**.
- **P1-F-04 F10 t1 AGGREGATOR_CIRCUIT_BREAKER card_ids:[]**.
- **P1-F-06 F09 t1 NULL_ROUTE card_ids:[]**.

## MUTATED (2)
- **NEW-P0-F-08 F05 t3 allocation timeout** — MUTATED **worse**: 58.7s (was 49.2s wave-6, hard break wave-5).
- **NEW-P1-F-01 F08 AVAX gateway gap** — MUTATED. No more "WrappedTokenGatewayV3 not registered" — instead `TOOL_TIMEOUT` after 45s with no message. Worse signal.

## NEW (7)
### P0
- **NEW-P0-F-09 wallet balance USD overflow $5e30** — F02 t3 `usd_total: 4.99808435474501e+30`. Source: Base `spark` token decimals × bad price. Pollutes downstream USD gates.
- **NEW-P0-F-10 allocation execution_plan step-index hole** — F04 t4 + F05 t3/t4: alloc shows 5 positions but plan emits 4 steps with indexes `[1,2,3,5]` or `[1,3,4,5]`. Silent step drop. User signs 4 of 5 promised positions. **Breaks plan↔alloc invariant.**

### P1
- **NEW-P1-F-09 F09 t3 empty final content** — `{"content":"", card_ids:[], elapsed_ms:6789}`.
- **NEW-P1-F-10 F03 t4 TOOL_TIMEOUT on in-balance supply** — Aave V3 Base wallet has 190 USDC; 10 USDC supply blew 45s SLO.
- **NEW-P1-F-11 F08 t3 fabricated AVAX balance math** — "you'll have ~0.35 AVAX total", "0.68 AVAX needed" with no tool call.
- **NEW-P1-F-12 get_wallet_balance 55s latency** (F02 t3).
- **NEW-P1-F-13 F06 t1/t4 Curve volatile-pool blocker missing** — "Supply USDC to Curve" routes to status:ready via Enso shortcut.
- **NEW-P1-F-14 sentinel-score search ranks 167% APY HIGH-risk on top** (F06 t3) — gmtrade USDCHF-USDC 167.6% APY $1.5M TVL HIGH-risk as #2.

## Verdict
Pendle schedule fix landed. **Critical regressions wave 7:**
1. NEW-P0-F-10 step-index hole — trust-breaking.
2. NEW-P0-F-09 $5e30 USD overflow.
3. NEW-P0-F-08 allocation timing regressed 49s → 58s.
4. NEW-P1-F-01 mutated to mask AVAX gateway error behind 45s timeout.

Net: 1 closed, 7 new, 2 mutated-worse, 7 still. **P0 count grew from 3 → 4**; **P1 count grew from 6 → 12**.
