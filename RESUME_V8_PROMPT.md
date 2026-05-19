# RESUME V8 — CLOSE 9 PARTIAL GAPS · 88% → 100% SPEC MATCH

You are resuming an autonomous build of **IlyonAi**. The prior session's "97% complete" claim was **independently falsified** by a 6-subagent parallel audit run on 2026-05-19. Real measured completion: **66/75 LIVE (88%)** with **9 PARTIAL gaps still open** — 5 safety-impacting, 4 cosmetic.

This prompt is self-contained. Do not look for prior conversation context.

---

## ENVIRONMENT

- Repo: `C:\Users\griff\Документи\IlyonAI` on `main` (HEAD `7b4d1f5`)
- VPS: `ssh ilyonai-vps` (alias). Staging dir `/home/aisentinel/ai-sentinel-staging`. Prod dir `/home/aisentinel/ai-sentinel` — **READ-ONLY, NEVER TOUCH.**
- Staging URL: `https://staging.ilyonai.com` (health 200 verified)
- Prod URL: `https://ilyonai.com` — **never fire validation requests at this.**
- Test wallets: EVM `0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, Solana `5MgZcXp2qmH3jH8b4dZ7BoFvg9YjQRzL3Wb74Vfy839L`
- All commits land on `main`. Do not push to `origin/staging` even though the branch exists.

## SPEC SOURCES (read in this order if you need refresher)

1. `IlyonAi_LP_Execution_Spec.pdf` (canonical)
2. `IlyonAi_Development_Plan_v2.md` (75 V7-XXX tasks, 11 batches)
3. `V6_GAP_ANALYSIS.md` (upstream gap source)
4. `docs/SPEC_COVERAGE.md` (coverage tracker — note it currently over-claims 100%; this resume corrects it)

---

## THE 9 OPEN GAPS (close all of them, exit criteria below)

### TIER 1 — SAFETY-IMPACTING (fix first, one parallel wave)

#### V7-041 — Solana CLMM init gate BROKEN
- **Where**: `services/solana-yield-builder/src/adapters/_token_safety.js:331,344` exports `isWhirlpoolInitialized` and `isRaydiumCLMMInitialized` — but `orca.js` and `raydium.js` never call them.
- **Fix**: in each adapter's build path, call the helper before constructing the open-position IX. If `false` → emit `POOL_NOT_INITIALIZED` blocker + return early.
- **Pin test**: `tests/services/test_clmm_init_detection.test.js` — mocked Whirlpool RPC returns absent → assert blocker fires; absent Raydium CLMM → assert blocker fires.
- **Exit**: blocker fires in both adapters; pin test green; grep `POOL_NOT_INITIALIZED` in each adapter ≥ 1.

#### V7-031 — Token-2022 hook bypass via orca.js
- **Where**: 5 of 6 Solana adapters (jlp/raydium/kamino/meteora/sanctum/marinade) call `checkTransferHook`; `services/solana-yield-builder/src/adapters/orca.js` imports `tokenSafety` at line 35 but never invokes the function.
- **Fix**: add `checkTransferHook(mint)` call in orca.js build path before any transfer; refuse on non-allowlisted hook.
- **Pin test**: `tests/services/test_orca_token_2022.test.js` — mocked mint with unknown hook → orca refuses.
- **Exit**: grep `checkTransferHook` in `orca.js` ≥ 1; pin test green.

#### V7-043 — V3 NFT verify() still stub (core LP path)
- **Where**: `src/defi/execution/adapters/uniswap_v3_nft.py:951-952` returns `confirmed=False` with TODO. Sibling stubs: `enso_shortcut.py:329-330`, `wallet_assistant.py:53-54`.
- **Fix**: replace the stub with `parse_receipt_logs(receipt, canonical_topic0_for(IncreaseLiquidity))` — the helper exists at `src/defi/execution/adapters/base.py:68-106`. For Enso shortcut, parse the protocol-specific Deposit event from the routed adapter. For wallet_assistant, parse the generic Transfer event.
- **Pin test**: extend existing `tests/defi/test_verify_real.py` (or create) with a mocked receipt containing the canonical event → assert `confirmed=True`.
- **Exit**: all 3 stubs return `confirmed=True` on a real receipt; pin tests green.

#### V7-045 — useWalletSigning.ts is scaffolding only
- **Where**: `web/hooks/useWalletSigning.ts` has zero callsites repo-wide; internal `sign()` returns the literal string `"0x_PLACEHOLDER_set_by_real_wallet_call"`; no Jest test.
- **Fix**: (1) replace placeholder with real wagmi `useSignTypedData` (EVM) + Phantom `signTransaction` (Solana) wired path; (2) refactor 3-4 wallet-signing callsites to consume the hook — start with `Permit2SigButton.tsx`, the V3 mint signer in `ExecutionPlanV3Card.tsx`, and the broadcast handler; (3) add Jest test asserting 30s freshness gate refuses stale sim + calldata-hash assert fires.
- **Exit**: grep `useWalletSigning` in `web/components/` ≥ 3; no `_PLACEHOLDER_` strings remain; Jest test green.

#### V7-049 — V4 hook allowlist empty placeholder
- **Where**: `src/data/v4_hooks_allowlist.py:6-9` has real rebase/dynamic-fee hook addresses commented out; only `0x0000…0000` zero-address sentinel is allowlisted; `check_v4_hook` is never called from preflight.
- **Fix**: (1) WebFetch the official Uniswap V4 hook registry (docs.uniswap.org/contracts/v4/concepts/hooks, plus on-chain verifiable addresses) — never guess; (2) populate the allowlist with rebase hook + dynamic-fee hook + hook-less constant; (3) wire `check_v4_hook(hook_addr)` into `src/defi/execution/preflight.py` V4-detection branch — emit `DISALLOWED_V4_HOOK` on miss.
- **Pin test**: `tests/defi/test_v4_hooks_allowlist.py` already exists — extend it with a callsite-presence assertion (`grep check_v4_hook src/defi/execution/preflight.py`).
- **Exit**: allowlist has ≥ 3 real addresses (zero + ≥ 2 verified); preflight callsite present; pin test green.

### TIER 2 — SPEC-EXIT MISMATCHES (fix after Tier 1)

#### V7-015 — EntityResolver only 2/6 adapters refactored
- **Where**: class is correct (`src/defi/resolver/entity_resolver.py`); only `balancer.py:35` and `curve.py:28` import it.
- **Fix**: refactor 4 more adapter callsites to use `EntityResolver.resolve_token` / `resolve_chain` instead of local helpers. Suggested targets: `uniswap_v2.py`, `uniswap_v3_nft.py`, `aave_v3.py`, `compound_v3.py`.
- **Exit**: grep `from src.defi.resolver.entity_resolver import` ≥ 6 in `src/defi/execution/adapters/`.

#### V7-014 — LpStrategy enum unused by DLMM
- **Where**: enum at `liquidity_intent.py:57-71` (7 values); `src/defi/dlmm/bin_distribution.py` exposes raw `spot_distribution` / `curve_distribution` / `bid_ask_distribution` functions with no enum-based dispatch.
- **Fix**: add `dispatch_strategy(strategy: LpStrategy, ...)` in `bin_distribution.py` that routes to the right function. Add pin test asserting `LpStrategy.SPOT` → spot_distribution, etc.
- **Exit**: `LpStrategy` imported in `bin_distribution.py`; pin test maps all 7 enum values to a function.

#### V7-013 — Range numeric inconsistency
- **Where**: spec.md says WIDE=±20% but `liquidity_intent.py:91-100` pins WIDE=2500 bps (±25%) citing PDF p.6. Pin test agrees with code.
- **Fix**: open the PDF, confirm the value. Update whichever is wrong: either spec.md (if PDF is canonical) or code+test (if spec.md is canonical). Document the resolution in `docs/SPEC_COVERAGE.md`. ALSO: create the spec-mandated `src/defi/range_calculator.py` re-exporting `range_preset_bps()` for spec-path compatibility.
- **Exit**: spec/code/test all agree on WIDE bps; `src/defi/range_calculator.py` exists with the helper.

#### V7-020 — OpenRouter file-path drift
- **Where**: spec said `src/agent/llm/openrouter_client.py`; actual lives at `src/ai/openai_client.py:849-907` (dual OpenAI/OpenRouter via `use_openrouter` flag).
- **Fix**: create a thin re-export shim at `src/agent/llm/openrouter_client.py` that imports from `src/ai/openai_client.py` so spec-path lookups work. Document in `docs/SPEC_COVERAGE.md` that the canonical implementation is the dual-provider client.
- **Exit**: file exists at the spec path; existing tests still green.

---

## DISPATCH PROTOCOL

**Wave 1 (Tier 1, 5 parallel subagents)** — each subagent owns one V7-XXX:
- Constraints per subagent: independent file sets only; write code + pin test; run pytest itself; return diff list + verdict.
- Main thread aggregates → run full regression sweep (`pytest tests/agent tests/defi -q --deselect <3 known>`) → must stay green → stage → commit → push to `origin/main`.
- Single deploy to staging after Wave 1 completes.

**Wave 2 (Tier 2, 4 parallel subagents)** — V7-013, V7-014, V7-015, V7-020. Same protocol.

**Wave 3 (cleanup + audit)** — fix any audit-infrastructure issues surfaced in the 2026-05-19 audit:
- Install `pytest-asyncio`, `pytest-anyio`, `pydantic-settings`, `solana-py`, `sqlalchemy` in the dev/CI env
- Fix `test_no_legacy_100bps_in_adapters` and `test_slippage_defaults.py:56` hard-coded Linux paths (`/home/griffiniskid/Documents/ai-sentinel/`) → make cross-platform
- Update `IlyonAi_Development_Plan_v2.md` plan paths that drifted from reality (V7-002 adapter dir, V7-004 storage dir, V7-067 enum file, V7-055 lst_registry path, V7-056 zap adapter path)
- Update `docs/SPEC_COVERAGE.md` from claimed 100% to honest 88% → and only flip back to 100% after this resume completes

---

## DEPLOY-TO-STAGING CYCLE (one per wave, never mid-wave)

```bash
# Local (Windows)
git push origin main

