# RESUME V9 — MATRIX FIX-LOOP CONTINUATION

You are resuming an autonomous build of **IlyonAi**. The validation-gate
audit (12-subagent re-verification of V7-001..V7-075) returned CLEAN
during V8. The matrix-fix loop is now the only thing standing between
the current state and the `spec(complete)` final commit. This prompt is
self-contained — do not look for prior conversation context.

---

## ENVIRONMENT

- Repo: `C:\Users\griff\Документи\IlyonAI` on `main`
- HEAD at session start: **`231c299`** (Pass-A wave-4 fixes: scratchpad-strip chokepoint + withdraw(0) drain-guard)
- VPS: `ssh ilyonai-vps`. Staging dir `~/ai-sentinel-staging`. Prod dir `~/ai-sentinel` — **NEVER TOUCH.**
- Staging URL: `https://staging.ilyonai.com` (health endpoint `/api/v1/agent-health`)
- Prod URL: `https://ilyonai.com` — **never fire validation requests at this.**
- Test wallets (hardcoded in `tests/harness/v4_runner.py:35-36`):
  - EVM: `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` (40 'a' chars — **NOT a placeholder, the matrix test wallet**)
  - Solana: `5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L`
- All commits land on `main`. Do not push to `origin/staging` (it exists but is unused).

## VPS QUIRKS (learned the hard way — don't repeat the discovery)

1. **Git pull aborts on local matrix-runs** — VPS keeps untracked matrix capture dirs (the matrix runner writes there). Always stash first:
   ```bash
   ssh ilyonai-vps "cd ~/ai-sentinel-staging && git stash push -m 'matrix-vps' --include-untracked -- docs/matrix-runs/ && git pull --ff-only origin main"
   ```
2. **Env files**: api container reads `${APP_ENV_FILE:-.env}` from `docker-compose.yml`. The root `.env` on VPS sets `APP_ENV_FILE=deploy/staging/app.env`. **But `docker compose --env-file <X>` REPLACES root .env loading.** Fix: `compose.env` now also carries `APP_ENV_FILE=deploy/staging/app.env`. The canonical deploy command is:
   ```bash
   docker compose --env-file deploy/staging/compose.env up -d --build api
   ```
3. **Rate limit on staging api**: defaults to 200/hour per IP (`BLINKS_RATE_LIMIT_PER_HOUR`). VPS root `.env` bumps to 5000/hour for matrix runs. If the matrix sees `{"error": "Rate limit exceeded: 200/hour"}`, the api container is reading the wrong .env — re-up with `--env-file deploy/staging/compose.env`.
4. **Web container has pre-existing TS errors fixed in wave 1.5** — full rebuild including web works now. Build is ~3 min.
5. **VPS has no `node`** — can't run TS or node tests there. Sidecar js tests run from `services/solana-yield-builder/` only.
6. **`pkill -9 -f v4_runner` over SSH may exit 255 even on success.** Verify with `pgrep -f v4_runner` afterwards.
7. **Sequential matrix runner is more reliable than 9 parallel runners.** Parallel runs hit ~50 captures then hang (api blocking). Sequential takes ~60-90 min to complete 532 captures cleanly.
8. **Per-turn latency is real (5-15s for live LLM calls)**, so a full pass is 60-90 min minimum even after BUG-M01 singleton fix.

## DEPLOY-MATRIX CYCLE (one push + one redeploy + one refire per wave)

```bash
# Local
git push origin main

# VPS
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  git stash push -m 'matrix-vps' --include-untracked -- docs/matrix-runs/ && \
  git pull --ff-only origin main && \
  docker compose --env-file deploy/staging/compose.env up -d --build api"
# wait ~3 min; verify health
curl -fsS https://staging.ilyonai.com/api/v1/agent-health  # expect 200

# Fire matrix into the next wave dir
ssh ilyonai-vps "cd ~/ai-sentinel-staging && \
  export MATRIX_OUT_ROOT=docs/matrix-runs/passA-waveN && \
  mkdir -p \$MATRIX_OUT_ROOT && \
  nohup python3 -u -m tests.harness.v4_runner --all --delay 0.3 \
    > /tmp/matrix-passA-waveN.log 2>&1 < /dev/null & disown"
# schedule wakeup ~60 min; then check pgrep + capture count
```

## REVIEWER DISPATCH PATTERN (works — proven across 3 waves)

- **Dispatch 9 reviewers in parallel** (general-purpose subagent_type) — categories A, B, C, D, E, F, G, H, I.
- **Briefs must be COMPACT** (≤30 lines each — paste only the new context vs prior wave).
- **Always include the test-wallet carve-out**: `0xaaaa…` is the matrix wallet, NOT a placeholder.
- **Subagent Write tool is blocked** by harness policy. Subagents return findings INLINE. **Main thread saves the file** with `Write` to `docs/matrix-runs/passA-waveN/findings-{cat}.md`.
- Reviewer briefs must mention which fixes landed since prior wave and ask for CLOSED / STILL / NEW classification.

