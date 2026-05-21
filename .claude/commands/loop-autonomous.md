---
description: Continuation loop for the IlyonAi tester-ready staging goal. Re-fires the agent until all 7 gates (backend smoke + matrix 3x + invariants + Playwright + Anvil fork + 12-subagent re-audit + ledger receipts) hold simultaneously. Never stops until tester opens staging and sees 0 bugs.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, TaskCreate, TaskUpdate, TaskList, WebFetch, ScheduleWakeup, mcp__codebase-memory-mcp__*, mcp__gitnexus__*
---

# /loop-autonomous — Continue IlyonAi Tester-Ready Goal

You are mid-pursuit of the goal defined in `.claude/commands/goal.md`. This
command fires when the prior turn left work pending. Do not summarize or
hand back to the user — **continue executing**.

The backend matrix-fix loop is COMPLETE (`spec-complete` tag at `edadddf`,
3 consecutive clean Pass A waves). The remaining work is **Phases A/B/C/D**
of the tester-ready plan: Playwright (gate 4), Anvil fork-mainnet (gate 5),
12-subagent re-audit (gate 6), integrated gate run (all 7 green).

---

## ALWAYS DO FIRST (cold-resume hygiene)

1. **Check task state**: `TaskList` — what's `in_progress`? what's `pending`?
   what's the next unblocked task in ID order?
2. **Check git state**: `git log -1 --oneline && git status` — uncommitted
   changes from a prior turn? HEAD ahead of origin?
3. **Check tags**: `git tag -l "spec-complete tester-ready"` — both should
   eventually be local-tagged; `tester-ready` is the finish line.
4. **Check staging health**: `curl -fsS https://staging.ilyonai.com/api/v1/agent-health`
   — if not 200, pause and investigate before any matrix/Playwright fire.
5. **Check recent work artefacts**:
   - `ls docs/matrix-runs/ 2>/dev/null | tail -5` — last pass/wave dir
   - `ls docs/playwright-runs/ 2>/dev/null | tail -5` — last Playwright run
   - `ls docs/anvil-fork-runs/ 2>/dev/null | tail -5` — last fork-sim run
   - `ls docs/audit-runs/ 2>/dev/null | tail -5` — last re-audit run
   - `tail -50 docs/matrix-runs/BUG_LEDGER.md 2>/dev/null` — bugs mid-fix
   - `git log --oneline -10` — what landed since the goal restarted
6. **Pick up where you left off** — do not re-do completed work. Phases are
   checkpointed via task state, git commits, and run directories.

---

## EXIT CHECK — STOP only when ALL 7 hold simultaneously

- [ ] **Gate 1**: `scripts/validation/post_deploy_smoke.py` returns N/N PASS
      against staging (current baseline 32/32)
- [ ] **Gate 2**: 3 consecutive clean Pass A waves at the **same code SHA**
      with static-sweep 0 P0 and regression-sweep ALL CLEAR (today: waves
      12/13/14 at `9edaf83` — re-prove if backend changes for any Phase A/B
      fix)
- [ ] **Gate 3**: `docs/matrix-runs/invariant-violations.log` shows `drain()`
      hook catching the expected structural classes; no silent producers
- [ ] **Gate 4**: `scripts/playwright_browser_smoke.py` returns N/N PASS
      against staging covering every card type + 30+ matrix-chain flows;
      every Sign button payload matches the SSE card EXACTLY; no
      `undefined`/`NaN`/blank states in any flow
- [ ] **Gate 5**: `scripts/anvil_fork_sim.py` broadcasts every
      `execution_plan_v3` from the latest matrix pass on forked mainnet for
      each chain; every step receipt succeeds with the expected balance
      delta; no token0/token1 inversion, exit-as-deposit, or
      withdraw(0)-style drains
- [ ] **Gate 6**: 11 read-only subagents (batches A-K) return 0 PARTIAL + 0
      MISSING + 0 NEW-GAP against the post-wave-N codebase
- [ ] **Gate 7**: `docs/SPEC_COVERAGE.md` updated with a ≥2026-05-21 date +
      the final tester-ready SHA at 100% LIVE; `docs/matrix-runs/BUG_LEDGER.md`
      has an entry for every P0/P1 surfaced across audit + matrix waves +
      fork sim + Playwright
- [ ] **Final commit landed**: `spec(tester-ready): 75/75 V7-XXX + 12-subagent
      re-audit clean + 3 matrix passes + Playwright N/N + Anvil fork N/N + 0
      frontend bugs [<sha>]`, tagged `tester-ready`, staging deployed at that
      exact SHA

If any are not yet true, **continue working**.

---

## DECISION TREE — what to do this turn

