# Matrix Pass A — Wave 5 — Category F findings

`SUMMARY: CLOSED=6 STILL=7 MUTATED=0 NEW=4 P0_REMAINING=2 P1_REMAINING=8`

## CLOSED (6)
- **BUG-F-01..F-05** code normalization holds.
- **NEW-P0-F-01 F10 t4 hallucinated executed swap** — chokepoint catches "has been executed".
- **NEW-P0-F-03 F06/F08 t1 build_yield_execution_plan timeouts** — F06 t1 27.5s, F08 t1 21.2s (within SLO).
- **NEW-P1-F-02 F07 t2 / F09 t4 silent freeform empty content** — now substitutes apology + re-ask CTA.
- **NEW-P1-F-03 F02 t3 wallet preflight 90s timeout** — completes in 16.3s.

## STILL (7)

### P0-F-04 Pendle PT-USDE still wrong typed code
F04 t1 `UNSUPPORTED_ADAPTER` instead of `PENDING_EPOCH_ENTRY + NEEDS_FRONTEND_SDK`.

### NEW-P0-F-02 F10 t3 HALLUCINATED QUOTE — STILL OPEN
"Swapping 100 USDC to ETH on Base **gives you about** 0.062 ETH (≈$100)." Wave-4 fix catches `swap(ping) X to Y on Z yields|delivers`; this uses `gives you about`. Pattern mutation evaded regex.
Fix: extend regex with `gives?\s+you\s+(?:about|roughly|approximately|~)?\s*[\d.,]+\s*(ETH|SOL|USDC|...)`.

### P1-F-02 pool-not-found template leaks wider
F01/F04/F07 t1 + F08 t4 all carry "Recovery: Pool unavailable — Pool removed / paused / cap reached" even on UNSUPPORTED_ADAPTER + ADAPTER_BUILD_FAILED.

### P1-F-03 affected_step_ids:[] on every blocker
F03 t1 has 2 real steps; INSUFFICIENT_BALANCE blocker `affected_step_ids:[]`. F08 t1 same.

### P1-F-04 F10 t1 AGGREGATOR_CIRCUIT_BREAKER card_ids:[]
Recovery rationale in prose only.

### P1-F-06 F09 t1 NULL_ROUTE card_ids:[]
Same shape on `simulate_swap`.

### P1-F-05 F05 t3 allocation prose leak — STILL N/A (now regression NEW-P0-F-08)
Second wave same 90s curl timeout on allocate-to-prior-pool-list.

### NEW-P1-F-01 AVAX gateway gap (wave 3)
F08 t4 still "Aave V3 WrappedTokenGatewayV3 not registered on avalanche".

## NEW wave-5 (4)

### NEW-P0-F-04 (P0) — F04 t2 HALLUCINATED PENDLE EPOCH DATES
"Pendle's PT-USDe minting epochs open every Thursday at 00:00 UTC… Based on today's date (Wednesday 24 Sep 2025), the next epoch starts Thursday 25 Sep 2025…" — no tool call, fabricated cadence, **fabricated date (Sep 2025 in a 2026 universe)**, invented "Discord/announcements" source.
Fix: add `_FREEFORM_PROTOCOL_SCHEDULE_RE = r"(pendle|sky|spark|aave|maple).{0,80}(epoch|countdown|window|opens?\s+(?:every|on|at)|starts?\s+at)"`. Route through `pendle_schedule` tool or refuse.

### NEW-P1-F-07 (P1) — F02 t4 CONFIRMATION-PROMPT-WITHOUT-CARD
"Supply 100 USDC to Aave V3 on Base. Risk: MEDIUM. Confirm if you'd like to proceed." `card_ids:[]`. Primes user to type "yes" — same precursor pattern that produced wave-4 NEW-P0-F-01 (executed-swap hallucination).
Fix: extend chokepoint to refuse `(supply|stake|swap|bridge|deposit|withdraw)\s+\d+\s+\w+.*\b(confirm|proceed|let me know|would you like)\b` when no tool was called this turn.

### NEW-P1-F-08 (P1, regression) — F02 t3 RAW JSON BALANCE DUMP
SSE final: `{"type": "balance_report", "wallet_addresses": [...], "balances": [...], "total_usd": 66334.4}` — raw JSON in content field, `card_ids:[]`. User sees JSON wall.
Fix: `get_wallet_balance` must wrap into `wallet_balance` card_type.

### NEW-P0-F-08 (P0, regression) — F05 t3 ALLOCATION 90s CURL TIMEOUT
Hard stream break, no SSE done. Two consecutive waves same path.
Fix: 30s SLO on allocate-to-prior-pool-list.

## Verdict
NET PROGRESS but financial-safety NOT fully closed. Wave-4 chokepoints landed and caught executed/submitted tense, silent freeform, 45s SLO regression. BUT: F10 t3 `gives you about` mutated past regex, F04 t2 surfaces NEW P0 hallucination class (fabricated schedule + invented date), F02 t4 surfaces NEW P1 precursor.