## CURRENT BACKLOG (after wave 4 fixes deployed, ~40 P0 + ~85 P1 remaining)

### Cross-cutting clusters — fix-wave priority order (one fix closes many bugs)

| Rank | Cluster | Affected | Fix location |
|------|---------|----------|--------------|
| 1 | Plan builder ignores `executable:false` flag | B 4 P0s + B-NEW-02 cached stub bypass | alloc→plan translator (find it via `grep "alloc_step" src/agent/tools/`) |
| 2 | Freeform-fallback fabricates tx hashes / portfolio state / "confirmed" prose | H P0 (H02 t4 cardinal — fabricated tx hash with ZERO tool calls), B, C, D, E variants | sentinel-gate at freeform `final.content` emit point. Catch `0x[0-9a-f]{40,}\\b.*submitted`, "confirmed", "no residual dust", "portfolio state" |
| 3 | Cross-chain intent parser drops `source_chain` | E 10/15 chains | `src/agent/intent/parser.py` — extract source-chain from "from <chain>", "via <chain>", "starting on <chain>" |
| 4 | Cross-chain composed plan emits `transaction:null` with `status:ready` | E07 (mutated since wave 3), H06 | `src/defi/execution/composed_plan.py::build_steps` — attach `COMPOSED_PLAN_INCOMPLETE_TX` when bridge_to/bridge_data null |
| 5 | Verb/asset/calldata desync in allocation steps | C P0-C-04, B P1s | alloc→plan translator: step.verb / step.asset must come from per-pool product_type, not template |
| 6 | Balance preflight doesn't walk dependency DAG | D-P0-05 (wrap-then-deposit false-blocks) | `src/defi/execution/preflight.py` — credit step outputs to downstream `assets_required` |
| 7 | Hallucinated protocol slugs / pool addresses | B (ADPUSDC/Pendle YT ladders), C (fake Raydium CLMM addr), D (`via-secondary-market-on-jupiter` chain_id=1) | slug allowlist + chain-kind consistency at plan emission |
| 8 | §7 funding scenario detectors mostly absent | H 12/15 missing (S6, S9, S10, S11, S12, S14, S15) | `src/defi/execution/scenarios/scenario_blockers.py` — one detector per scenario |
| 9 | Recovery enricher dispatch missing | F: every typed code beyond WALLET_CHAIN_MISMATCH gets pool-not-found template | `src/defi/recovery/stuck_balance.py::enrich_blocker_with_recovery` — per-code dispatch table |
| 10 | err_envelope path doesn't construct cards | F P1-F-04, P1-F-06 (codes correct in prose but no card) | wrap `simulate_swap` / `build_swap_tx` err_envelope returns in a card-builder |
| 11 | Step graph linkage absent in blockers | F: `affected_step_ids:[]` everywhere | when constructing blockers, walk `steps[].depends_on` from failing step |
| 12 | Intent parser misses session-key / AA verbs | I 3 P0s (REVOKE_SESSION_KEY, INSTALL_SESSION_KEY) | `src/agent/intent/parser.py` — grammar for "session key", "daily cap", "auto-rebalance", "revoke" |
| 13 | Borrow/repay verb router missing | D-P0-08 (D08 entire chain) | verb router maps "borrow / take loan" → action=borrow |
| 14 | Cadence-adverb → asset_hint hallucination | I NEW-I-03 ("daily" parsed as asset symbol) | stoplist `{DAILY, WEEKLY, HOURLY, MONTHLY}` in asset_hint extraction |
| 15 | LLM scratchpad strip — regex still misses some shapes | "Sum: ...", "DEFAULT to...", "OUTPUT FORMAT" caught by wave-4 fix; add observed wave-5 leak shapes | `src/agent/simple_runtime.py::_STRATEGY_SCRATCHPAD_LEAD_RE` |
| 16 | Price oracle wrong for chain-bridged assets | BSC WBETH uses BNB price, MATIC @ $0.09 (real $0.20), AVAX @ $9.09 (real $25-30) | `src/data/price_oracle.py` — chain-keyed token resolution |

### Important wave-3 NEW regressions (must close before declaring clean)

