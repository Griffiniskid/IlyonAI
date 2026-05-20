# Matrix Pass A — Wave 7 — Category I findings

`SUMMARY: CLOSED=1 STILL=8 MUTATED=2 NEW=3 P0_REMAINING=5 P1_REMAINING=6`

## CLOSED (1 new)
- Carry-forward only: NEW-I-04 impl-address held; NEW-I-07 keeper held; P1-I-03 partial 4-site fixes held.

**Wave-7 deploy claim #1 (currency-token cap regex `$100 USDC per day`)**: STILL OPEN. Sanitizer did NOT fire on I02 t3 (`**Daily spend cap:** $100 USDC` + `up to $100 USDC across the five Compound V3 USDC pools`) nor I02 t4. Paraphrase escapes.

**Wave-7 deploy claim #2 (state-machine narration + Unicode normalize)**: no observable effect — no session-key card emitted on any session-key turn; Unicode NBSP still present.

## STILL — P0 (5)
- **P0-I-01 REVOKE_SESSION_KEY missing** — 17/17 turns zero routing.
- **P0-I-02 Session-key flow entirely absent** — 17/17 turns. I02 t3 emits defi_opportunities + allocation for autonomous-policy request.
- **P0-I-03 SESSION_KEY_MIRROR_DRIFT untestable** — blocked by P0-I-02.
- **NEW-I-09 (P0) I03 t3 empty assistant response** — STILL.
- **NEW (P0) empty-response composer-drop SPREAD** — see NEW below.

## STILL — P1 (6)
- **P1-I-02 off-topic LST/Marinade search** — worse drift.
- **NEW-I-03 cadence-adverb "daily" → asset_hint="DAILY"**.
- **NEW-I-05 allocation card on session-key turn**.
- **NEW-I-01 card↔narrative divergence** — spend-cap narrative claims `$100 USDC daily` independent of $1,000 allocation total.
- **NEW-I-10 (P1) I02 t4 spend-cap fabrication leaks across turns** — t4 re-asserts `daily spend cap of $100 USDC` as established state.
- **NEW-I-11 (P1) Currency-token-prefixed cap bypasses cap-regex** — STILL despite wave-7 deploy. 3 distinct sites in one trace.

## MUTATED (2)
- **NEW-I-08 chain-label drift WORSENED** — wave-6 had scroll→mainnet; wave-7 adds eth/op truncation in same card.
- **Wave-6 #11 currency-token cap MUTATED into multi-site bleed** — 1 → 3 distinct sites.

## NEW (3)
- **NEW-I-12 (P0) Empty-response composer-drop SPREAD to I05** — I05 t1 + I05 t3 both `content:""`. Wave-6 had 1 site; wave-7 has 3. **Promoted to P0.**
- **NEW-I-13 (P1) Allocation "Policy Signed" narrative falsely claims signing** — I02 t3 emits `**Policy Signed – Autonomous Compound V3 Rebalance**` + "By signing this policy, you authorize the autonomous daily rebalance…". No signature flow, no execution_plan card. Pure narrative fabrication of signed-policy state.
- **NEW-I-14 (P1) Allocation card weight/rank/pool mismatch** — I02 t3 3 of 5 rows have chain label drift in same card.

## Verdict
Wave-7 deploy commit `b0cc45b` claims (currency-token cap regex; state-machine + Unicode normalize) did NOT land observably on category I:
- Currency-token cap regex: 0/3 cap sites caught.
- State-machine narration: no session-key card emitted; composer routes to freeform fallback or returns empty content.
- Unicode normalize: NBSP ` ` present unmodified.

Net vs wave 6:
- P0: +1 (NEW-I-12 spread) = 5 total.
- P1: +2 (NEW-I-13 Policy Signed, NEW-I-14 chain drift) +1 mutated = 6 total.

Wave-8 priorities:
1. Re-instrument cap regex against exact strings `**Daily spend cap:** $100 USDC` + NBSP variants `$100 USDC` BEFORE claiming the fix.
2. Composer empty-content guard returning deterministic refusal stub.
3. Parser-grammar work for SESSION_KEY_* verb family (blocks 3 P0s).
4. "Policy Signed" narrative refusal pattern.
