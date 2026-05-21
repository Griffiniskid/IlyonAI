---
description: IlyonAi production tester-ready. Spec + devplan 100% match in code AND frontend AND on-chain AND real conversation. Tester opens staging, holds a real multi-turn conversation (ambiguous prompts, follow-up references, recovery, allocation), hits 0 bugs and 0 logical issues. Do not stop until all true.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, TaskCreate, TaskUpdate, TaskList, WebFetch, ScheduleWakeup, mcp__codebase-memory-mcp__*, mcp__gitnexus__*
---

# /goal — IlyonAi Tester-Ready Staging (V2 — Real-Conversation Validation)

## The perfect end state

When a human tester opens `https://staging.ilyonai.com` and exercises every
flow that the spec PDF describes — search, allocate, single-pool deposit,
withdraw, exit, claim, cross-chain bridge, session-key install/revoke, LST
stake/unstake, V3/V4 LP NFT mint/refinance, every §13 27-row edge case,
every §7 S1-S15 funding scenario — **and ALSO** holds a multi-turn natural
conversation with ambiguous prompts, follow-up references ("execute pool
X", "re-quote", "sign it"), informal language ("re quote please", "best
pools"), allocation requests ("pick 4 and distribute across them"), and
recovery flows ("any pool that works?"), they hit **0 bugs and 0 logical
issues**:

- Every emitted card renders correctly (no broken layouts, no `undefined`,
  no missing prices, no literal `**bold**` asterisks, no fabricated content
  slipping past the runtime invariant layer, no card whose title says one
  thing and whose description says another, no defi_opportunities card
  missing the sentinel scoring bar).
- Every "Sign" button produces a real wallet popup with a payload that
  **actually executes correctly on-chain** (no token0/token1 inversion, no
  verb-inverted dispatch, no drain-by-MAX_UINT256, no asset-pool mismatch
  where the user asked for USDC and the pool is WSTETH).
- Every agent intent → action is semantically correct: when the user says
  `Supply 100 USDC to Aave V3 on Base`, the response is an Aave V3 plan
  on Base, NOT a silent substitution to Fluid Lending. When the user says
  `pick 4 best pools and allocate $40 across them`, an `allocation` card
  is emitted, NOT a single execute attempt on the first pool.
- Every blocker card shows the correct typed code (UPPER_SNAKE), the
  correct affected_step_ids, a usable recovery CTA, AND when the recovery
  text promises alternatives, the alternative cards actually appear.
- Every internal exception is caught and surfaced as a structured
  `invariant_violation` card — **never** as raw Python text like
  `cannot access local variable 'ExecutionBlocker'`.
- Every time-formatted UI string (`SIM_STALE`, freshness gates, ETA) shows
  a finite numeric (`30s`, `1m 12s`) — **never** `Infinitys` or `nan` or
  `None`.
- The codebase at `HEAD` matches every line of
  `IlyonAi_LP_Execution_Spec.pdf` (v1.0, 40 pages) and
  `IlyonAi_Development_Plan_v2.md` (75 V7-XXX tasks) — verified by a fresh
  12-subagent re-audit run AFTER all wave-1..N fixes shipped. Phase C P1
  items P1-C-006 (`LiquidityIntent` wire-up) and P1-C-010 (wrong-spender
  preflight) **cannot remain deferred** — they're now P0 because the real
  tester hit them.
- All **EIGHT** validation gates run green back-to-back without flapping:
  smoke + matrix passes + drain() invariant log + Playwright + Anvil fork
  + 12-subagent re-audit + SPEC_COVERAGE/BUG_LEDGER receipts **+ Gate 8
  conversation matrix with LLM judge ≥95% PASS**.

## The eight validation gates

1. **Backend canonical-leak smoke** — `scripts/validation/post_deploy_smoke.py`
   runs against staging in ≤120 sec, returns N/N PASS.

2. **Backend matrix Pass A** — 3 consecutive clean Pass A waves on staging
   (532 captures each), static-sweep 0 P0 patterns, regression-sweep ALL
   CLEAR. Same code SHA across all 3 waves.

3. **Backend runtime invariants firing** —
   `docs/matrix-runs/invariant-violations.log` confirms `drain()` hook
   catches the expected structural classes (I1 ready+null-tx, I2
   tx_count↔requires_signature, I3 USD overflow, I4 step-index continuity,
   I6 executable:false ⇒ blocker required, **I7 title/payload
   consistency, I8 sentinel scoring present, I9 allocation intent fired,
   I10 asset-pool matching, I11 no raw exception text, I12 time
   formatting**).

4. **Frontend Playwright** — `scripts/playwright_browser_smoke.py` runs
   against staging, asserts every card type renders, every Sign button
   payload matches the SSE step.transaction EXACTLY, every blocker card
   shows typed code + recovery CTA, no `undefined`/`NaN`/blank states,
   **every defi_opportunities card has sentinel-bar DOM, every
   execution_plan_v3 card's title contains the same protocol+asset its
   payload declares, every blocked card hides placeholder fields, every
   card body Markdown renders as HTML (not literal `**bold**`).**

5. **On-chain fork-mainnet executability** —
   `scripts/anvil_fork_replay.py` forks ethereum/base/arb/opt/polygon/bsc/
   avax mainnets, broadcasts every execution_plan_v3's calldata, asserts
   receipts + balance deltas + **asset-pool matching** (the position
   token returned must match the pool the user thought they were
   entering).

6. **12-subagent codebase re-audit** — 11 batches A-K return 0 PARTIAL +
   0 MISSING + 0 NEW-GAP. **P1-C-006 LiquidityIntent wire-up and
   P1-C-010 wrong-spender preflight cannot remain PARTIAL** — both are
   P0 after `AI Bug Convo.md`.

7. **`docs/SPEC_COVERAGE.md`** updated with a current date + final
   tester-ready commit SHA at 100% LIVE; **`docs/matrix-runs/BUG_LEDGER.md`**
   has an entry for every P0/P1 ever surfaced (audit + matrix waves + fork
   sim + Playwright **+ conversation matrix + BUG-RC-001..023 from
   `AI Bug Convo.md`**).

8. **Conversation matrix with LLM judge (NEW)** —
   `scripts/validation/conversation_matrix.py` runs ≥15 R-category
   multi-turn natural conversations against staging. Per-turn LLM judge
   asserts: agent intent matches user intent, no silent protocol
   substitution, no asset-pool mismatch, no raw exception text, finite
   numeric in all time strings, no duplicate paragraphs, no markdown
   leak, sentinel scoring present on opportunity cards, allocation card
   on multi-pool requests, prior-failure memory across turns. PASS bar:
   **≥95% of turn-level assertions** AND **zero P0 turn-level failures**.

## Final commit + tag

```
spec(tester-ready-v2): 75/75 V7-XXX + 12-subagent re-audit clean + 3 matrix passes + Playwright N/N + Anvil fork N/N + conversation matrix N/N + 0 frontend bugs + BUG-RC-001..023 closed [<sha>]
```

Tag as `tester-ready-v2` (NOT `tester-ready` — the V1 tag has been rolled
back to `pre-real-conversation-validation-v1` because it was claimed
prematurely) and confirm staging is deployed at exactly that SHA.

## Persistence mandate

Do not stop, summarize, or hand back until every claim above is verifiably
true. Not when smoke passes alone. Not when only 3 matrix passes clean.
Not when only the backend is green. **Only when all eight gates above
hold simultaneously, with receipts, AND every BUG-RC-001 through
BUG-RC-023 in `AI Bug Convo.md` is closed with a pin test.**

When a turn leaves work pending, `ScheduleWakeup` with
`<<autonomous-loop-dynamic>>` to fire `/loop-autonomous`. When a background
subagent completes, the harness re-fires you — continue. Catch yourself
writing "shipped," "done," "complete," "good progress," "scheduled wakeup,"
"I'll continue when…", "edge case," "deferred", "architectural rewrite" →
delete, schedule the wake-up, do the next action.

## Hard never-violate

- All validation against `https://staging.ilyonai.com`. Never prod.
- Commits on `main` only. Never `origin/staging`, force-push, `--no-verify`,
  bypass signing, commit secrets, or deploy prod.
- Never guess on-chain addresses — WebFetch the official source + verify
  on-chain.
- Never claim "tester-ready-v2" until ALL 8 gates above hold simultaneously
  AND every BUG-RC item closed.
- Spec PDF is canonical. When plan/coverage/code/tests disagree, PDF wins.
- One push + one redeploy + one refire per cycle. Mid-pass redeploy =
  cascade kill.
- **No single tool is enough alone.** Matrix-sweep+smoke catch ~50%;
  fork-sim + Playwright + 12-subagent re-audit catch the structural
  rest; **conversation matrix + LLM judge catches the semantic intent
  failures the other tools miss.** All required.
- Every fix has a pin test. Every BUG-RC has either a runtime invariant
  assertion test OR a conversation-matrix scenario.
- VPS prod dir `~/ai-sentinel` is read-only — never touch. Staging dir
  is `~/ai-sentinel-staging`.
- **Phase C P1 items P1-C-006 (LiquidityIntent wire-up) and P1-C-010
  (wrong-spender preflight) are P0 — not deferrable.**
- **Roll back the misleading `tester-ready` tag** — replace with
  `pre-real-conversation-validation-v1`. Re-tag `tester-ready-v2` only
  after all 8 gates green AND every BUG-RC closed.

## Authoritative sources

- Spec PDF: `IlyonAi_LP_Execution_Spec.pdf` (40 pages, v1.0 · 2026-05-14)
- Dev plan: `IlyonAi_Development_Plan_v2.md` (75 V7-XXX tasks)
- **Real-tester evidence: `AI Bug Convo.md` — BUG-RC-001 through
  BUG-RC-023 grounded in line citations.**
- Coverage ledger: `docs/SPEC_COVERAGE.md`
- Bug ledger: `docs/matrix-runs/BUG_LEDGER.md`
- Validation infra: `scripts/validation/static_sweep.py`,
  `post_deploy_smoke.py`, `regression_sweep.py`,
  `conversation_matrix.py` (NEW), `src/agent/runtime_invariants.py`
- Frontend test: `scripts/playwright_browser_smoke.py`
- On-chain sim: `scripts/anvil_fork_replay.py`
- Matrix harness: `tests/harness/v4_runner.py` (use `--parallel 6` for
  ~25-30 min/wave) + `tests/harness/v4_matrix.py` (add R-category
  conversations)
- Continuation prompt for autonomous mode: `.claude/commands/loop-autonomous.md`
- Latest resume prompt: `RESUME_V11_PROMPT.md`
