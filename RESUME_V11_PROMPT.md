# RESUME V11 — Real-Conversation Validation Phase

You are continuing the IlyonAi pursuit of **production tester-ready** state.
The `tester-ready` tag at SHA `29dcd27` (Phase D session) **was rolled out
too early**: the very first human-tester conversation surfaced 23 distinct
bugs across protocol intent, card consistency, exception handling, time
formatting, allocation flow, sentinel scoring, and Markdown rendering. This
prompt re-orients the work around a stricter, conversation-driven
validation regime.

**Read this end-to-end before doing anything.** Especially the bug
catalogue — every item is grounded in `AI Bug Convo.md` (the verbatim
chat transcript) and is the source of truth for what the next fix waves
must close.

---

## WHAT'S WRONG WITH THE CURRENT `tester-ready` TAG

The 7 gates I claimed green at SHA `29dcd27` validated **syntax** (no
`undefined`, no token0/token1 inversion, no calldata revert, no
canonical-leak phrases) but **NO gate validated semantic correctness of
agent intent → action**. A tester opened the chat, exchanged 10 messages,
and within 5 minutes hit:

- A protocol intent inversion (asked for Aave V3, got Fluid Lending —
  silent substitution by the regex `_detect_*` dispatcher).
- A card title/asset/pool mismatch (USDC ask routed against WSTETH pool
  with no `INTENT_MISMATCH` blocker).
- A raw Python `UnboundLocalError: cannot access local variable
  'ExecutionBlocker'` shown verbatim to the user, twice.
- A `SIM_STALE: Simulation is Infinitys old (>30s)` string-format bug.
- A multi-pool "allocate $40 USDT on SOL across 4" intent collapsed into
  a single execute attempt with no allocation card ever emitted.
- Duplicate "Excluded 25 candidates" lines, missing sentinel-scoring bars,
  0% APY pools surfaced as "best", suspiciously-high APY pools ranked
  first without yield-trap warning, and more.

Roll back the tag (locally + on origin) and replace with
`pre-real-conversation-validation-v1` so the production-readiness claim
doesn't mislead anyone reading the repo while real validation continues.

---

## VERBATIM TRANSCRIPT EVIDENCE

The source-of-truth conversation lives at `AI Bug Convo.md` in the repo
root. Every bug ID below cites the line number(s).

### P0 bugs (lose user funds or trust on first contact)

**BUG-RC-001 — Protocol intent inversion.** Transcript line 801–833:
user typed `Supply 100 USDC to Aave V3 on Base`, agent emitted
`Fluid Lending Supply on Base` with tool args
`{"chain":"base","protocol":"fluid-lending",...}`. The user_message at
line 833 correctly contains "Aave V3" but the dispatcher routed to
`fluid-lending`. Root cause: `src/agent/simple_runtime.py` regex
`_detect_*` chain bypasses the typed `LiquidityIntent` envelope at
`src/agent/intent/lp_intent_extractor.py` (Phase C batch A audit
flagged this as orphan; I deferred as "architectural". It is P0.)

**BUG-RC-002 — Card title vs pool-id asset mismatch.** Transcript line
719–767: user typed `Execute deposit into pool 69b12bf9-…` (which is
`fluid-lending WSTETH` per turn 7 line 681). Agent emitted card with
title `Fluid Lending Supply — Supply 100.0 USDC via Fluid Lending on
Ethereum` and description `Direct deposit into fluid-lending WSTETH on
ethereum`. USDC and WSTETH cannot both be correct; the user signs a
USDC→WSTETH coercion they never asked for.

**BUG-RC-003 — Raw Python exception leaked to user.** Transcript lines
395–409: two consecutive `Execute deposit into pool <uuid>` prompts
returned literal `cannot access local variable 'ExecutionBlocker' where
it is not associated with a value`. An `UnboundLocalError` from
somewhere in the execute-by-pool-id codepath, never wrapped in a
structured error card. Exposes internal stack trace; breaks user flow
with zero recovery path.

**BUG-RC-004 — Re-quote intent unrecognised + cross-suggestion cascade.**
Transcript line 789–795: user typed `Re quote please` to refresh the
SIM_STALE state on the prior card. Agent refused with the generic
fallback and suggested `Supply 100 USDC to Aave V3 on Base` as an
example. User followed that suggestion and hit BUG-RC-001. Two failures
chained from one missing handler.

