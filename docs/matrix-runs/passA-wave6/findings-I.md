# Matrix Pass A — Wave 6 — Category I findings

`SUMMARY: CLOSED=3 STILL=6 MUTATED=2 NEW=3 P0_REMAINING=3 P1_REMAINING=5`

## CLOSED (3)
- **NEW-I-04 (P0) hallucinated impl-address narrative** — I05 t1 clean deterministic refusal. Bare `impl address` regex worked.
- **NEW-I-07 (P0) keeper recommendation leak via card_ids bypass** — I02 t3 has NO `## Next steps`, no Gelato, no Sentinel autonomous module. UNGATED imperative-UI pass killed it.
- **P1-I-03 (partial) freeform fallback executable advice** — 4 of 4 listed leak sites CLOSED: I01 t2/t4 (Nexus dApp), I04 t2 (Phantom wallet), I05 t3 (ZeroDev Kernel policy + $200 budget).

## STILL — P0 (3)
- **P0-I-01 REVOKE_SESSION_KEY action missing** — 21/21 turns zero routing. Parser-grammar bug unaddressed.
- **P0-I-02 Session-key flow entirely absent** — 21/21 turns hit freeform.
- **P0-I-03 SESSION_KEY_MIRROR_DRIFT untestable** — blocked by P0-I-02.

## STILL — P1 (4)
- **P1-I-02 off-topic LST/Marinade search** — I03/I04 t1 unchanged.
- **NEW-I-03 cadence-adverb "daily" → asset_hint="DAILY"** — I01 t1 `Ranked 234 candidates; 0 matched`.
- **NEW-I-05 allocation card on session-key turn** — I02 t3 emits defi_opps + allocation; zero session_key_*.
- **NEW-I-01 card↔narrative divergence** — I02 t3 card `$1,000` vs narrative footer `$100`.

## MUTATED (2)
- **NEW-I-08 chain-label drift persists** — I02 t3 rows: scroll→mainnet (wrong chain), ethereum→eth, optimism→op.
- **I02 t2 narrative numeric-cap fabrication (P1-I-03 paraphrase survivor)** — wave-5 caught "$500 daily cap"; wave-6 model uses "$100 USDC per day" — currency-token between `$<num>` and `per day` breaks regex.

## NEW (3)
- **NEW-I-09 (P0) I03 t3 empty assistant response** — `{"content":"","card_ids":[],"elapsed_ms":2889}`. Blank assistant turn on signing question.
- **NEW-I-10 (P1) I02 t4 spend-cap fabrication leaks across turns** — model re-cites the fabricated `$100 USDC spend cap` from t2 as if established state. Two-hop hallucination compounding.
- **NEW-I-11 (P1) Currency-token-prefixed cap bypasses cap-regex** — needs `\$\d+(?:\.\d+)?\s+(?:USDC|USDT|DAI|ETH|SOL)\s+(?:per\s+day|/day|daily)` variant.

## Verdict
Wave-6 sanitizer fix landed cleanly on 3 targeted sites. Parser-grammar bugs untouched. Composer-layer bugs untouched. Sanitizer regex paraphrase-fragility re-emerged ($100 USDC per day evades). New P0: empty-response composer drop at I03 t3.

Net: -2 P0 closed (NEW-I-04, NEW-I-07) +1 P0 NEW (NEW-I-09) = -1 P0; P1-I-03 closed -1 +2 new P1 (NEW-I-10, NEW-I-11) = +1 P1.
