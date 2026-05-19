---
description: IlyonAi production-readiness. Every line of the spec PDF implemented + 3 clean matrix passes on staging + every bug logged. Do not stop until all true.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, TaskCreate, TaskUpdate, TaskList, WebFetch, ScheduleWakeup, mcp__codebase-memory-mcp__*, mcp__gitnexus__*
---

# /goal — IlyonAi Production-Readiness

## The perfect end state

The codebase implements **every line** of `IlyonAi_LP_Execution_Spec.pdf` (sole source of truth) — every §1-§14, every row of the §13 27-row edge-case appendix, every S1-S15 funding scenario, every D.1-D.8 safety invariant, every native LST protocol, every one of the 10 new EVM chains, every field of every typed schema. Where spec says "must," code does. Where spec says "blocker fires," it fires. Where spec defines an invariant, a pin test asserts it. Nothing missing, partial, stubbed, placeholdered, hardcoded, commented-out, or paths-only-on-Linux.

`IlyonAi_Development_Plan_v2.md` shows all 75 V7-XXX tasks DONE. `docs/SPEC_COVERAGE.md` reads 100% LIVE with date, SHA that took it there, and the 3 matrix-pass SHAs that proved it. When any artifact disagrees with the PDF, the PDF wins.

Real users on `https://staging.ilyonai.com` get the right answer on every spec-defined flow. The 120-chain × ≥4-turn matrix at `tests/harness/v4_matrix.py` fired **three consecutive times** with no P0/P1 outside `tests/harness/v4_gaps.py EXPECTED_BLOCKED`. Captures live under `docs/matrix-runs/passA-waveN/`, `passB-wave1/`, `passC-wave1/` with per-category LLM-judged findings showing 0 P0/P1.

Every bug — audit, matrix, anti-pattern grep — is in `docs/matrix-runs/BUG_LEDGER.md`: pass/chain/turn, severity, spec ref (§X.Y), root cause, fix file:line, commit SHA, before/after SSE quote. Nothing offline. The ledger is the receipt.

Grep `confirmed=False` in safety paths → zero. `_PLACEHOLDER_` → zero. `TODO|FIXME` in `src/shield/`, `src/auth/`, `src/defi/execution/` → zero. V4 hook allowlist has verified addresses (not zero-address). Wallet signing uses real wagmi/Phantom paths. Verify() returns `confirmed=True` from real receipt-log parsing in every adapter the watcher fires.

## How to know it's true

12-subagent re-verification (same as V6_GAP_ANALYSIS.md) returns **0 PARTIAL + 0 MISSING + 0 NEW-GAP** every section. Matrix clean 3× in a row. Anti-pattern grep at zero. Final commit on `main`: `spec(complete): 75/75 V7-XXX + 12-subagent clean + 3 matrix passes [<shaA>, <shaB>, <shaC>]`, and that SHA is what staging is deployed at.

## Persistence mandate

**Do not stop, summarize, or hand back until every claim above is verifiably true.** Not when 9 PARTIALs closed. Not when one matrix pass clean. Not when audit is mostly-DONE. Only when all hold, with receipts.

When a turn leaves work pending, `ScheduleWakeup` with `<<autonomous-loop-dynamic>>` to fire `/loop-autonomous`. When a background subagent completes, the harness re-fires you — continue. Catch yourself writing "shipped," "done," "complete," "good progress," "scheduled wakeup," "I'll continue when…" → delete, schedule the wake-up, do the next action.

Plan → `RESUME_V8_PROMPT.md` + `.claude/commands/loop-autonomous.md`. Spec → `IlyonAi_LP_Execution_Spec.pdf`. Ledger → `IlyonAi_Development_Plan_v2.md`.

## Hard never-violate

- Matrix only against `https://staging.ilyonai.com`. Never prod.
- Commits on `main` only. Never `origin/staging`, force-push, `--no-verify`, bypass signing, commit secrets, or deploy prod.
- Never guess on-chain addresses — WebFetch the official source.
- Never claim "complete" without 12-subagent clean **+** 3 clean matrix passes **+** grep at zero.
- Spec PDF is canonical. When plan/coverage/code/tests disagree, PDF wins.
- One push + one redeploy + one refire per cycle. Mid-pass redeploy = cascade kill.
- No mechanical matrix analysis. Findings come from LLM-subagent judgement on raw SSE, not regex.
- Every fix has a pin test.
