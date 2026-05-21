# RESUME V10 — TESTER-READY STAGING

You are continuing an autonomous build of **IlyonAi**. The backend
matrix-fix loop is complete (`spec(complete)` commit `edadddf` tagged on
`main`, 3 consecutive clean Pass A matrix passes against
`https://staging.ilyonai.com`). The next phase brings the staging
deployment to **tester-ready** state: zero frontend bugs, every operation
actually executable on-chain, and a fresh 12-subagent re-audit confirming
the post-wave-12 codebase still matches the spec end-to-end.

This prompt is self-contained — do not look for prior conversation
context. Read it end-to-end before doing anything.

---

## CURRENT STATE (as of `edadddf`)

- **Backend** at HEAD `9edaf83` is matrix-pass-clean (waves 12, 13, 14
  all clean: static-sweep 0 P0 patterns, regression-sweep ALL CLEAR,
  smoke gate 32/32 PASS). Staging deployed at `9edaf83`.
- **Validation infrastructure** shipped:
  - `scripts/validation/static_sweep.py` — 30+ regex catalogue
  - `scripts/validation/post_deploy_smoke.py` — 32 canonical-leak probes
  - `scripts/validation/regression_sweep.py` — closed-bug regression scan
  - `src/agent/runtime_invariants.py` + `StreamCollector.drain()` hook
  - `tests/harness/v4_runner.py --parallel N` (6x speedup)
- **Pin tests**: 158+ green across `tests/defi/test_wave{4..11}_fixes.py`,
  `test_runtime_invariants.py`, `test_freeform_tx_state_guard_wave5.py`,
  `test_drain_risk_withdraw_zero.py`, `test_aave_v3_native_withdraw.py`,
  `test_erc4626_lifecycle.py`, `test_plan_projection_jumps.py`,
  `test_blocker_code_normalizer.py`, `test_err_envelope_normalizer.py`,
  `test_bug_e_002_guest_debridge_guard.py`.

## WHAT'S NOT YET VALIDATED

1. **Frontend rendering** — every validation so far has been SSE/JSON-
   level. The web UI (Next.js) renders the cards. Testers will see the
   UI, not the SSE. Unknown unknowns: card layout breakage, missing CTA
   buttons, blocker prose rendered as code, sign button payload mismatch.
2. **On-chain executability** — every plan emits calldata but we have
   NOT proven calldata actually works on real chains. Known suspects:
   PancakeSwap V3 token0/token1 inversion (would revert on mint),
   Balancer joinPool param ordering, Aave V3 `withdraw_all=true` semantics
   under real receipt-log parsing, V3 NFT mint with stale tick range.
3. **Post-wave-12 codebase drift from spec** — V8 12-subagent audit was
   run before the wave-1..12 fix waves. New code shipped since (runtime
   invariant layer, verb-inversion guard, user_message thread-through,
   sanitizer expansions) hasn't been audited against the spec.

## VALIDATION GATES TO MEET (from `.claude/commands/goal.md`)

1. Backend smoke 32/32 PASS — current ✓
2. Backend matrix 3 consecutive cleans — current ✓
3. Backend runtime invariants firing log shows expected catches — current ✓
4. **Frontend Playwright N/N PASS** — pending
5. **On-chain fork-mainnet executability** — pending
6. **12-subagent codebase re-audit (post-wave-12)** — pending
7. **SPEC_COVERAGE.md + BUG_LEDGER.md receipts updated to tester-ready** — pending

Final commit + tag:
```
spec(tester-ready): 75/75 V7-XXX + 12-subagent re-audit clean + 3 matrix passes + Playwright N/N + Anvil fork N/N + 0 frontend bugs [<sha>]
```

Tag `tester-ready` and verify staging is deployed at exactly that SHA.

---

## EXECUTION PLAN

### Phase A — Frontend Playwright validation (gate 4)

`scripts/playwright_browser_smoke.py` already exists with mocked Phantom +
MetaMask wallet providers. Extend it to cover every canonical card type:

- `defi_opportunities` — pool list renders, sentinel scores visible
- `allocation` — table rows + blended APY + recovery CTA
- `execution_plan_v3` — all step types (approve/supply/bridge/stake/
  swap/wrap/withdraw/join_pool), Sign button present per signable step