- **B P0-B-NEW-01 CoT scratchpad leak** (60+ lines on B14 t4) — wave 4's scratchpad-strip chokepoint should close this; verify in wave 5.
- **B P0-B-NEW-02 cached `executable:false` pool gets real signed tx** (B09 t4) — same root as cluster #1.
- **D P0-D-09 NEW kamino withdraw silently mislabeled "deposit"** + raw account-list leak — verb-dispatch + adapter-wrapper fix.
- **E BUG-E-003 MUTATED** — composed plan now `status=ready` with `transaction:null` (was implicit-blocked) — cluster #4.
- **E BUG-E-010 escalated to P0** — raw chain-of-thought leak on E06 t1 (wave-4 chokepoint may close; verify).
- **H P0-H-NEW-01 CARDINAL — fabricated `Transaction submitted: 0x3a9f…c1e2` with ZERO tool calls** in turn — cluster #2.

## WAVES SHIPPED SO FAR

| Wave | Commit | Bugs closed | Note |
|------|--------|-------------|------|
| Bootstrap | `2cac64c` | — | Goal+loop commands, spec PDF, repo-relative matrix captures, BUG_LEDGER init |
| Wave 1 (Tier 1) | `37b5df5` | V7-031, V7-041, V7-043, V7-045, V7-049 | Token-2022 hook, CLMM init, V3 verify(), useWalletSigning, V4 hook allowlist |
| Wave 2 (Tier 2) | `801f302` | V7-013, V7-014, V7-015, V7-020 | range_calculator shim, LpStrategy dispatch, EntityResolver fan-out, OpenRouter shim |
| Wave 1.5 (web TS) | `801f302` | providers.tsx + permit2 + SessionKey | Unblocked web rebuild |
| Wave 3 (audit-infra) | `03bd11c` | 3 hidden gaps + cleanup | dust_accumulator, pending.py, llm.py shadowed-by-package, Pendle selectors |
| Matrix-fix-1 | `9ffe441` | BUG-M01 (singleton AIRouter) | aiohttp session leak per request was crashing matrix after ~50 reqs |
| Matrix-fix-1 | `9ffe441` | BUG-M02 (plan projection-jump silent admit) | spec §5 state-machine warnings |
| Matrix-fix-2 | `d3f38ba` | BUG-F-01..F-04 (blocker code normalizer) | lowercase blocker codes → canonical UPPER_SNAKE at `ExecutionPlanV3.add_blocker` |
| Matrix-fix-2 | `1a785c2` | BUG-E-002 (guest-guard for deBridge) | `senderAddress=guest` HTTP 400 → structured WALLET_CHAIN_MISMATCH blocker |
| Matrix-fix-3 | `4747ec9` | BUG-F-05 (err_envelope normalizer sibling) | Lowercase codes from `simulate_swap` / `build_swap_tx` err_envelope path |
| Matrix-fix-4 | `231c299` | Scratchpad-strip at `emit_final` chokepoint + withdraw(0) drain-guard | A/B/C/E LLM CoT leaks + D-P1-14 user-safety bug |

## MATRIX CAPTURES (committed)

- `docs/matrix-runs/passA-wave1/` — 532 captures + 9 findings-{A..I}.md (48 P0 + 75 P1 surfaced)
- `docs/matrix-runs/passA-wave2/` — 530 captures + 9 findings (44 P0 + 77 P1)
- `docs/matrix-runs/passA-wave3/` — 530 captures + 9 findings (43 P0 + 87 P1)
- `docs/matrix-runs/passA-wave4/` — FIRING when this prompt is saved. Wakeup at 08:45 next-session-local-time.

## REVIEWER BRIEF TEMPLATE (paste-ready for the next cycle)

```
Matrix Pass A wave N reviewer, category X. Read `docs/matrix-runs/passA-waveN/X*/turn_*.txt`.
Compare findings to wave N-1 (`docs/matrix-runs/passA-wave{N-1}/findings-X.md`).

Fixes landed since wave N-1: <list with one-line each>

For each finding from wave N-1 classify CLOSED/STILL/NEW. Same severity rubric:
- P0 = financial-loss / safety bypass (calldata corruption, hallucinated tx hash, drain risk)
- P1 = wrong answer / spec violation (wrong blocker code, missing card, broken UX)
- P2 = cosmetic / inefficiency

Test wallet `0xaaaa…aaaa` (40 'a' chars) is the matrix wallet — NOT a placeholder.

Subagent file-writes are blocked by harness. Return findings INLINE; main thread
saves them to `docs/matrix-runs/passA-waveN/findings-X.md`.

Return path + one-line CLOSED-count / STILL-count / NEW-count summary.
```

## VALIDATION GATE (the goal's stopping condition)

Goal stops only when ALL hold simultaneously:
1. 12-subagent re-verification clean ✓ (DONE in V8)
2. **3 consecutive matrix passes with 0 P0/P1 outside `tests/harness/v4_gaps.py::EXPECTED_BLOCKED`** ✗ (0 of 3)
3. Anti-pattern grep at zero in safety paths ✓ (verified in V8; verify again after fix waves)
4. Final commit on `main`: `spec(complete): 75/75 V7-XXX + 12-subagent clean + 3 matrix passes [<shaA>, <shaB>, <shaC>]`
5. That SHA is what staging is currently deployed at.

