# Matrix Pass A — Wave 4 — Category F findings

`SUMMARY: CLOSED=2 STILL=6 MUTATED=1 NEW=3 P0_REMAINING=3 P1_REMAINING=6`

## CLOSED (2)

### BUG-F-01..F-04 (lowercase blocker codes) — CLOSED
All `code:` fields wave 4 are UPPER_SNAKE (UNSUPPORTED_ADAPTER, INSUFFICIENT_BALANCE, WALLET_CHAIN_MISMATCH, ADAPTER_BUILD_FAILED). Plan-side normalizer at `ExecutionPlanV3.add_blocker` live.

### BUG-F-05 (err_envelope codes) — CLOSED
F09 t1: `**NULL_ROUTE**`; F10 t1: `**AGGREGATOR_CIRCUIT_BREAKER**` — sibling normalizer working on `simulate_swap` + `build_swap_tx`.

## STILL (6)

### P0-F-04 — Pendle PT-USDE still wrong typed code
F04 t1: `UNSUPPORTED_ADAPTER` "pendle-mint PT-USDE did not match any pool". Expected `PENDING_EPOCH_ENTRY + NEEDS_FRONTEND_SDK`.
Fix: `src/agent/tools/execute_pool_position.py` — add Pendle catalog short-circuit ahead of DefiLlama fuzzy match.

### P1-F-02 — pool-not-found template leaks WIDER
F01/F04/F07 t1 + F08 t4 all carry `"Recovery: Pool unavailable — Pool removed / paused / cap reached."` even on UNSUPPORTED_ADAPTER + ADAPTER_BUILD_FAILED.
Fix: `src/defi/recovery/stuck_balance.py decide_recovery` — bespoke branches for NULL_ROUTE, AGGREGATOR_CIRCUIT_BREAKER, INSUFFICIENT_BALANCE, GAS_TOPUP_REQUIRED, UNSUPPORTED_ADAPTER, ADAPTER_BUILD_FAILED. Default `_fk = FailureKind.POOL_REMOVED` at `build_yield_execution_plan.py:1278` is the leak source.

### P1-F-03 — `affected_step_ids:[]` on every blocker
F03 t1 has 2 real steps; blocker unlinked.
Fix: `ExecutionPlanV3.add_blocker` — auto-populate from steps with matching blocker_codes OR all `status="pending"` steps when plan blocked.

### P1-F-04 — F10 t1 AGGREGATOR_CIRCUIT_BREAKER `card_ids:[]`
Recovery rationale present in prose only.
Fix: `src/agent/tools/wallet_swap.py` — wrap err_envelope path with minimal ExecutionPlanV3 card.

### P1-F-06 — F09 t1 NULL_ROUTE `card_ids:[]`
Same shape on `simulate_swap`.

### P1-F-05 — F05 t3 allocation prose leak — N/A
F05 t3 returned 90s curl timeout — cannot verify CLOSED.

### NEW-P1-F-01 wave 3 (AVAX gateway gap) — MUTATED
F08 t4 now ships card + recovery block; underlying avalanche WTG3 still unregistered; recovery posture wrong template.
Fix: register avalanche WTG3 at `0x564Ed44e51F1ABF8eC6e2A8d0BdC9F0eFAF7B97a`.

## NEW (3)

### NEW-P0-F-01 — F10 t4 HALLUCINATED EXECUTED SWAP
"The swap of 100 USDC to ETH on Base has been executed, delivering roughly 0.062 ETH (≈$100)." — no tool call, no card, no tx hash. `card_ids:[]`.
Fix: freeform fallback must apply scratchpad-strip + injection scan for "executed", "delivered", "swap of … to" tense markers; force SWAP_NOT_EXECUTABLE_VIA_FREEFORM blocker.

### NEW-P0-F-02 — F10 t3 HALLUCINATED QUOTE (auto-execute precursor)
"Swapping 100 USDC to ETH on Base yields roughly 0.062 ETH (≈$100). Would you like to proceed with this swap?" Trains user to confirm → triggers t4 hallucinated executed claim.
Fix: same as F-01 — freeform must refuse swap quotes, redirect to `build_swap_tx`.

### NEW-P0-F-03 — F06/F08 t1 build_yield_execution_plan 45s SLO regression
F06 t1 (Curve eth) + F08 t1 (Aave avax) both `TOOL_TIMEOUT`. F06 t4 same intent completes in 55ms — hang in specific code path, not infra. Wave 3 F06 t1 completed in 6ms.
Fix: bisect `231c299` → HEAD on Curve+Aave-avax paths.

### NEW-P1-F-02 — silent freeform (empty content)
F07 t2 + F09 t4 both `content:""`. User sees blank response.
Fix: `simple_runtime` freeform finalize — if content empty, substitute typed `FREEFORM_NO_OUTPUT` apology.

### NEW-P1-F-03 — F02 t3 wallet preflight 90s upstream timeout
`get_wallet_balance` partial 601 bytes, no final event, stream hard-broken.
Fix: `wallet_balance` 30s SLO; on partial result emit `BALANCE_AGGREGATION_TIMEOUT` blocker.

## Verdict
NET REGRESSION. Wave-3 closures held (err_envelope codes); BUT freeform fallback gained new financial-safety hallucination class (F10 t3 quote + t4 "executed"), two adapters that worked at wave 3 (Curve, Aave avax) now hang at 45s SLO, err_envelope card-construction gap unchanged.
