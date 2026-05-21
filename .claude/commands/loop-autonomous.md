---
description: Continuation loop for the IlyonAi tester-ready-v2 goal. Re-fires the agent until ALL 8 gates (smoke + matrix 3x + invariants I1-I12 + Playwright + Anvil + 11-batch re-audit + ledger receipts + conversation matrix LLM judge) hold simultaneously AND every BUG-RC-001..023 from AI Bug Convo.md is closed. Never stops until tester holds a real multi-turn conversation and sees 0 bugs.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, TaskCreate, TaskUpdate, TaskList, WebFetch, ScheduleWakeup, mcp__codebase-memory-mcp__*, mcp__gitnexus__*
---

# /loop-autonomous — Continue IlyonAi Tester-Ready-V2 Goal

You are mid-pursuit of the goal defined in `.claude/commands/goal.md`. This
command fires when the prior turn left work pending. Do not summarize or
hand back to the user — **continue executing**.

The V1 `tester-ready` tag was rolled out too early. The very first
real-tester conversation (`AI Bug Convo.md`) surfaced 23 distinct bugs
across protocol intent, card consistency, exception handling, time
formatting, allocation flow, sentinel scoring, and Markdown rendering.
**Read `RESUME_V11_PROMPT.md` if you've lost context** — it holds the
full bug catalogue and root-cause taxonomy.

The current work is **Waves RC-α/β/γ** + building Gate 8 conversation
matrix.

---

## ALWAYS DO FIRST (cold-resume hygiene)

1. **Check task state**: `TaskList` — what's `in_progress`? what's
   `pending`? what's the next unblocked task in ID order?
2. **Check git state**: `git log -1 --oneline && git status` —
   uncommitted changes from a prior turn? HEAD ahead of origin?
3. **Check tags**: `git tag -l "spec-complete pre-real-conversation-validation-v1 tester-ready-v2"`
   — `tester-ready-v2` is the finish line; the V1 `tester-ready` tag
   should be gone (rolled back to `pre-real-conversation-validation-v1`).
4. **Check staging health**: `curl -fsS https://staging.ilyonai.com/api/v1/agent-health`
   — if not 200, pause and investigate before any matrix/Playwright/
   conversation fire.
5. **Check recent work artefacts**:
   - `ls docs/matrix-runs/ 2>/dev/null | tail -5` — last pass/wave dir
   - `ls docs/playwright-runs/ 2>/dev/null | tail -5` — last Playwright
   - `ls docs/anvil-fork-runs/ 2>/dev/null | tail -5` — last fork-sim
   - `ls docs/audit-runs/ 2>/dev/null | tail -5` — last re-audit
   - `ls docs/conversation-runs/ 2>/dev/null | tail -5` — last
     conversation-matrix run (NEW)
   - `tail -50 docs/matrix-runs/BUG_LEDGER.md 2>/dev/null` — bugs
     mid-fix, especially the BUG-RC-* section
   - `git log --oneline -10` — what landed since the goal restarted
6. **Pick up where you left off** — do not re-do completed work. Phases
   are checkpointed via task state, git commits, and run directories.

---

## EXIT CHECK — STOP only when ALL 8 hold simultaneously

- [ ] **Gate 1**: `scripts/validation/post_deploy_smoke.py` returns N/N
      PASS against staging.
- [ ] **Gate 2**: 3 consecutive clean Pass A waves at the **same code
      SHA** with static-sweep 0 P0 and regression-sweep ALL CLEAR.
- [ ] **Gate 3**: `docs/matrix-runs/invariant-violations.log` shows
      `drain()` hook catching the expected structural classes; I1-I12
      all wired.
- [ ] **Gate 4**: `scripts/playwright_browser_smoke.py` returns N/N PASS
      including title/payload consistency check, sentinel-bar presence,
      Markdown render, blocked-state field suppression, asset-pool
      matching, and no raw exception in console.
- [ ] **Gate 5**: `scripts/anvil_fork_replay.py` runs on every
      execution_plan_v3 from the latest matrix pass + asserts
      asset-pool matching (position token matches user-intent asset).
- [ ] **Gate 6**: 11 read-only subagents return 0 PARTIAL + 0 MISSING +
      0 NEW-GAP. **P1-C-006 + P1-C-010 must be LIVE, not deferred.**
