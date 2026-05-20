# findings-I — matrix Pass A wave 2, category I (session-key / AA)

**Scope**: `docs/matrix-runs/passA-wave2/I01..I05/turn_*.txt` — 5 chains, 21 turns.
**Baseline**: `docs/matrix-runs/passA-wave1/findings-I.md` (3 P0 + 3 P1).
**Known-live fixes**: BUG-M01 singleton, BUG-M02 projection-jump, blocker normalizer. P0-I-01/02/03 NOT yet fixed.

## Per-chain verdict

| Chain | Turns | SK install card? | Revoke action? | Mirror-drift gate? | Net vs wave 1 |
|-------|-------|------------------|----------------|--------------------|---------------|
| I01_session_key_aave     | 5 | NO | NO | NO | PARTIAL — refusal-acked still fires |
| I02_session_key_compound | 4 | NO | NO | NO | PARTIAL — NEW regression: execution_plan card vanished on t2 |
| I03_session_key_LST      | 4 | NO | NO | NO | PARTIAL — off-topic persists; NEW "send me token/spender/wallet" template |
| I04_session_key_marinade | 4 | NO | NO | NO | PARTIAL — verbatim same imperative leak on t3 |
| I05_session_key_kernel   | 4 | NO | NO | NO | STILL — 100% freeform fallback, identical to wave 1 |

## P0 findings (all STILL)

- **P0-I-01** REVOKE_SESSION_KEY action missing — STILL. I02 t4, I03 t3/t4, I04 t4, I05 t4. Asks for ERC-20 approval primitives instead of routing "revoke session key" verb into V7-074.
- **P0-I-02** Session-key flow entirely absent — STILL. I01–I05 all 5. Zero `session_key_install` / `session_key_policy` / `aa_install_module` cards across 21 turns.
- **P0-I-03** SESSION_KEY_MIRROR_DRIFT untestable — STILL (downstream of P0-I-02).

## P1 findings

### NEW-I-01 (P1) — BUG-M02 partial fix introduced card↔narrative divergence
- **Hit**: I02 t2.
- **Wave 1**: `defi_opportunities` + `allocation` + `execution_plan` with `serialized:null`, `requires_signature:true` (draft→ready skip).
- **Wave 2**: Only `defi_opportunities` + `allocation` emitted. **No `execution_plan` card.** Final narrative still says "Sign each supply transaction individually via your wallet (one per pool) using the deterministic Execution Plan" — instructing user to sign a plan that was never built.
- **Diagnosis**: Projection-jump silent-admit now suppresses execution_plan emission, but narrative wording + allocation card "next steps" were not updated in lockstep.
- **Fix path**: when execution_plan is suppressed by the projection-jump guard, scrub "Execution Plan" / "Sign each transaction" wording from LLM final, OR emit a stub execution_plan card with `blocker: EXPECTED_DRAFT_PRE_SIMULATED` so UI shows pending state.

### NEW-I-02 (P1) — Session-key/revoke asks misrouted to ERC-20 approval template
- **Hit**: I03 t2, t3, t4.
- New canned template in wave 2: "I need: token contract address, spender contract address, your wallet address, network/chain ID." Asks for ERC-20 approval primitives in response to session-key / mirror / revoke questions. Worse than wave-1 generic refusal because it confuses the user about agent capabilities.

### P1-I-02 (STILL) — Off-topic search results when LST / Marinade asked
- I03 t1 (Saturn SUSDAT, Uniswap-V4 RAVE-USDT…), I04 t1 (gmtrade XAU-USDC, SOL-USDC FX perps).
- Intent-parser still drops LST class + Marinade/Jito protocol-family hints.

### P1-I-03 (STILL) — Freeform fallback gives executable advice without calldata (verbatim)
- I04 t3 byte-for-byte identical to wave 1: "Open Marinade Finance, connect your Phantom wallet, and stake 0.1 SOL…"
- Imperative-verb suppression for freeform-fallback never landed.

## P2 (CLOSED + STILL)

- **CLOSED**: I01 t5 `EXPECTED_REFUSAL_INTENT_ACKED` still fires correctly with cleaner deterministic refusal narrative.
- **STILL**: I02 t2 chain-name normalization dupe (allocation rank 3 chain="mainnet" + rank 4 chain="eth", same pool surfaced twice). Identical to wave 1.
- **CLOSED**: AI-unavailable / TOOL_TIMEOUT not observed — BUG-M01 singleton fix stays clean.

## Summary

- CLOSED: 1 (EXPECTED_REFUSAL stays; BUG-M01 stays clean)
- STILL: 6 (P0-I-01, P0-I-02, P0-I-03, P1-I-02 off-topic, P1-I-03 freeform leak, chain-name dupe)
- NEW: 2 P1s (card↔narrative divergence from BUG-M02; ERC-20 template misroute)
- **Counts**: P0=3 (all STILL), P1=4 (2 STILL + 2 NEW)
- **Verdict**: **FINDINGS** — all 3 wave-1 P0s persist as predicted. Wave 2 introduces 2 new P1 regressions. Root cause remains P0-I-02 (intent parser has no session-key / AA-kind routing).