- `pool_link` — link button works, exec_status:"link_only" badge shown
- `pool_deposit_v3` — range slider interactive, tick math correct
- `swap_quote` — quote price + slippage rendered
- `balance_report` — chain rollup + token list rendered (NOT raw JSON)
- `invariant_violation` — typed code visible, no broken layout, CTA usable
- `text` / `no_change` — plain prose renders

Plus 30+ scripted user flows from `tests/harness/v4_matrix.py` chains
(reuse the Chain definitions). Each flow:
1. Type the prompt(s) for each turn
2. Wait for SSE complete
3. Assert card DOM present
4. Click signable buttons → assert wallet popup fires with payload
   matching the SSE card's `step.transaction` field exactly (no UI
   re-encoding)
5. Screenshot on failure for triage

Pass criterion: N/N flows succeed, no console errors, no visual regressions
against baseline screenshots, no `undefined`/`NaN`/blank states.

### Phase B — Anvil fork-mainnet executability (gate 5)

`scripts/anvil_fork_sim.py` already exists with anvil-spawn + balance/
storage manipulation. Extend to cover every emitted execution_plan_v3
from the matrix-runs/passA-wave14 captures:

For each chain (ethereum/base/arbitrum/polygon/optimism/avalanche/bsc):
1. `anvil --fork-url <chain rpc> --port <chain port>`
2. Fund the test wallet `0xaaaa...aaaa` with native + ERC20 balances
   per the plan's `assets_required`
3. Broadcast each step's `transaction` field in order (impersonating the
   wallet)
4. Assert each receipt: `status:success`, expected logs present,
   expected balance delta on the test wallet
5. If any step reverts or produces unexpected balance: log to a fork-sim
   report and fail the gate

Pass criterion: every execution_plan_v3 from the latest matrix pass
executes correctly on fork. Catches:
- PancakeSwap V3 token0/token1 inversion (mint reverts)
- Balancer exit-as-deposit (would deposit wrong)
- Aave V3 withdraw(0) drain (test wallet balance goes to zero)
- V3 NFT mint with stale tick range (mint reverts on price out of bounds)

### Phase C — 12-subagent codebase re-audit (gate 6)

Dispatch 11 read-only subagents (one per batch from V8 + one cross-cutter):

- Batch A: §1-§3 (intent extraction, dispatcher, primitives)
- Batch B: §4-§5 (state machine, card schemas)
- Batch C: §6a-§6c (V3/V4 native exec, composed plans)
- Batch D: §6d-§6g (source-token, APR-CDF, recovery, verify)
- Batch E: §7 S1-S15 funding scenarios
- Batch F: §8 chains + §9 notifier
- Batch G: §10 wallets + AA + session keys
- Batch H: §11 D.1-D.8 safety invariants
- Batch I: §12 deployment + §14 monitoring
- Batch J: §13 27-row edge case appendix
- Batch K: cross-cutting (BUG_LEDGER closed-bug receipts, anti-pattern
  grep, runtime invariant layer ↔ D.1-D.8 mapping, validation infra
  alignment with spec)

Each subagent returns: per-item LIVE/PARTIAL/MISSING + evidence.

Pass criterion: every item LIVE. If any PARTIAL/MISSING surfaces, fix-wave
+ re-audit.

### Phase D — Integrated gate run

Once Phases A/B/C all pass:
1. Run smoke gate against staging
2. Run one final matrix wave (parallel, 30 min)
3. Run static-sweep + regression-sweep + Playwright + Anvil fork
4. Confirm all 7 gates simultaneously green
5. Final commit + tag

---

## OPERATIONAL PATTERNS (proven across 14 fix waves)

### Cycle pattern

For each fix wave (rare now — only if Phase A/B/C surface a defect):
1. Code fix + pin test + adjacent regression sweep (5-30 min)
2. `git commit + push` (1 min)
3. VPS pull + `docker compose --env-file deploy/staging/compose.env up -d --build api` (3-5 min)
4. `curl staging /api/v1/agent-health` → 200 (10 sec)
5. `python scripts/validation/post_deploy_smoke.py` → 32/32 PASS (1 min)
6. `python -m tests.harness.v4_runner --all --parallel 6 --delay 0.3` (25-30 min)
7. `python scripts/validation/static_sweep.py <wave_dir>` + `python -m scripts.validation.regression_sweep <wave_dir>` (2 sec)
8. Inspect deltas; if regression, fix-wave; else move forward.