- [ ] **Gate 7**: `docs/SPEC_COVERAGE.md` updated with current date +
      the final tester-ready-v2 SHA at 100% LIVE;
      `docs/matrix-runs/BUG_LEDGER.md` has entries for every P0/P1 ever
      surfaced including BUG-RC-001..023 with file:line fix evidence.
- [ ] **Gate 8 (NEW)**: `scripts/validation/conversation_matrix.py`
      runs ≥15 R-category conversations with per-turn LLM-judge
      assertions. PASS bar: ≥95% turn-level assertions AND zero P0
      turn-level failures.
- [ ] **Final commit landed**:
      `spec(tester-ready-v2): 75/75 V7-XXX + 12-subagent re-audit clean
      + 3 matrix passes + Playwright N/N + Anvil fork N/N + conversation
      matrix N/N + 0 frontend bugs + BUG-RC-001..023 closed [<sha>]`,
      tagged `tester-ready-v2`, staging deployed at that exact SHA.

If any are not yet true, **continue working**.

---

## DECISION TREE — what to do this turn

```
git status dirty?
  → finish/commit/push before anything else

Wave RC-α (P0 root cause) incomplete?
  → priority order:
    1. Wire LiquidityIntent typed envelope as primary planner
       (src/agent/simple_runtime.py), demoting _detect_* regex to
       pre-filter only. Closes BUG-RC-001 + BUG-RC-004 + BUG-RC-005.
    2. Add catch-all exception wrapper at tool dispatch — uncaught
       Python becomes INTERNAL_ERROR_CAUGHT invariant_violation card.
       Closes BUG-RC-003.
    3. Fix Infinitys formatting at SIM_STALE/freshness/ETA sites with
       finite-check helper. Closes BUG-RC-006.
    4. Add ASSET_POOL_MISMATCH preflight in
       src/defi/execution/preflight.py. Closes BUG-RC-002.
    5. Add allocation-intent recognition ("pick N" / "distribute" /
       "allocate" / "split across" → allocation generator). Closes
       BUG-RC-005.
  Each needs pin test + commit + push + ONE redeploy + matrix pass at
  new SHA. After all 5: matrix MUST stay clean across 3 consecutive
  passes (re-opens Gate 2).

Conversation matrix infra not built?
  → build scripts/validation/conversation_matrix.py
  → add R-category to tests/harness/v4_matrix.py (R01-R15)
  → wire LLM judge with per-turn assertion checklist
  → dry-run against staging at current SHA to baseline

Wave RC-β (P1 visible defects) pending?
  → priority order (each commit→ONE redeploy→re-run conversation matrix
    + Playwright):
    6. Sentinel-scoring DOM in defi_opportunities CardRenderer
    7. Yield-trap warning when apy > 100%
    8. 0% APY filter at pool-ranking layer
    9. Suppress placeholder fields on blocked cards
    10. Markdown pass on card body text
    11. Deduplicate "Excluded N candidates" footer
    12. Collapse reasoning trace in MessageList
    13. Add prior-failure memory to dispatcher
    14. Add re-quote / refresh-sim handler
    15. Use prior-chain context in refusal examples

Wave RC-γ (P2 hygiene) pending?
  → priority order:
    16. Normalise "Excluded N candidates" wording (single source)
    17. Annotate position-token addresses with semantic context
    18. Replace generic Enso warnings with pool-specific risk callouts

All 18 BUG-RC fixes shipped, conversation matrix built?
  → re-run all 8 gates fresh against current SHA:
    - Gate 1 smoke
    - Gate 2 3x matrix
    - Gate 3 invariants log (I1-I12 firing or quiet — expected)
    - Gate 4 Playwright (with new assertions)
    - Gate 5 Anvil with asset-pool match
    - Gate 6 11-batch re-audit (P1-C-006 + P1-C-010 must be LIVE now)
    - Gate 7 ledger update
    - Gate 8 conversation matrix LLM judge ≥95%
  → if any flap: triage which gate, return to that wave
  → if all 8 simultaneously green AND all BUG-RC closed:
    - update SPEC_COVERAGE.md → 100% with date + tester-ready-v2 SHA
    - confirm BUG_LEDGER.md has BUG-RC-001..023 closed entries
    - final commit on main: spec(tester-ready-v2): ... [<sha>]
    - tag tester-ready-v2
    - confirm staging deployed at that SHA
    - final report to user (counts: bugs found per phase, gates green,
      coverage delta, SHA + tag, conversation-matrix LLM-judge score)
    - STOP (do not schedule another wake-up)
```

---

## CADENCE — when to use ScheduleWakeup vs continue immediately

