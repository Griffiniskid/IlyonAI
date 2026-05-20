# findings-I — matrix Pass A wave 3, category I (session-key / AA)

**Scope**: 5 chains, 21 turns. **Baseline**: wave 2 (3 P0 STILL + 4 P1).
**Wave 3 fix added**: err_envelope normalizer. **Predicted impact on I: none** (session-key turns short-circuit at freeform fallback before any err_envelope can fire). **Confirmed: zero err_envelope blockers observed**.

## P0 (3, all STILL)

- **P0-I-01** REVOKE_SESSION_KEY action missing — STILL. I02 t4 (asks for verb-form `Revoke USDC allowance for Compound V3 on Polygon`), I03 t3/t4 (ERC-20 template), I04 t4 (Phantom sign-in-wallet instruction), I05 t4. Zero V7-074 routing.
- **P0-I-02** Session-key flow entirely absent — STILL. All 21 turns. Zero session_key_install / session_key_policy / aa_install_module cards. Even I05 t3 user says "Create a ZeroDev Kernel policy for autonomous rebalancing with a daily budget of $200" — agent merely echoes the request as final narrative, emits no card.
- **P0-I-03** SESSION_KEY_MIRROR_DRIFT untestable — STILL.

## P1 (5)

- **NEW-I-01** Card↔narrative divergence — STILL (I02 t2 — softer narrative but still implies signable plan).
- **NEW-I-02** ERC-20 template misroute — **STILL on I03**, **CLOSED on I02** (I02 t4 now asks for verb form not ERC-20 template — improvement).
- **P1-I-02** Off-topic search results for LST / Marinade — STILL. I03 t1 returns Saturn/Uniswap-V4/Curve; I04 t1 returns FX perps. Intent parser drops `protocol_family=LST` and `protocol_filter=marinade-finance` hints.
- **P1-I-03** Freeform fallback gives executable advice without calldata — STILL, **SCOPE EXPANDED**. I04 t2+t3 verbatim Marinade imperative. I04 t4 "Open Phantom wallet, locate signing request..." NEW I02 t3: multi-step keeper recipe naming Gelato/Keep3r/Sentinel as third-party services — worst leak yet.
- **NEW-I-03 (NEW P1)** Asset-hint hallucination on cadence adverbs. I01 t1: user asked to "rebalance daily across Aave V3 USDC pools" → intent parser captured `asset_hint="DAILY"` → 0 matches → "Loosen any one filter" reply. Fix: stoplist `{DAILY, WEEKLY, HOURLY, MONTHLY, YEARLY, ANNUALLY}` from asset_hint extraction.

## P2

- **CLOSED**: I01 t5 EXPECTED_REFUSAL_INTENT_ACKED fires correctly.
- **STILL** (mutated): I02 t2 chain-label drift (`defi_opportunities` uses "scroll/ethereum/optimism"; `allocation` uses "mainnet/eth/op"). Rank-2 row mis-labelled — DefiLlama pool is scroll USDC but allocation tags chain="mainnet".
- **CLOSED**: AI-unavailable / TOOL_TIMEOUT not observed (BUG-M01 stays clean).
- **CLOSED**: err_envelope normalizer no impact / no regression on session-key paths (predicted).

## Counts

| Severity | Wave 2 | Wave 3 | Delta |
|----------|--------|--------|-------|
| P0       | 3 STILL | 3 STILL | 0 |
| P1       | 2 STILL + 2 NEW = 4 | 2 STILL + 2 partial-STILL + 1 NEW = 5 | +1 (NEW-I-03 cadence-adverb) |
| P2       | 1 CLOSED + 1 STILL | 2 CLOSED + 1 STILL | +1 CLOSED |

## Verdict

FINDINGS — all 3 wave-1/2 P0s persist for 3rd pass running. Wave 3's err_envelope normalizer didn't touch session-key surface (predicted). One marginal improvement (I02 revoke template), one regression (I02 freeform expanded to keeper orchestration recipes), one fresh P1 (cadence-adverb).

Root cause unchanged: **intent parser has no session_key_* / aa_install_module / revoke_session_key verbs in its grammar.** Until P0-I-02 is fixed, every I chain hits the freeform fallback.