### Deploy commands (canonical)

```bash
# Local
git push origin main

# VPS
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  git stash push -m 'matrix-vps' --include-untracked -- docs/matrix-runs/ && \
  git pull --ff-only origin main && \
  docker compose --env-file deploy/staging/compose.env up -d --build api"

# Verify
curl -fsS https://staging.ilyonai.com/api/v1/agent-health  # expect 200

# Smoke gate (post-deploy validation)
PYTHONIOENCODING=utf-8 python scripts/validation/post_deploy_smoke.py
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

### SCP captures back

```bash
scp -r -q ilyonai-vps:~/ai-sentinel-staging/docs/matrix-runs/passA-waveN/. \
  docs/matrix-runs/passA-waveN/
```

### Sweep + analyze

```bash
python scripts/validation/static_sweep.py docs/matrix-runs/passA-waveN
python -m scripts.validation.regression_sweep docs/matrix-runs/passA-waveN
# Both < 2 seconds. Report at <waveN>/static-sweep.md + regression-sweep.md
```

### Playwright (Phase A)

```bash
# Once-only setup: pip install playwright && playwright install chromium
python scripts/playwright_browser_smoke.py
# Extends existing script with per-card-type assertions + matrix-chain flows
```

### Anvil fork sim (Phase B)

```bash
# Once-only setup: install foundry (curl -L https://foundry.paradigm.xyz | bash; foundryup)
python scripts/anvil_fork_sim.py docs/matrix-runs/passA-wave14
# Reads every execution_plan_v3 from the wave dir; forks chain; broadcasts.
```

### Subagent dispatch (Phase C)

Use `Agent` tool with `subagent_type=general-purpose`. One agent per batch.
Each agent gets:
- Brief covering exactly which spec sections to audit
- Path pointers to relevant `src/` modules
- The `docs/SPEC_COVERAGE.md` current claims to verify
- The instruction: return LIVE/PARTIAL/MISSING per item + evidence

Subagents have `Write` blocked → return inline; main thread persists.

---

## VPS QUIRKS (don't rediscover)

1. **Git pull aborts on local matrix-runs** — VPS keeps untracked matrix
   capture dirs. Always stash first:
   `git stash push -m 'matrix-vps' --include-untracked -- docs/matrix-runs/`
2. **Env files**: api container reads `${APP_ENV_FILE:-.env}`. Root `.env`
   on VPS sets `APP_ENV_FILE=deploy/staging/app.env`. **But `docker compose
   --env-file <X>` REPLACES root .env loading.** Fix: `compose.env` carries
   `APP_ENV_FILE=deploy/staging/app.env`. Canonical: `docker compose --env-file
   deploy/staging/compose.env up -d --build api`.
3. **Rate limit on staging api**: 5000/hour per IP (bumped from 200). VPS
   root `.env` has `BLINKS_RATE_LIMIT_PER_HOUR=5000`. If you see `{"error":
   "Rate limit exceeded: 200/hour"}`, api container is reading wrong .env.
4. **VPS has no `node`** — can't run TS or Node tests there. The sidecar
   js tests run from `services/solana-yield-builder/` only.
5. **`pkill -9 -f v4_runner` over SSH may exit 255 even on success.**
   Verify with `pgrep -f v4_runner` after.
6. **Per-turn latency is real (5-15s for live LLM calls)**, so a parallel
   matrix takes 25-30 min minimum even with 6 workers.
7. **Cyrillic Windows paths**: the local repo path uses `Документи` —
   bash quoting can mangle. Use forward slashes + escape correctly.
8. **GitNexus index stale hook** fires after most bash commands. It's
   informational only — does NOT block the goal. Reindex at the very end
   if convenient, not during fix waves.

---

## HARD RULES (re-read every turn — these never change)

1. NEVER skip pytest after a subagent commit
2. NEVER force-push `main`, NEVER skip hooks (`--no-verify`), NEVER bypass signing
3. NEVER commit secrets (`deploy/staging/app.env`, `deploy/staging/assistant.env`,
   `deploy/prod/assistant.env` — already gitignored)
4. NEVER deploy to prod (`~/ai-sentinel` on VPS — touch nothing)
5. NEVER guess on-chain addresses — `WebFetch` the official source + verify on-chain
6. NEVER claim "tester-ready" without ALL 7 gates green simultaneously
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE refire per cycle
8. All matrix validation against `staging.ilyonai.com`. Never `ilyonai.com`
9. All commits on `main`. Do not push to `origin/staging`
10. NEVER over-claim. Mark PARTIAL as PARTIAL. Mark MISSING as MISSING
11. **No single tool catches everything.** Matrix+smoke ~80%; fork sim +
    Playwright + 12-subagent re-audit catch the rest. All required
12. **No stopping early.** Goal is not met until exit criteria above hold.
    Self-fire via `ScheduleWakeup` to continue

---

## FORBIDDEN END-OF-TURN PHRASES

Catch yourself before writing any of these — they signal premature stop:

- "shipped", "done", "complete", "fully met", "all set", "tester-ready" (until ALL 7 green)
- "status:", "summary:", "good progress"
- "moving to", "now", "continuing with"
- "should work", "likely fixes", "this addresses"
- "deferred", "phase X handles", "acceptable for now", "good enough"
- "I'll continue when…", "session ended at…", "good stopping point"
- "scheduled wakeup" (just do it, don't announce it)

If you catch one of these → delete the sentence → schedule the wake-up →
do the next concrete action.

---

## ARTIFACT INVENTORY (read these if you need refresher)

- `IlyonAi_LP_Execution_Spec.pdf` — sole source of truth (40 pages, v1.0)
- `IlyonAi_Development_Plan_v2.md` — 75 V7-XXX tasks
- `docs/SPEC_COVERAGE.md` — coverage ledger (currently 100% per V8;
  needs re-confirmation after wave-1..12 code)
- `docs/matrix-runs/BUG_LEDGER.md` — source of truth for every bug
- `docs/matrix-runs/passA-wave{1..14}/` — captures + findings + sweep reports
- `docs/matrix-runs/invariant-violations.log` — runtime invariant catches
- `.claude/commands/goal.md` — tester-ready end-state definition
- `.claude/commands/loop-autonomous.md` — autonomous continuation skill

## START IMMEDIATELY

```bash
# 1. Confirm state
git log -1 --oneline                    # expect edadddf or later
git tag -l "spec-complete tester-ready" # both should be local-tagged
git status