**Continue immediately (no wake-up)** if:
- A background subagent just finished and your re-fire was triggered by
  its completion notification (the harness re-fires you for free)
- You have an uncommitted change to finish
- You just received a Playwright/Anvil/audit/findings/matrix/
  conversation-matrix result you need to act on

**Schedule a wake-up** at the end of the turn if:
- You're waiting on a long external operation the harness cannot notify
  you about (matrix run on VPS, staging redeploy, Anvil fork sim batch,
  conversation-matrix LLM-judge batch on VPS, CI run)
- You just dispatched parallel subagents and your next action depends
  on all of them returning

Delay rules (clamped to 60-3600s):
- **60-270s** when actively polling external state the harness can't
  track (use sparingly)
- **1200-1800s** default for idle waits (matrix run, redeploy heartbeat,
  parallel-subagent batch, conversation-matrix batch)
- **Never 300s** (worst-of-both cache cliff)

Pass the literal sentinel `<<autonomous-loop-dynamic>>` as the `prompt`
argument so the runtime resolves it to this command body.

---

## TOOLING REMINDERS

### Deploy commands (canonical)
```bash
git push origin main
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  git stash push -u -m 'wave-rc-X' 2>&1 | tail -2 && \
  git pull --ff-only origin main 2>&1 | tail -2 && \
  docker compose --env-file deploy/staging/compose.env up -d --build api"
curl -fsS https://staging.ilyonai.com/api/v1/agent-health   # expect 200
```

### Smoke / sweep
```bash
PYTHONIOENCODING=utf-8 python scripts/validation/post_deploy_smoke.py
python scripts/validation/static_sweep.py docs/matrix-runs/passA-waveX
python -m scripts.validation.regression_sweep docs/matrix-runs/passA-waveX
```

### Parallel matrix fire
```bash
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  rm -rf docs/matrix-runs/passA-waveX && mkdir -p docs/matrix-runs/passA-waveX && \
  export MATRIX_OUT_ROOT=docs/matrix-runs/passA-waveX && \
  nohup python3 -u -m tests.harness.v4_runner --all --parallel 6 --delay 0.3 \
    > /tmp/matrix-waveX.log 2>&1 < /dev/null & disown"
# ~25-35 min; schedule wakeup 1800s
```

### Conversation matrix (NEW — Gate 8)
```bash
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  nohup python3 -u scripts/validation/conversation_matrix.py \
    --judge-model gpt-4o-mini --conversations R01,R02,...,R15 \
    --out docs/conversation-runs/<ts> \
    > /tmp/convmatrix.log 2>&1 < /dev/null & disown"
# Expect 15-30 min; LLM-judge prose per turn + per-turn assertion list.
```

### Playwright iteration
```bash
PYTHONIOENCODING=utf-8 python scripts/playwright_browser_smoke.py
# Artefacts → docs/playwright-runs/<ts>/
```

### Anvil fork sim
```bash
PYTHONIOENCODING=utf-8 python scripts/extract_execution_plans.py docs/matrix-runs/passA-waveX -o docs/anvil-fork-runs/waveX-plans.json --signable-only
ssh ilyonai-vps "cd ~/ai-sentinel-staging && python3 scripts/anvil_fork_replay.py docs/anvil-fork-runs/waveX-plans.json"
```

### Subagent dispatch (Gate 6 re-audit)
- Use `Agent` tool, `subagent_type=general-purpose`
- One agent per batch (A-K)
- Brief contains: spec sections to audit, src/ path pointers,
  SPEC_COVERAGE claims to verify, return format

---

## HARD RULES (re-read every turn — these never change)

1. NEVER skip pytest after a code commit.
2. NEVER force-push `main`, skip hooks (`--no-verify`), or bypass signing.
3. NEVER commit secrets (`deploy/staging/app.env`,
   `deploy/staging/assistant.env`, `deploy/prod/assistant.env` — already
   gitignored).
4. NEVER deploy to prod (`~/ai-sentinel` on VPS — touch nothing).
5. NEVER guess on-chain addresses — WebFetch the official source +
   verify on-chain.
6. NEVER claim "tester-ready-v2" / "done" / "complete" until ALL 8
   exit-check boxes hold simultaneously AND every BUG-RC-001..023
   closed.
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE
   refire per cycle.