**BUG-RC-005 — Allocation intent collapsed to single execute.**
Transcript line 169–176: user typed `Can you pick 4 best pools out of
those in your opinion and distribute and allocate 40 usdt on sol across
them?` Agent picked ONE pool (Gmtrade XAU-USDC) and tried to execute it.
The multi-pool allocation flow that is the centre of §3 sizing/range
never fired. No `allocation` card was emitted at any point in the
entire conversation.

### P1 bugs (visible UX defects)

**BUG-RC-006 — `Infinitys` time-formatting leak.** Lines 779 and 889:
`SIM_STALE: Simulation is Infinitys old (>30s)`. Literal string
`"Infinitys"` — either `math.inf` got `str()`'d into a pluralised noun
or a template `{seconds}s` evaluated against `Infinity`. Must always be
finite numeric like `30s` or `1m 12s`.

**BUG-RC-007 — Duplicate "Excluded 25 candidates" footer.** Lines 29 +
163 (turn 1), 249 + 385 (turn 3), 593 + 713 (turn 7). The numbered-list
path and the card-list path BOTH emit the footer. Wording even drifts
between the two ("violated the requested" vs "violated requested").

**BUG-RC-008 — Pool count mismatch numbered-list vs cards.** Line 251
says `Execution readiness: 8 candidate(s) have adapter support` but the
numbered list at lines 239–247 enumerates only 5 pools. The cards then
render 8. User cannot tell whether there are 5 or 8 actionable pools.

**BUG-RC-009 — 0% APY pools ranked as "best".** Turn 7 lines 587 + 591:
Sky Lending WETH and Sky Lending WSTETH both 0.0% APY ranked #3 and #5.
The §3.2 pool ranking formula (`0.4·log(TVL)+0.3·log(7d_vol)+
0.15·fee_apr_30d+0.10·age_yrs+0.05·audit`) is either inactive or has
TVL completely dominating without an APY floor.

**BUG-RC-010 — Suspiciously high APY without yield-trap warning.** Turn
1 lines 19–27: Gmtrade pools 208–264% APY ranked as "best" with only a
generic "HIGH risk" tag. No yield-trap callout, no historical-30d-APY
comparison, no warning about Gmtrade's protocol-specific routing
limitation (which the agent itself reveals in turn 2 line 179).

**BUG-RC-011 — Sentinel scoring absent on every card.** Spec §3 mandates
Safety/Durability/Exit/Confidence 4-axis scoring on every pool /
defi_opportunities / pool_link card. Not visible anywhere in the
transcript. Either backend isn't emitting the sentinel block or the
CardRenderer dropped it.

**BUG-RC-012 — Blocked-state placeholder fields rendered as `0`/`-`.**
Turn 2 lines 189–209: blocker card shows `Signatures 0 · Status blocked
· Risk gate clear · Total Gas - · Chains - · 0s ETA`. The "clear" risk
gate on a blocked card is contradictory; the `0` signatures /
`0s ETA` / `-` totals are meaningless once the plan is blocked and
should be suppressed.

**BUG-RC-013 — Blocker title repeated 3+ times.** Lines 187, 185, 213:
`Gmtrade XAU-USDC` printed once as card title, once as header re-line,
and embedded again inside the body text.

**BUG-RC-014 — Markdown `**bold**` rendered as literal asterisks.** Lines
725, 727, 807, 809: `**Fluid Lending Supply**`, `**Steps**`, `**Blockers**`
visible with the asterisks present. Card body rendering path doesn't
run a markdown pass.

**BUG-RC-015 — Cross-chain context lost.** Turn 2 line 169: user said
`40 usdt on sol`. Agent never asked about USDT on Solana being available
in the wallet, never surfaced a bridge plan, never offered to bridge
from another chain. §7 S5 (cross-chain different-token) flow didn't
fire even though the prompt explicitly cross-chain.

**BUG-RC-016 — No prior-failure learning between turns.** Turn 6 line
421: after two consecutive `cannot access local variable` errors on
pools `7f5c2e8b…` and `7083d6a5…`, agent's next response is the
IDENTICAL 8-pool list that just failed. Both broken pool IDs are
listed AGAIN as "Execution: ready". The "ready" label is lying.

**BUG-RC-017 — Redundant `Open the Execution Plan card above and sign`
filler.** Lines 729 and 811: the card already has a Sign button; the
instruction is noise.