# VPS
ssh ilyonai-vps
cd ~/ai-sentinel-staging
git pull
# Canonical staging env file is deploy/staging/compose.env (provides
# COMPOSE_PROJECT_NAME=ilyonai-staging so containers land in the right
# namespace). The container app envs live in deploy/staging/app.env and
# are referenced by ${APP_ENV_FILE:-.env} in docker-compose.yml — repo
# root .env already points at them on VPS.
docker compose --env-file deploy/staging/compose.env up -d --build
# Web container has a pre-existing TS error in providers.tsx that blocks
# full rebuild. To deploy only the python+solana backend without the web
# rebuild step (matrix doesn't need browser UI):
#   docker compose --env-file deploy/staging/compose.env up -d --build api assistant-api solana-yield-builder
# wait for healthcheck
curl -fsS https://staging.ilyonai.com/api/v1/agent-health  # expect 200
```

**Mid-wave redeploy = cascade kill 30-50 chains.** Batch fixes between waves.

---

## VALIDATION GATE (after all 9 gaps closed)

1. **Re-run the 6-subagent verification sweep** (same prompts as 2026-05-19 audit, see `/goal` command body). Each subagent returns:
   - 0 PARTIAL
   - 0 MISSING
   - All DONE
2. **Fire matrix Pass A** on staging: `STAGING_URL=https://staging.ilyonai.com python -m tests.harness.v4_runner --all --delay 1.5`. 120 chains × ≥4 turns. Captures → `docs/matrix-runs/passA-wave1/<chain_id>/turn_N.txt` (patch `OUT_ROOT` in `tests/harness/v4_runner.py:37` to repo-relative path).
3. **9 LLM category reviewer subagents** (A/B/C/D/E/F/G/H/I) hand-read transcripts in their category. Each writes `docs/matrix-runs/passA-wave1/findings-<category>.md`. **No regex/word-count checks** — judgement-based: hallucinated addresses, wrong blocker codes, missing cards, stale prices, calldata mismatches, gas miscalcs, dust unreported, sanitizer bypass.
4. If Pass A surfaces findings: fix on `main` → push → redeploy staging → fire Pass B as `passA-wave2/`. Loop. **One push + one redeploy + one matrix refire per cycle.**
5. **3 consecutive clean passes** (Pass A, B, C) required. All blockers HONEST per `tests/harness/v4_gaps.py`.
6. Update `docs/SPEC_COVERAGE.md` to 100% LIVE with the date + commit SHA.
7. Final commit: `spec(complete): 75/75 V7-XXX gaps closed + 6-subagent re-verification clean + 3 consecutive matrix passes`.