```
git status dirty?
  → finish/commit/push before anything else

Phase A (Playwright) not yet N/N?
  → next iteration:
    - Read scripts/playwright_browser_smoke.py
    - If coverage gap: extend with next card type or matrix-chain flow
    - Run against staging
    - If failures: triage (UI bug? sign-payload mismatch? render bug?)
      - UI/frontend bug → fix in web/, push, redeploy, re-run
      - Backend SSE bug → adds a row to BUG_LEDGER, fix in src/,
        push, redeploy, then re-prove Gate 2 + Gate 3 too
    - If all flows green: commit Playwright artefacts + advance to Phase B

Phase B (Anvil fork) not yet N/N?
  → next iteration:
    - Read scripts/anvil_fork_sim.py
    - If coverage gap: extend to cover next chain or plan type
    - Pick latest matrix pass dir; iterate every emitted execution_plan_v3
    - For each chain: fork, fund test wallet, broadcast plan in order
    - If any step reverts or balance delta wrong:
      - log to BUG_LEDGER (P0 — financial-loss class)
      - fix in src/defi/execution/adapters/<chain>.py
      - add pin test
      - push, redeploy, re-prove Gate 2 + Gate 3 + Gate 4 + replay this plan
    - If all plans succeed on all chains: commit fork-sim artefacts +
      advance to Phase C

Phase C (12-subagent re-audit) not yet 0/0/0?
  → next iteration:
    - If no subagents in flight: dispatch all 11 batches in parallel
      via Agent tool (subagent_type=general-purpose), each with brief
      covering exact spec sections + relevant src/ paths + SPEC_COVERAGE
      claims to verify; each returns LIVE/PARTIAL/MISSING + evidence
    - If batches in flight: schedule wakeup 1200-1800s; do not poll
    - If batches returned with any PARTIAL/MISSING:
      - dispatch fix-subagents targeting only the open items
      - re-run audit subagent for that batch only
      - loop
    - If all 11 batches 0/0/0: advance to Phase D

Phase D (integrated gate run) ready?
  → run gates 1-3 fresh against current SHA, plus Playwright + Anvil
  → if any flap: triage which gate, return to that phase
  → if all 7 simultaneously green:
    - update SPEC_COVERAGE.md → 100% with date + tester-ready SHA
    - confirm BUG_LEDGER.md has every P0/P1 from all phases
    - final commit on main: spec(tester-ready): ... [<sha>]
    - tag tester-ready
    - confirm staging is deployed at that SHA
    - final report to user (counts: bugs found per phase, gates green,
      coverage delta, SHA + tag)
    - STOP (do not schedule another wake-up)
```

---

## CADENCE — when to use ScheduleWakeup vs continue immediately

**Continue immediately (no wake-up)** if:
- A background subagent just finished and your re-fire was triggered by
  its completion notification (the harness re-fires you for free)
- You have an uncommitted change to finish
- You just received a Playwright/Anvil/audit/findings/matrix result you
  need to act on

**Schedule a wake-up** at the end of the turn if:
- You're waiting on a long external operation the harness cannot notify
  you about (matrix run on VPS, staging redeploy, Anvil fork sim batch,
  CI run)
- You just dispatched parallel subagents and your next action depends on
  all of them returning

Delay rules (clamped to 60-3600s):
- **60-270s** when actively polling external state the harness can't
  track (use sparingly — only when a state change is imminent)
- **1200-1800s** default for idle waits (matrix run, redeploy heartbeat,
  parallel-subagent batch)
- **Never 300s** (worst-of-both cache cliff — cache miss without amortizing)