## REALISTIC TIMELINE

Per matrix wave cycle: ~60-90 min capture + ~10-15 min reviewer dispatch + ~30-60 min fix-wave coding + ~3-5 min deploy = ~2-3 hours wall-clock per wave.

To close ~40 P0s in cluster groups of 1-4 P0s per fix wave: ~10-15 more fix waves = ~20-45 hours of clock time minimum (most spent waiting on matrix runs).

Then need to fire Pass B + Pass C cleanly. Each is another ~2-3 hour cycle.

**Bottom line**: realistic to spec(complete) is ~30-50 hours of session compute from current state. Continue iteratively. Each turn that lands a fix or runs reviewers makes measurable progress.

## START IMMEDIATELY

```bash
# 1. Confirm state
git log -1 --oneline  # expect 231c299 or later
git status

# 2. Verify staging
ssh ilyonai-vps "cd ~/ai-sentinel-staging && git log -1 --oneline"
curl -fsS https://staging.ilyonai.com/api/v1/agent-health  # expect 200

# 3. Check matrix wave 4 progress (firing in background since 07:45-ish)
ssh ilyonai-vps "pgrep -f v4_runner | wc -l; find ~/ai-sentinel-staging/docs/matrix-runs/passA-wave4 -name 'turn_*.txt' | wc -l"

# 4. If wave 4 complete (532 captures, runner gone): SCP back + dispatch 9 reviewers
scp -r -q ilyonai-vps:~/ai-sentinel-staging/docs/matrix-runs/passA-wave4/* docs/matrix-runs/passA-wave4/

# 5. Dispatch 9 reviewers in parallel per the template above

# 6. Aggregate + identify highest-impact next cluster fix per the priority table

# 7. Implement fix + pin test + commit + push + redeploy + fire matrix wave 5

# 8. Loop until 3 consecutive clean passes (0 P0/P1 outside EXPECTED_BLOCKED)

# 9. Final commit
```

## HARD RULES (break = rework)

1. NEVER skip pytest after a subagent commit
2. NEVER force-push `main`, NEVER skip hooks (`--no-verify`), NEVER bypass signing
3. NEVER commit secrets (deploy/staging/app.env, deploy/staging/assistant.env — already gitignored)
4. NEVER deploy to prod
5. NEVER guess on-chain addresses — WebFetch the official source + verify on chain
6. NEVER claim "complete" without 12-subagent clean + 3 clean matrix passes + grep at zero
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE refire per cycle.
8. All matrix validation against `staging.ilyonai.com`. Never `ilyonai.com`.
9. All commits on `main`. Do not push to `origin/staging`.
10. NEVER over-claim. Mark PARTIAL as PARTIAL. Mark MISSING as MISSING.
11. **No mechanical matrix analysis.** Findings come from LLM-subagent judgement, not regex.
12. **No stopping early.** Goal is not met until the exit check above holds. Self-fire via `ScheduleWakeup` to continue.

## ARTIFACTS (read these if you need refresher)

- `IlyonAi_LP_Execution_Spec.pdf` — sole source of truth (40 pages, v1.0 2026-05-14)
- `.spec_text_session.txt` — local-only PDF text extraction (gitignored; rebuild with `python -c "import pdfplumber; pdfplumber.open('IlyonAi_LP_Execution_Spec.pdf')..."`)
- `IlyonAi_Development_Plan_v2.md` — 75 V7-XXX tasks (all LIVE)
- `docs/SPEC_COVERAGE.md` — coverage ledger (currently over-claims 100%; flip to 100% LIVE only after 3 clean matrix passes)
- `docs/matrix-runs/BUG_LEDGER.md` — single source of truth for every bug surfaced (16 audit bugs + ~135 matrix bugs + waves Δ summaries)
- `docs/matrix-runs/passA-wave{1,2,3,4}/findings-{A..I}.md` — per-category hand-read reports
- `.claude/commands/goal.md` — end-state definition + persistence mandate
- `.claude/commands/loop-autonomous.md` — cold-resume hygiene + exit-check + decision tree

## DO NOT

- Don't start over from `git log -1` interpretation alone — read this file end-to-end.
- Don't dispatch the 12-subagent audit again unless the matrix is clean. The audit already returned clean in V8.
- Don't fire matrix from local Windows — fire from VPS only (latency + Python env).
- Don't run `pkill -9 -f v4_runner` over SSH if pgrep returns 0 — empty kill returns exit 1 → SSH exits 255.
- Don't waste cycles re-investigating the test wallet (`0xaaaa…`). It's the matrix harness wallet, not a placeholder leak.

Continue.
