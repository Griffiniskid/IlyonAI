---
description: IlyonAi tester-ready staging. Spec + devplan 100% match in code AND frontend AND on-chain. Tester opens staging, runs every flow, hits 0 bugs and 0 logical issues. Do not stop until all true.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, TaskCreate, TaskUpdate, TaskList, WebFetch, ScheduleWakeup, mcp__codebase-memory-mcp__*, mcp__gitnexus__*
---

# /goal — IlyonAi Tester-Ready Staging

## The perfect end state

When a human tester opens `https://staging.ilyonai.com` and exercises every
flow that the spec PDF describes — search, allocate, single-pool deposit,
withdraw, exit, claim, cross-chain bridge, session-key install/revoke, LST
stake/unstake, V3/V4 LP NFT mint/refinance, every §13 27-row edge case,
every §7 S1-S15 funding scenario — they hit **0 bugs and 0 logical issues**:

- Every emitted card renders correctly in the web UI (no broken layouts,
  no `undefined`, no missing prices, no fabricated content slipping past
  the runtime invariant layer)
- Every "Sign" button produces a real wallet popup (MetaMask, Phantom,
  Coinbase Wallet) with a payload that **actually executes correctly
  on-chain** (verified via fork-mainnet simulation: calldata succeeds,
  receipts match, balances move as promised — no token0/token1 inversion,
  no verb-inverted dispatch, no drain-by-MAX_UINT256)
- Every blocker card shows the correct typed code (UPPER_SNAKE), the
  correct affected_step_ids, and a usable recovery CTA
- The codebase at `HEAD` matches every line of
  `IlyonAi_LP_Execution_Spec.pdf` (v1.0, 40 pages) and
  `IlyonAi_Development_Plan_v2.md` (75 V7-XXX tasks) — verified by a
  fresh 12-subagent re-audit run AFTER all wave-1..N fixes shipped
- All seven validation gates run green back-to-back without flapping:
  smoke + matrix passes + drain() invariant log + Playwright + Anvil fork
  + 12-subagent re-audit + SPEC_COVERAGE/BUG_LEDGER receipts

## The seven validation gates

1. **Backend canonical-leak smoke** — `scripts/validation/post_deploy_smoke.py`
   runs against staging in ≤60 sec, returns 32/32 PASS (or N/N PASS if
   probes were added).
2. **Backend matrix Pass A** — 3 consecutive clean Pass A waves on staging
   (532 captures each), static-sweep 0 P0 patterns, regression-sweep ALL
   CLEAR. Same code SHA across all 3 waves.
3. **Backend runtime invariants firing** — `docs/matrix-runs/invariant-violations.log`
   confirms `drain()` hook catches any composed-plan ready+null-tx /
   `executable:false` references / USD overflows that producers fail to
   filter.
4. **Frontend Playwright** — `scripts/playwright_browser_smoke.py` runs
   against staging, asserts every card type renders, every Sign button
   generates a wallet popup with the EXACT payload from the SSE card (no
   UI-side re-encoding), every blocker card shows the typed code + recovery
   CTA, no `undefined`/`NaN`/blank states surface in any of 30+ scripted
   flows.
5. **On-chain fork-mainnet executability** — `scripts/anvil_fork_sim.py`
   forks ethereum/base/arbitrum mainnets, impersonates the test wallet,
   broadcasts every emitted execution_plan_v3's calldata in order, asserts
   each step succeeds with the expected receipt + balance delta. Catches
   PancakeSwap V3 token0/token1 inversion, Balancer exit-as-deposit, Aave
   V3 withdraw(0) silent drain, any structural calldata bug a regex sweep
   can't see.
6. **12-subagent codebase re-audit** — repeat of the V8 6-batch read-only
   audit, this time against the post-wave-12 codebase. Returns 0 PARTIAL +
   0 MISSING + 0 NEW-GAP across all 11 batches.
7. **`docs/SPEC_COVERAGE.md`** updated with a 2026-05-21+ date + the final
   tester-ready commit SHA showing 100% LIVE; **`docs/matrix-runs/BUG_LEDGER.md`**
   has an entry for every P0/P1 ever surfaced (audit + matrix waves + fork
   sim + Playwright).

## Final commit + tag

```
spec(tester-ready): 75/75 V7-XXX + 12-subagent re-audit clean + 3 matrix passes + Playwright N/N + Anvil fork N/N + 0 frontend bugs [<sha>]
```

Tag as `tester-ready` and confirm staging is deployed at exactly that SHA.

## Persistence mandate

Do not stop, summarize, or hand back until every claim above is verifiably
true. Not when smoke passes alone. Not when only 3 matrix passes clean.
Not when only the backend is green. **Only when all seven gates above hold
simultaneously, with receipts.**

When a turn leaves work pending, `ScheduleWakeup` with
`<<autonomous-loop-dynamic>>` to fire `/loop-autonomous`. When a background
subagent completes, the harness re-fires you — continue. Catch yourself
writing "shipped," "done," "complete," "good progress," "scheduled wakeup,"
"I'll continue when…" → delete, schedule the wake-up, do the next action.

## Hard never-violate

- All validation against `https://staging.ilyonai.com`. Never prod
  (`https://ilyonai.com`).
- Commits on `main` only. Never `origin/staging`, force-push, `--no-verify`,
  bypass signing, commit secrets, or deploy prod.
- Never guess on-chain addresses — WebFetch the official source + verify
  on-chain.
- Never claim "tester-ready" until ALL 7 gates above hold simultaneously.
- Spec PDF is canonical. When plan/coverage/code/tests disagree, PDF wins.
- One push + one redeploy + one refire per cycle. Mid-pass redeploy =
  cascade kill.
- **No single tool is enough alone.** Matrix-sweep+smoke catch ~80%;
  fork-mainnet sim + Playwright + 12-subagent re-audit catch the
  structural rest. All five mechanical tools + the human-judgement audit
  must run.
- Every fix has a pin test.
- VPS prod dir `~/ai-sentinel` is read-only — never touch. Staging dir
  is `~/ai-sentinel-staging`.

## Authoritative sources

- Spec PDF: `IlyonAi_LP_Execution_Spec.pdf` (40 pages, v1.0 · 2026-05-14)
- Dev plan: `IlyonAi_Development_Plan_v2.md` (75 V7-XXX tasks)
- Coverage ledger: `docs/SPEC_COVERAGE.md`
- Bug ledger: `docs/matrix-runs/BUG_LEDGER.md`
- Validation infra: `scripts/validation/static_sweep.py`,
  `post_deploy_smoke.py`, `regression_sweep.py`,
  `src/agent/runtime_invariants.py`
- Frontend test: `scripts/playwright_browser_smoke.py`
- On-chain sim: `scripts/anvil_fork_sim.py`
- Matrix harness: `tests/harness/v4_runner.py` (use `--parallel 6` for
  ~25-30 min/wave) + `tests/harness/v4_matrix.py`
- Continuation prompt for autonomous mode: `.claude/commands/loop-autonomous.md`
- Latest resume prompt: `RESUME_V10_PROMPT.md`