8. All validation against `https://staging.ilyonai.com`. NEVER prod.
9. All commits on `main`. Do not push to `origin/staging`.
10. NEVER over-claim. Mark PARTIAL as PARTIAL. Mark MISSING as MISSING.
11. **No single tool catches everything.** Matrix+smoke ~50%; fork-sim
    + Playwright + 12-subagent re-audit catch structural rest;
    **conversation matrix (Gate 8) catches semantic intent failures the
    other tools miss.** All required.
12. **No mechanical-only analysis.** Conversation-matrix judgements
    come from LLM-judge prose + per-turn assertion checklist, not
    regex.
13. **No stopping early.** Goal is not met until exit check above
    holds.
14. Every fix has a pin test. Every BUG-RC has either a runtime
    invariant assertion test OR a conversation-matrix scenario.
15. **Backend changes after the SHA at which Gate 2 was last clean
    re-open Gate 2** — must re-prove 3 consecutive clean matrix passes
    at the new SHA before claiming tester-ready-v2.
16. **Phase C P1-C-006 (LiquidityIntent wire-up) and P1-C-010
    (wrong-spender preflight) are P0 now — not deferrable.**
17. **The `tester-ready` V1 tag is rolled back. Replace with
    `pre-real-conversation-validation-v1`. Re-tag `tester-ready-v2`
    only after all 8 gates green AND every BUG-RC closed.**

---

## FORBIDDEN END-OF-TURN PHRASES

Catch yourself before writing any of these — they signal premature stop
or unjustified deferral:

- "shipped", "done", "complete", "fully met", "all set", "tester-ready",
  "tester-ready-v2" (until ALL 8 green AND every BUG-RC closed)
- "ready for tester" (until Gate 8 ≥95% PASS AND every BUG-RC-001..023
  closed)
- "Playwright covers it" / "Anvil covers it" / "matrix covers it"
  (without conversation-matrix Gate 8 ALL CLEAR)
- "the audit closed it" (when the audit flagged it PARTIAL and you
  deferred — that's NOT closure)
- "edge case" / "rare" / "follow-up" applied to anything in
  BUG-RC-001..023 — these are first-5-minutes-of-testing bugs
- "architectural rewrite, deferred" / "non-tester-visible" — if a real
  tester hit it, it is not deferrable
- "status:", "summary:", "good progress"
- "moving to", "now", "continuing with"
- "should work", "likely fixes", "this addresses"
- "I'll continue when…", "session ended at…", "good stopping point"
- "scheduled wakeup" (just do it, don't announce it)

If you catch one of these → delete the sentence → schedule the wake-up
→ do the next concrete action.

---

## ESCALATION (only when truly blocked, not before)

Stop and ask the user **only** when:
- Staging healthcheck returns non-200 for >3 consecutive checks (10+
  min) and the cause is non-obvious — production-style ops issue, not
  a bug.
- A subagent / fork sim reports a financial-loss-class bug whose fix
  requires user-judgement (e.g. a new on-chain contract address must
  be authorized).
- Disk fills on VPS / repo / matrix captures (>90% full).
- A phase has been re-firing for >10 cycles without convergence —
  there may be a systemic spec gap that needs human review.
- A required external tool (foundry, playwright browser, an LLM-judge
  API key for Gate 8) cannot be installed on the local machine and
  there is no equivalent already on the VPS.

In all other cases: **continue working autonomously**.

---

## ARTEFACT INVENTORY (read these if you need refresher)

- `IlyonAi_LP_Execution_Spec.pdf` — sole source of truth (40 pages,
  v1.0)
- `IlyonAi_Development_Plan_v2.md` — 75 V7-XXX tasks
- `RESUME_V11_PROMPT.md` — current real-conversation-validation
  resume prompt with full BUG-RC catalogue
- **`AI Bug Convo.md` — verbatim transcript with BUG-RC-001..023
  grounded in line citations**
- `docs/SPEC_COVERAGE.md` — coverage ledger
- `docs/matrix-runs/BUG_LEDGER.md` — every P0/P1 with receipts; add
  BUG-RC section as fixes land
- `docs/matrix-runs/passA-wave{1..N}/` — captures + sweeps
- `docs/matrix-runs/invariant-violations.log` — drain() catches
- `docs/conversation-runs/<ts>/` — Gate 8 LLM-judge runs (NEW)
- `docs/audit-runs/phase-c-v1-summary.md` — Phase C findings
- `docs/audit-runs/phase-d-d1-status.md` — Phase D state (superseded
  by V11)
- `.claude/commands/goal.md` — 8-gate end-state definition