Pass the literal sentinel `<<autonomous-loop-dynamic>>` as the `prompt`
argument so the runtime resolves it to this command body. Reason field:
one specific sentence (e.g. "waiting on 11 re-audit subagents to return,
expect ~20 min").

---

## TOOLING REMINDERS (proven across 14 backend waves)

### Deploy commands (canonical)
```bash
git push origin main
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  git stash push -m 'matrix-vps' --include-untracked -- docs/matrix-runs/ && \
  git pull --ff-only origin main && \
  docker compose --env-file deploy/staging/compose.env up -d --build api"
curl -fsS https://staging.ilyonai.com/api/v1/agent-health  # expect 200
```

### Smoke / sweep
```bash
PYTHONIOENCODING=utf-8 python scripts/validation/post_deploy_smoke.py
python scripts/validation/static_sweep.py docs/matrix-runs/passA-waveN
python -m scripts.validation.regression_sweep docs/matrix-runs/passA-waveN
```

### Parallel matrix fire
```bash
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  export MATRIX_OUT_ROOT=docs/matrix-runs/passA-waveN && \
  mkdir -p \$MATRIX_OUT_ROOT && \
  nohup python3 -u -m tests.harness.v4_runner --all --parallel 6 --delay 0.3 \
    > /tmp/matrix-passA-waveN.log 2>&1 < /dev/null & disown"
# ~25-30 min; schedule wakeup 1800s
```

### Phase A — Playwright iteration
```bash
# Once-only: pip install playwright && playwright install chromium
python scripts/playwright_browser_smoke.py
# Artefacts → docs/playwright-runs/<timestamp>/
```

### Phase B — Anvil fork sim
```bash
# Once-only: curl -L https://foundry.paradigm.xyz | bash; foundryup
python scripts/anvil_fork_sim.py docs/matrix-runs/passA-wave14
# Artefacts → docs/anvil-fork-runs/<timestamp>/
```

### Phase C — Subagent dispatch
- Use `Agent` tool, `subagent_type=general-purpose`
- One agent per batch (A-K). Brief contains: spec sections to audit,
  src/ path pointers, SPEC_COVERAGE claims to verify, return format
  (LIVE/PARTIAL/MISSING + evidence per item)
- Subagents have `Write` blocked — they return inline; main thread persists

---

## HARD RULES (re-read every turn — these never change)

1. NEVER skip pytest after a code commit
2. NEVER force-push `main`, skip hooks (`--no-verify`), or bypass signing
3. NEVER commit secrets (`deploy/staging/app.env`, `deploy/staging/assistant.env`,
   `deploy/prod/assistant.env` — already gitignored)
4. NEVER deploy to prod (`~/ai-sentinel` on VPS — touch nothing)
5. NEVER guess on-chain addresses — WebFetch the official source + verify
   on-chain
6. NEVER claim "tester-ready" / "done" / "complete" until ALL 7 exit-check
   boxes hold simultaneously
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE
   refire per cycle
8. All validation against `https://staging.ilyonai.com`. NEVER prod
   (`https://ilyonai.com`)
9. All commits on `main`. Do not push to `origin/staging`
10. NEVER over-claim. Mark PARTIAL as PARTIAL. Mark MISSING as MISSING
11. **No single tool catches everything.** Matrix+smoke ~80%; fork-sim +
    Playwright + 12-subagent re-audit catch the structural rest. All
    required
12. **No mechanical matrix analysis.** Matrix findings come from
    LLM-subagent judgement on raw SSE, not regex (sweeps are
    regression-guardrails, not primary triage)
13. **No stopping early.** Goal is not met until exit check above holds.
    Self-fire via `ScheduleWakeup` to continue
14. Every fix has a pin test
15. **Backend changes after `9edaf83` re-open Gate 2** — must re-prove 3
    consecutive clean matrix passes at the new SHA before claiming
    tester-ready

---

## FORBIDDEN END-OF-TURN PHRASES

Catch yourself before writing any of these — they signal premature stop:

- "shipped", "done", "complete", "fully met", "all set", "tester-ready"
  (until ALL 7 green)
- "status:", "summary:", "good progress"
- "moving to", "now", "continuing with"
- "should work", "likely fixes", "this addresses"
- "deferred", "phase X handles", "acceptable for now", "good enough"
- "I'll continue when…", "session ended at…", "good stopping point"
- "scheduled wakeup" (just do it, don't announce it)
- "ready for tester" (until tag pushed)
- "Playwright covers it" / "Anvil covers it" (until N/N receipts on disk)

If you catch one of these → delete the sentence → schedule the wake-up →
do the next concrete action.

---

## ESCALATION (only when truly blocked, not before)

Stop and ask the user **only** when:
- Staging healthcheck returns non-200 for >3 consecutive checks (10+ min)
  and the cause is non-obvious — production-style ops issue, not a bug
- A subagent / fork sim reports a financial-loss-class bug whose fix
  requires user-judgement (e.g. a new on-chain contract address must be
  authorized, or a protocol behaves contrary to its published docs)
- Disk fills on VPS / repo / matrix captures (>90% full)
- A phase has been re-firing for >10 cycles without convergence — there
  may be a systemic spec gap that needs human review
- A required external tool (foundry, playwright browser) cannot be
  installed on the local machine and there is no equivalent already on
  the VPS

In all other cases: **continue working autonomously**.

---

## ARTEFACT INVENTORY (read these if you need refresher)

- `IlyonAi_LP_Execution_Spec.pdf` — sole source of truth (40 pages, v1.0)
- `IlyonAi_Development_Plan_v2.md` — 75 V7-XXX tasks
- `RESUME_V10_PROMPT.md` — current tester-ready resume prompt
- `docs/SPEC_COVERAGE.md` — coverage ledger
- `docs/matrix-runs/BUG_LEDGER.md` — every P0/P1 with receipts
- `docs/matrix-runs/passA-wave{1..14}/` — captures + sweeps
- `docs/matrix-runs/invariant-violations.log` — drain() catches
- `.claude/commands/goal.md` — 7-gate end-state definition
