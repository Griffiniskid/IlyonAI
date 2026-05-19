---
description: Continuation loop for the IlyonAi production-readiness goal. Re-fires the agent until 100% spec match + 3 consecutive clean matrix passes + bug ledger complete. Never stops until all gates hold.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, TaskCreate, TaskUpdate, TaskList, WebFetch, ScheduleWakeup, mcp__codebase-memory-mcp__*, mcp__gitnexus__*
---

# /loop-autonomous — Continue IlyonAi Goal

You are mid-pursuit of the goal defined in `.claude/commands/goal.md`. This command fires when the prior turn left work pending. Do not summarize or hand back to the user — **continue executing**.

---

## ALWAYS DO FIRST (cold-resume hygiene)

1. **Check task state**: `TaskList` — what's `in_progress`? what's `pending`? what's the next unblocked task in ID order?
2. **Check git state**: `git log -1 --oneline && git status` — are there uncommitted changes from a prior turn? Is HEAD ahead of origin?
3. **Check staging health**: `curl -fsS https://staging.ilyonai.com/api/v1/agent-health` — if not 200, pause and investigate before any matrix fire.
4. **Check recent work artefacts**:
   - `ls docs/matrix-runs/ 2>/dev/null | tail -5` — what was the last pass/wave?
   - `tail -50 docs/matrix-runs/BUG_LEDGER.md 2>/dev/null` — what bugs are mid-fix?
   - `git log --oneline -10` — what landed since the goal started?
5. **Pick up where you left off** — do not re-do completed work. The audit + fix pattern is checkpointed via task state, git commits, and matrix-run directories.

---

## EXIT CHECK — STOP only when ALL of these hold

- [ ] Phase 2 audit (6 read-only subagents covering all 11 batches) returned 0 PARTIAL + 0 MISSING on the **most recent** run
- [ ] `docs/SPEC_COVERAGE.md` shows 100% with a date + commit SHA from the current resume cycle
- [ ] `docs/matrix-runs/` contains 3 consecutive clean pass directories (e.g. `passA-wave3/`, `passB-wave1/`, `passC-wave1/`) where each has 9 `findings-<category>.md` files reporting 0 P0/P1 outside the `tests/harness/v4_gaps.py` allowlist
- [ ] `docs/matrix-runs/BUG_LEDGER.md` has an entry for every P0/P1 surfaced across all passes, each with: root cause, fix file:line, commit SHA, before/after SSE quote
- [ ] No `_PLACEHOLDER_` strings, no `confirmed=False` verify() stubs, no commented-out hook addresses, no hard-coded Linux paths in tests (grep these explicitly)
- [ ] Final commit landed: `spec(complete): 75/75 V7-XXX gaps closed + 6-subagent re-verification clean + 3 consecutive matrix passes [<sha-A>, <sha-B>, <sha-C>]`

If any are not yet true, **continue working**.

---

## DECISION TREE — what to do this turn

```
git status dirty?
  → finish/commit before anything else

phase 1 (gap closure) incomplete?
  → dispatch next pending wave (1=safety, 2=spec-exit, 3=cleanup)
  → 5/4/3 parallel subagents per wave
  → aggregate → regression sweep → commit → push → ONE staging redeploy

phase 2 (audit) returned PARTIAL or MISSING on last run?
  → dispatch fix-subagents targeting only the open items
  → re-run audit subagent for that batch
  → loop

phase 3 matrix in flight?
  → if background run pending, do not poll — schedule wake-up 1200-1800s
  → if matrix complete and findings not analyzed → dispatch 9 category reviewers
  → if findings analyzed and not de-duped → de-dupe + classify P0/P1/P2
  → if P0/P1 not fixed → dispatch fix wave
  → if fix wave landed → push, redeploy staging, refire matrix as next wave/pass
  → if 3 consecutive clean → proceed to final commit

phase 4 ready (3 clean passes done)?
  → re-run phase 2 audit one final time
  → update SPEC_COVERAGE.md → 100%
  → final commit
  → final report to user (bug ledger summary, total bugs found, coverage delta)
  → STOP (do not schedule another wake-up)
```

---

## CADENCE — when to use ScheduleWakeup vs continue immediately

**Continue immediately (no wake-up)** if:
- A background subagent just finished and your re-fire was triggered by its completion notification (the harness re-fires you for free)
- You have an uncommitted change to finish
- You just received an audit/findings/matrix result you need to act on

**Schedule a wake-up** at the end of the turn if:
- You're waiting on a long external operation the harness cannot notify you about (matrix run on VPS, staging redeploy, CI run)
- You just dispatched parallel agents and your next action depends on all of them returning

Delay rules (clamped to 60-3600s):
- **60-270s** when actively polling external state the harness can't track (use sparingly)
- **1200-1800s** default for idle waits (matrix run, redeploy heartbeat)
- **Never 300s** (worst-of-both cache cliff)

Pass the literal sentinel `<<autonomous-loop-dynamic>>` as the `prompt` argument so the runtime resolves it to this command body. Reason field: one specific sentence (e.g. "watching matrix pass B fire on VPS, expect ~25 min").

---

## HARD RULES (re-read every turn — these never change)

1. NEVER skip pytest after a subagent commit
2. NEVER force-push `main`, skip hooks (`--no-verify`), or bypass signing
3. NEVER commit secrets
4. NEVER deploy to prod
5. NEVER guess on-chain addresses — WebFetch the official source + verify on chain
6. NEVER claim "done" / "complete" / "100%" until **all** exit-check boxes hold
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE refire per cycle.
8. All matrix validation against `https://staging.ilyonai.com`. NEVER `https://ilyonai.com`.
9. All commits on `main`. Do not push to `origin/staging`.
10. NEVER over-claim. Mark PARTIAL as PARTIAL. Mark MISSING as MISSING.
11. **No mechanical analysis.** Matrix findings come from LLM-subagent judgement, not regex.
12. **No stopping early.** Goal is not met until the exit check above holds. Self-fire via `ScheduleWakeup` to continue.

---

## FORBIDDEN END-OF-TURN PHRASES

Catch yourself before writing any of these — they signal you're about to stop prematurely:

- "shipped", "done", "complete", "fully met", "all set"
- "status:", "summary:", "good progress"
- "moving to", "now", "continuing with"
- "should work", "likely fixes", "this addresses"
- "deferred", "phase X handles", "acceptable for now", "good enough"
- "I'll continue when…", "session ended at…", "good stopping point"
- "scheduled wakeup" (just do it, don't announce it)

If you catch one of these → delete the sentence → schedule the wake-up → do the next concrete action.

---

## ESCALATION (only when truly blocked, not before)

Stop and ask the user **only** when:
- Staging healthcheck returns non-200 for >3 consecutive checks (10+ min) and the cause is non-obvious — production-style ops issue, not a bug
- A subagent reports a financial-loss-class bug whose fix requires user-judgement (e.g. a new on-chain contract address must be authorized)
- Disk fills on VPS / repo / matrix captures (>90% full)
- The matrix has been re-firing for >10 cycles without convergence — there may be a systemic spec gap that needs human review

In all other cases: **continue working autonomously**.