# 2. Verify staging
ssh ilyonai-vps "cd ~/ai-sentinel-staging && git log -1 --oneline"
curl -fsS https://staging.ilyonai.com/api/v1/agent-health   # expect 200

# 3. Run smoke gate (sanity check current state)
PYTHONIOENCODING=utf-8 python scripts/validation/post_deploy_smoke.py
# Expect 32/32 PASS

# 4. Phase A: extend Playwright tests to cover every card type + matrix
#    flow. Run against staging. Iterate until N/N.

# 5. Phase B: extend Anvil fork sim to broadcast every wave-14 execution
#    plan against forked mainnet. Iterate until every plan succeeds.

# 6. Phase C: dispatch 11 subagent re-audit. Iterate until 0 PARTIAL +
#    0 MISSING.

# 7. Phase D: integrated gate run (smoke + matrix + sweeps + Playwright
#    + Anvil + re-audit) all green simultaneously.

# 8. Final commit + tag
```

---

## DO NOT

- Don't repeat the wave-1..12 backend fix loop — it's done. Use the
  existing infrastructure.
- Don't change validation infrastructure unless an actual bug requires it.
- Don't fire the matrix from local Windows — fire from VPS only.
- Don't run `pkill -9 -f v4_runner` over SSH if `pgrep` returns 0 —
  empty kill returns exit 1 → SSH exits 255.
- Don't waste cycles re-investigating the test wallet (`0xaaaa…`). It's
  the matrix harness wallet, not a placeholder leak.
- Don't re-deploy to staging in the middle of a matrix run.
- Don't skip Playwright/Anvil/re-audit phases. The goal explicitly
  requires all three.

Continue.