**BUG-RC-018 — Reasoning trace `01`/`02`/`03` exposed.** Lines 813–841:
`🧠 Parsed direct yield execution`, `🧠 Confirming adapter coverage`,
`⚙️ Called build_yield_execution_plan`, `✅ build_yield_execution_plan
completed`, etc. visible in the chat. Should be inside a collapsible
reasoning accordion per §4.

**BUG-RC-019 — "Surfacing alternatives" promise without alternatives.**
Turn 2 lines 181, 216: blocker recovery text says `Pool unavailable —
surfacing alternatives — Pool removed / paused / cap reached.
Alternatives ranked by APR + similarity. Never auto-route — you pick.`
No alternative cards followed in the response.

**BUG-RC-020 — Refusal example mismatches user's prior chain.** Turn 9
line 795: user was looking at an Ethereum plan; refusal example suggests
`Supply 100 USDC to Aave V3 on Base` — wrong chain. Should reuse the
prior plan's chain.

### P2 hygiene

**BUG-RC-021 — Excluded-line wording drift.** "Excluded 25 candidates
that violated the requested…" vs "Excluded 25 candidates that violated
requested…". Same emit done two different ways at two sites.

**BUG-RC-022 — Receipt-token address shown without semantic context.**
Lines 767, 877: `(0x9Fb7b447…)` / `(0xf42f5795…)` listed as "position
token" with no explanation of what to verify against.

**BUG-RC-023 — Generic Enso risk warnings on every card.** Lines 771–775,
881–885: every Enso shortcut card prefixes the same generic warning
text. Not pool-specific; loses signal value.

---

## ROOT-FAILURE TAXONOMY

| Category | What I tested | What I should have tested |
|---|---|---|
| **Matrix (Gate 2)** | Explicit-verb single-turn happy paths (`Supply 100 USDC to Aave V3 on Base`) | Multi-turn natural dialogue: "best pools" → "pick 4" → "execute pool X" → "re-quote", follow-up reference resolution, ambiguous prompts |
| **Playwright (Gate 4)** | Per-card-type DOM rendering, no `undefined`/`NaN`/blank | Cross-field consistency (title vs payload vs pool-id), markdown render, reasoning-trace collapse, blocked-state field suppression, sentinel-scoring presence |
| **Anvil (Gate 5)** | Calldata reverts on fork | Asset-pool matching (USDC intent against WSTETH pool), substitute-protocol detection, position-token semantics check |
| **11-batch audit (Gate 6)** | Spec section LIVE/PARTIAL/MISSING | Did flag §3.1 LiquidityIntent orphan + §6d B-path orphan; I deferred both as "architectural". Tester hit them in turn 1+2. **Severity reclassified to P0.** |
| **Smoke (Gate 1)** | Canonical-leak text doesn't appear | Doesn't probe ambiguous prompts; doesn't probe "re-quote"; doesn't probe execute-by-pool-id route |

**Single root cause behind most P0/P1 bugs**: the agent dispatcher is
regex-based and silently substitutes/coerces intent rather than asking
the user to clarify. The `LiquidityIntent` typed envelope (which would
force structured field extraction with refusal on ambiguity) exists in
`src/agent/intent/lp_intent_extractor.py` but is **never called** from
the production path.

---

## NEW VALIDATION INFRA (must build before claiming tester-ready)

### 1. `scripts/validation/conversation_matrix.py` (NEW)

A matrix-style harness that fires **multi-turn natural-language
conversations** instead of single-turn explicit-verb prompts. Each
conversation has an **LLM judge** asserting per-turn:

- agent intent (parsed protocol/action/asset) matches user intent
- no silent protocol substitution (Aave → Fluid)
- no silent asset substitution (USDC → WSTETH)
- allocation cards emitted when user said "pick N" / "distribute" /
  "allocate" / "split across"
- sentinel scoring present on every opportunity card
- no raw Python exception text in response body
- finite numeric in every time-stamped UI string (no `Infinitys`)
- no duplicate paragraph in same response
- markdown `**bold**` renders as `<strong>`, not literal asterisks
- reasoning trace collapsed (not flat in chat)

Initial conversation set (15-20 conversations, each 4-10 turns):

- C-R01 best-pools → pick-N → allocate-across (must emit allocation)
- C-R02 execute-by-pool-id with id from prior list (must succeed or
  return structured blocker, never raw exception)