---

## HARD RULES (break = rework)

1. NEVER skip pytest after a subagent commit
2. NEVER force-push `main`, NEVER skip hooks (`--no-verify`), NEVER bypass signing
3. NEVER commit secrets
4. NEVER deploy to prod
5. NEVER guess on-chain addresses — WebFetch the official source + verify on chain
6. NEVER claim 100% without 6-subagent re-verification returning 0 PARTIAL + 0 MISSING **AND** 3 consecutive clean matrix passes
7. **Mid-pass redeploy = cascade kill.** ONE push + ONE redeploy + ONE refire per cycle.
8. All matrix validation against `staging.ilyonai.com`. Never `ilyonai.com`.
9. All commits on `main`. Do not push to `origin/staging` even though the branch exists.
10. NEVER over-claim. If something is partial, mark it PARTIAL in the report. The prior agent over-claimed 97% — do not repeat.

---

## START IMMEDIATELY

```bash
# 1. Confirm state
git log -1 --oneline
git status

# 2. Verify staging health
curl -fsS https://staging.ilyonai.com/api/v1/agent-health

# 3. Dispatch Wave 1 — 5 parallel subagents for Tier 1 safety gaps
#    V7-041 (CLMM init), V7-031 (Token-2022 orca), V7-043 (verify stubs),
#    V7-045 (useWalletSigning), V7-049 (V4 hook allowlist)
#    Each writes code + pin test + runs pytest + returns diff list

# 4. Aggregate, run regression sweep, stage, commit, push, redeploy staging

# 5. Dispatch Wave 2 — 4 parallel subagents for Tier 2 spec-exit gaps
#    V7-013, V7-014, V7-015, V7-020

# 6. Aggregate, regression, stage, commit, push, redeploy

# 7. Wave 3 — cleanup (audit infra + plan-path corrigenda + SPEC_COVERAGE refresh)

# 8. Re-run 6-subagent verification sweep — loop until 0 PARTIAL + 0 MISSING

# 9. Fire matrix Pass A on staging — capture to docs/matrix-runs/passA-wave1/

# 10. 9 category subagents read transcripts → findings-<X>.md

# 11. Fix findings → push → redeploy → refire as passA-wave2 (or passB-wave1 if clean)

# 12. Loop until 3 consecutive clean passes

# 13. Update SPEC_COVERAGE.md → 100% with date+SHA

# 14. Final commit
```
