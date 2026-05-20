# Matrix Pass A — Wave 6 — Category F findings

`SUMMARY: CLOSED=2 STILL=8 MUTATED=1 NEW=0 P0_REMAINING=3 P1_REMAINING=6`

## CLOSED (2)
- **NEW-P0-F-02 F10 t3 "gives you about"** — chokepoint refuses cleanly.
- **NEW-P1-F-07 F02 t4 confirmation-without-card** — now educational disambiguation.

## STILL (8)

### P0
- **P0-F-04 F04 t1 Pendle PT-USDE wrong typed code** — still UNSUPPORTED_ADAPTER.
- **NEW-P0-F-04 F04 t2 fabricated Pendle epoch + date** — STILL OPEN: "Pendle's PT-USDe minting epochs open every Thursday at 00:00 UTC… next epoch starts Thursday 25 Sep 2025 at 00:00 UTC" with 8-month-stale date in 2026 universe. Wave-6 `_FREEFORM_PROTOCOL_SCHEDULE_RE` did NOT fire — pattern too narrow (needs `epoch.{0,40}(?:open|start|run)` not just `open every`).
- **NEW-P0-F-08 F05 t3 allocation timeout** — MUTATED (improved): hard stream break → 49.2s completion with 3 cards, but still over 30s SLO.

### P1
- **NEW-P1-F-08 F02 t3 raw JSON balance dump** — `get_wallet_balance` returns raw JSON in content with `card_ids:[]`.
- **NEW-P1-F-01 F08 t4 AVAX gateway gap** — still "WrappedTokenGatewayV3 not registered on avalanche".
- **P1-F-02 pool-not-found template leak** — F01/F04/F07 t1.
- **P1-F-03 affected_step_ids:[] on blockers w/ real steps** — F03 t1, F08 t1.
- **P1-F-04 F10 t1 AGGREGATOR_CIRCUIT_BREAKER card_ids:[]**.
- **P1-F-06 F09 t1 NULL_ROUTE card_ids:[]**.

## MUTATED (1)
- **NEW-P0-F-08 F05 t3** — improved from hard break to 49s but still over SLO.

## Verdict
2 of 3 wave-5 P0 surface fixes landed (gives-you-about, confirm-without-card). **NEW-P0-F-04 (fabricated Pendle epoch + 8-month-stale date) is the most serious miss** — schedule regex either didn't deploy or matches too narrowly. err_envelope card-wrapping for blockers (P1-F-02/-03/-04/-06) untouched.