- C-R03 re-quote / refresh-sim (must re-simulate prior plan)
- C-R04 protocol typo / under-specification (must disambiguate, never
  substitute silently)
- C-R05 ambiguous "best" without constraints (must ask clarifying
  question OR show diverse risk-tier sample with sentinel scoring)
- C-R06 asset-pool mismatch (USDC ask against WSTETH pool — must refuse
  with `ASSET_POOL_MISMATCH`)
- C-R07 cross-chain implicit ("40 usdt on sol") — must surface bridge
  requirement
- C-R08 follow-up reference ("sign it", "what was the gas?", "execute
  number 3") — must resolve to prior card
- C-R09 prior-failure learning ("any pool that works?") — must NOT
  re-list pools that just errored
- C-R10 sentinel-scoring presence — every defi_opportunities card has
  the 4-axis bar
- C-R11 0% APY filter — listing shouldn't surface 0% APY as "best"
- C-R12 suspicious-APY warning — pools >100% APY trigger yield-trap
  callout
- C-R13 markdown render — agent's `**bold**` headers render as bold
- C-R14 blocker recovery — promised alternatives actually appear
- C-R15 refusal-example chain context — wrong-chain examples don't
  appear in refusal text

### 2. New runtime invariants in `src/agent/runtime_invariants.py`

- **I7 (title/payload consistency)**: every card's title text mentions
  the same protocol+asset that `payload.protocol` and `payload.asset_in`
  declare. Mismatch → replace with `invariant_violation` card carrying
  `INTENT_MISMATCH` code.
- **I8 (sentinel scoring present)**: every `defi_opportunities` / `pool`
  / `pool_link` card with a pool reference includes a `sentinel` block
  with all 4 axes. Missing → emit a degraded card with explicit
  "scoring unavailable" rather than silent omit.
- **I9 (allocation intent fired)**: if user prompt contains "pick N",
  "distribute", "allocate", "split across", and the tool dispatch
  picked anything other than `allocate_portfolio` /
  `generate_allocation`, raise `INTENT_MISMATCH_ALLOCATION` blocker.
- **I10 (asset-pool matching)**: if `asset_in` ≠ pool's declared
  deposit token, refuse with `ASSET_POOL_MISMATCH` blocker showing the
  pool's expected asset.
- **I11 (no raw exception text)**: catch-all wrapper around every tool
  dispatch; any uncaught Python exception becomes a structured
  `invariant_violation` card with code `INTERNAL_ERROR_CAUGHT`. Never
  `cannot access local variable 'X'` text.
- **I12 (time formatting)**: SIM_STALE / freshness / ETA messages must
  contain a finite numeric (regex `\b\d+(\.\d+)?\s*[smhd]\b`); reject
  `Infinitys`, `nan`, `None`, `Infinity`.

### 3. New static-sweep patterns in `scripts/validation/static_sweep.py`

```
AP-RC-001 (P0): Infinitys?\s+old              — BUG-RC-006
AP-RC-002 (P0): cannot access local variable
              |UnboundLocalError
              |NoneType has no attribute
              |UnhandledPromiseRejection      — BUG-RC-003
AP-RC-003 (P1): \*\*[A-Z][^*]*\*\* in card body without <strong>
                                              — BUG-RC-014
AP-RC-004 (P1): same ≥10-token sentence twice in same response
                                              — BUG-RC-007/008
AP-RC-005 (P1): "Excluded \d+ candidates" appearing >1× per response
                                              — BUG-RC-007 verbatim
```

### 4. Playwright additions in `scripts/playwright_browser_smoke.py`

- Per `execution_plan_v3` card: assert title regex contains
  `payload.protocol` AND `payload.asset_in`. Fail with TITLE_MISMATCH
  on divergence.
- Per `defi_opportunities` card: assert sentinel-bar DOM is present and
  shows numeric values for all 4 axes.
- Per text response containing `**bold**`: assert rendered HTML has
  `<strong>` not literal `**`.
- On any `Execute deposit into pool <uuid>` prompt: assert no `[error]`
  console message contains `UnboundLocalError` / `cannot access local
  variable`.
- Multi-turn flow: `best pools` → `pick 4 and allocate $X` → assert
  `allocation` card type emitted (or a clarifying-question text card).
- Per blocker card: assert `0 signatures` / `0s ETA` / `-` totals are
  HIDDEN, not rendered with placeholder values.
- Per refusal text card: assert the example phrase uses the prior
  chain context (no Base example if user was on Ethereum).

### 5. New conversation scenarios in `tests/harness/v4_matrix.py` (category R)

R01–R15 listed above in §1.

---

## FIX-WAVE ORDERING

**Wave RC-α (P0 root cause)**:

1. **Wire `LiquidityIntent` typed envelope as the primary planner** in
   `src/agent/simple_runtime.py`, demoting `_detect_*` regex to a
   pre-filter only. (Phase C P1-C-006 promoted to P0.)
2. **Add catch-all exception wrapper at tool dispatch** that converts
   any uncaught Python exception to a structured `invariant_violation`
   card with code `INTERNAL_ERROR_CAUGHT`. (Fixes BUG-RC-003.)
3. **Fix `Infinitys` formatting** at SIM_STALE/freshness/ETA emission
   sites — find the `f"Simulation is {x}s old"` template that's
   evaluating `x = math.inf` and add a `finite-check` helper.
4. **Add `ASSET_POOL_MISMATCH` blocker** in
   `src/defi/execution/preflight.py` that refuses when `asset_in` ≠
   pool's declared deposit token. (Fixes BUG-RC-002.)
5. **Add allocation-intent recognition** in the intent layer so
   "pick N", "distribute", "allocate", "split across" route to the
   allocation generator. (Fixes BUG-RC-005.)

**Wave RC-β (P1 visible defects)**:

6. **Add sentinel-scoring DOM to defi_opportunities CardRenderer** —
   render the 4-axis bar from `payload.items[i].sentinel`.
7. **Add yield-trap warning** when `apy > 100%` — emit a callout above
   the card.
8. **Add 0% APY filter** at the pool-ranking layer — don't surface
   zero-yield pools as "best" without explicit user request.
9. **Suppress placeholder fields on blocked cards** in
   `ExecutionPlanV3Card` — when status=blocked, hide signatures/gas/
   ETA/risk-gate rather than showing 0/-/clear.
10. **Run markdown pass on card body text** — render `**bold**` as
    `<strong>` in `cardShell` body.
11. **Deduplicate "Excluded N candidates" footer** — pick one emission
    site, remove the other.
12. **Collapse reasoning trace** in `MessageList` — default-collapsed
    `<details>` instead of flat in chat.
13. **Add prior-failure memory** to the dispatcher — when a pool just
    errored, mark it as "tried, failed" in the session memory and
    exclude from subsequent "ready" lists or annotate clearly.
14. **Add re-quote / refresh-sim handler** — natural-language intents
    for refreshing SIM_STALE state without re-typing the full prompt.
15. **Use prior-chain context in refusal examples** — if last plan was
    on Ethereum, refusal example should use Ethereum.

**Wave RC-γ (P2 hygiene)**:

16. Normalise "Excluded N candidates" wording (single source).
17. Annotate position-token addresses with `(receipt token — verify
    Etherscan name matches <protocol>)` context.
18. Replace generic Enso warnings with pool-specific risk callouts.

After Wave RC-α + RC-β land:

- Re-prove all 7 original gates at the new SHA.
- Run the new Gate 8 (conversation matrix) and require ≥95% LLM-judge
  PASS across 15 R-category conversations.
- Re-run the 11-batch audit; P1-C-006 + P1-C-007 + P1-C-009 + P1-C-010
  should all be LIVE.
- **Then and only then** tag `tester-ready-v2`.

---

## HARD RULES (unchanged from V10 + additions)

1. NEVER skip pytest after a code commit.
2. NEVER force-push `main`, skip hooks, or bypass signing.
3. NEVER commit secrets.
4. NEVER deploy to prod.
5. NEVER guess on-chain addresses — WebFetch the official source +
   verify on-chain.
6. NEVER claim "tester-ready" until ALL **8 gates** hold simultaneously
   (the original 7 + new Gate 8 conversation-matrix).
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE
   refire per cycle.
8. All validation against `https://staging.ilyonai.com`. Never prod.
9. All commits on `main`. Do not push to `origin/staging`.
10. NEVER over-claim. Mark PARTIAL as PARTIAL. Mark MISSING as MISSING.
11. **No single tool catches everything.** Matrix+smoke+Playwright+Anvil
    +audit catch syntax; only **conversation-matrix (Gate 8)** catches
    semantic intent failures.
12. **No mechanical-only matrix analysis.** Conversation matrix
    judgements come from LLM-judge prose + per-turn assertions, not
    regex.
13. **No stopping early.** Goal is not met until exit check above holds.
14. **Every P0/P1 from `AI Bug Convo.md` has a pin test** (either
    runtime invariant + assertion test, or conversation-matrix scenario
    + LLM-judge expectation).
15. **Backend changes after `4ddfa52` re-open Gate 2** — must re-prove
    3 consecutive clean matrix passes at the new SHA.
16. **NEW — Phase C P1 items now P0**: P1-C-006 (LiquidityIntent
    wire-up) and P1-C-010 (wrong-spender preflight) cannot remain
    deferred. The tester hit both. Close in Wave RC-α.
17. **NEW — Roll back the `tester-ready` tag.** Replace with
    `pre-real-conversation-validation-v1` so the repo history doesn't
    mislead. Re-tag `tester-ready-v2` only after Gate 8 holds.

---

## FORBIDDEN END-OF-TURN PHRASES

(All from V10, plus the additions.)

- "shipped", "done", "complete", "fully met", "all set", "tester-ready"
  (until ALL 8 green — Gate 8 included)
- "ready for tester" (until Gate 8 ≥95% PASS AND every BUG-RC-001..023
  closed)
- "Playwright covers it" / "Anvil covers it" / "matrix covers it"
  (without conversation-matrix Gate 8 ALL CLEAR)
- "the audit closed it" (when the audit flagged it PARTIAL and you
  deferred — that's NOT closure)
- "edge case" / "rare" / "follow-up" applied to anything in BUG-RC-001
  through BUG-RC-023 — these are first-5-minutes-of-testing bugs
- "architectural rewrite, deferred" — if a real tester hit it, it is
  not deferrable

If you catch one of these → delete the sentence → schedule the wake-up
→ do the next concrete action.

---

## START IMMEDIATELY

```bash
# 1. Confirm state
git log -1 --oneline                  # expect 29dcd27 or later
git tag -l "spec-complete tester-ready pre-real-conversation-validation-v1"
git status

# 2. Roll back the misleading tag
git tag pre-real-conversation-validation-v1 29dcd27
git push origin pre-real-conversation-validation-v1
git tag -d tester-ready
git push origin :tester-ready

# 3. Verify staging
curl -fsS https://staging.ilyonai.com/api/v1/agent-health   # expect 200

# 4. Open and re-read AI Bug Convo.md — every line cited above

# 5. Wave RC-α order:
#    a. Wire LiquidityIntent typed envelope in simple_runtime.py
#    b. Add I11 exception-capture wrapper
#    c. Fix Infinitys formatting (find the template + add finite-check)
#    d. Add I10 ASSET_POOL_MISMATCH preflight
#    e. Add I9 allocation-intent recognition
#    All five need pin tests + commit + push + ONE redeploy + matrix
#    pass at the new SHA.

# 6. Build scripts/validation/conversation_matrix.py + R-category
#    scenarios. Don't dispatch the LLM judge until at least RC-α is in.

# 7. Wave RC-β P1 fixes. Each with pin test.

# 8. Build out Gate 8: conversation matrix + LLM judge.

# 9. Re-prove Gates 1-7 at the new SHA. Then run Gate 8. Then re-audit.

# 10. Only after 8/8 green AND all BUG-RC-001..023 closed:
#     spec(tester-ready-v2): ... [<sha>] + tag tester-ready-v2.
```

---

## ARTEFACT INVENTORY

- `IlyonAi_LP_Execution_Spec.pdf` — sole source of truth (40 pages,
  v1.0)
- `IlyonAi_Development_Plan_v2.md` — 75 V7-XXX tasks
- `AI Bug Convo.md` — **the real-tester transcript with BUG-RC-001
  through BUG-RC-023 grounded in it**
- `docs/SPEC_COVERAGE.md` — coverage ledger
- `docs/matrix-runs/BUG_LEDGER.md` — every P0/P1 with receipts (add a
  BUG-RC section)
- `docs/audit-runs/phase-c-v1-summary.md` — Phase C findings (P1-C-006
  and P1-C-010 promoted to P0)
- `docs/audit-runs/phase-d-d1-status.md` — Phase D D1 status (now
  superseded by this V11)
- `.claude/commands/goal.md` — updated with 8-gate definition
- `.claude/commands/loop-autonomous.md` — updated with conversation
  matrix phase

Continue.
