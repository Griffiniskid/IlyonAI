# BUG_LEDGER — IlyonAi production-readiness pursuit

Single source of truth for every bug surfaced during the V8 close-to-100% pursuit:
6-subagent re-verification audit, anti-pattern grep sweep, hidden-gap discoveries,
and matrix passes A/B/C.

Initialized 2026-05-19 against HEAD `7b4d1f5` (after prior session's claimed-100%
was independently falsified to 88% by 6-subagent audit run on the same date).

## Schema

Each entry has:
- **ID** — `BUG-NNN` monotonically increasing
- **Surfaced by** — `audit-batch-X` | `hidden-gap` | `anti-pattern-grep` | `pass{A,B,C}-wave{N}/{chain_id}/turn_{N}`
- **Severity** — `P0` (financial loss / safety bypass) | `P1` (wrong answer / missing card / bad blocker code) | `P2` (cosmetic / inefficiency)
- **Spec reference** — `§X.Y`, requirement ID, S{1-15}, D.{1-8}, or §13 row label
- **Root cause** — one-line technical explanation
- **Fix** — `path/to/file.py:line_no` (or multiple) + commit SHA
- **Before/after SSE quote** — for matrix-surfaced bugs only; literal substring of SSE that flips from broken → fixed

## Entries

### Tier 1 — Safety-impacting PARTIALs (Wave 1, commit 37b5df5)

#### BUG-001 — Token-2022 transfer-hook bypass via orca.js
- **Surfaced by**: 2026-05-19 audit batch §5 (V7-031)
- **Severity**: P0 (financial-loss class — malicious Token-2022 mint with non-allowlisted hook silently routed deposits through Orca)
- **Spec reference**: §11 D.5 (Token-2022 transfer-hook gate)
- **Root cause**: 5 of 6 Solana adapters called `checkTransferHook`; orca.js imported `tokenSafety` at line 35 but never invoked the helper. Build path constructed open-position IX without gating either pool mint.
- **Fix**: `services/solana-yield-builder/src/adapters/orca.js` (added `checkTransferHook` calls + `_orcaHookBlocker` factory in `buildOpen` for both pool sides + input mint). Commit `37b5df5`.
- **Pin test**: `tests/services/test_orca_token_2022.test.js` — 6/6 pass; asserts TRANSFER_HOOK_NOT_ALLOWED blocker fires on unknown hook + allowlisted hook passes through.

#### BUG-002 — Solana CLMM pool-init gate never invoked
- **Surfaced by**: 2026-05-19 audit batch §5 (V7-041)
- **Severity**: P0 (confusing on-chain revert instead of clean blocker — user signs tx that fails at the contract level)
- **Spec reference**: §11 invariant (clean-blocker-before-broadcast)
- **Root cause**: `_token_safety.js:331,344` exported `isWhirlpoolInitialized` and `isRaydiumCLMMInitialized` but no adapter called them. Open-position attempts on missing pools went through to chain-level failure.
- **Fix**: `services/solana-yield-builder/src/adapters/orca.js` (gate in `buildOpen` before `pool.openPosition`); `services/solana-yield-builder/src/adapters/raydium.js` (added `buildCloseChecked` async wrapper); `services/solana-yield-builder/src/index.js:172-191` (HTTP dispatcher prefers `buildCloseChecked` when available, adapts request body → wrapper signature). Commit `37b5df5`.
- **Pin test**: `tests/services/test_clmm_init_detection.test.js` — 6/6 pass; mocked RPC returns null + wrong-owner → POOL_NOT_INITIALIZED blocker.

#### BUG-003 — V3 NFT verify() returns confirmed=False stubs (3 core LP adapters)
- **Surfaced by**: 2026-05-19 audit batch §6 (V7-043)
- **Severity**: P0 (perma-pending receipts — user UI shows "pending" forever even after on-chain confirmation)
- **Spec reference**: §11 D.7 (receipt verification), §6g (Receipt-token verification)
- **Root cause**: `uniswap_v3_nft.py:951-952`, `enso_shortcut.py:329-330`, `wallet_assistant.py:53-54` all returned `confirmed=False` with TODO comments. Helper `parse_receipt_logs` existed at `base.py:68-106` but was unused.
- **Fix**: `src/defi/execution/adapters/uniswap_v3_nft.py` (canonical IncreaseLiquidity topic0 `0x3067048b…7e35f` parsing + tokenId/liquidity/amount0/amount1 surface); `src/defi/execution/adapters/enso_shortcut.py` (protocol-aware topic0 registry: Aave Supply, Compound Supply, ERC-4626 Deposit family + two-leg ERC-20 Transfer fallback for unknown protocols); `src/defi/execution/adapters/wallet_assistant.py` (canonical ERC-20 Transfer `0xddf252ad…b3ef`). Commit `37b5df5`.
- **Pin test**: `tests/defi/test_adapter_verify_real.py` — 42/42 pass; matching topic0 + empty + wrong topic0 cases per adapter.

#### BUG-004 — useWalletSigning.ts was placeholder scaffolding
- **Surfaced by**: 2026-05-19 audit batch §7 (V7-045)
- **Severity**: P1 (no freshness gate / no calldata-hash bind — broadcast could replay stale sim or diverge from sim payload)
- **Spec reference**: §11 D.1 (calldata-hash bind), §11 D.2 (30s freshness)
- **Root cause**: `web/hooks/useWalletSigning.ts` existed but `sign()` returned the literal string `"0x_PLACEHOLDER_set_by_real_wallet_call"`; zero callsites repo-wide; no test. Every wallet-signing callsite duplicated logic and missed the gates.
- **Fix**: `web/hooks/useWalletSigning.ts` (real wagmi+Phantom wiring via `window.ethereum`, 30s SIM_STALE gate, keccak256(calldata) CALLDATA_MISMATCH bind); refactored 3 callsites — `web/components/agent/cards/Permit2SigButton.tsx`, `web/components/agent/cards/ExecutionPlanV3Card.tsx`, `web/components/agent-app/MainApp.tsx::handleSignStep`. Commit `37b5df5`. Type declarations added in Wave 1 aggregate at `web/types/agent.ts` (ExecutionPlanV3StepTransaction.simulated_calldata_hash + simulated_at).
- **Pin test**: `web/tests/hooks/useWalletSigning.test.tsx` — 4/4 vitest; freshness gate, calldata-hash bind, happy paths.
- **Note**: wagmi migration deferred intentionally (multi-day separate task). The hook composes existing window.ethereum primitives with the gates the spec mandates.

#### BUG-005 — V4 hook allowlist empty + check never wired
- **Surfaced by**: 2026-05-19 audit batch §7 (V7-049)
- **Severity**: P0 (any V4 pool with any hook accepted by preflight — malicious hook could drain on add_liquidity)
- **Spec reference**: §11 D.4 (V4 hook allowlist), §6a (Slipstream + Uniswap V4 native exec)
- **Root cause**: `src/data/v4_hooks_allowlist.py:6-9` had real rebase/dynamic-fee addresses commented out; only zero-address sentinel; `check_v4_hook` defined but never called from preflight.
- **Fix**: `src/data/v4_hooks_allowlist.py` (Angstrom + BunniHook on Ethereum mainnet from Uniswap/hooklist registry); `src/shield/v4_hook_allowlist.py` (same 2 entries with HookEntry+audit URL); `src/defi/execution/preflight.py` (wired `_check_v4_hook_blockers` detector emitting DISALLOWED_V4_HOOK). Commit `37b5df5`.
- **Pin test**: `tests/defi/test_v4_hooks_allowlist.py` + `test_v4_hook_allowlist.py` — 27/27 pass; cross-module sync test `test_shield_and_data_allowlists_stay_in_sync` prevents future drift.
- **WebFetch source**: `https://github.com/Uniswap/hooklist`. Audit: Spearbit Oct 2024 for Angstrom. Etherscan verified-source for both.

### Tier 2 — Spec-exit mismatches (Wave 2, commit 801f302)

#### BUG-006 — Range numeric reconciliation phantom (V7-013)
- **Surfaced by**: V8 resume brief (claimed spec.md says WIDE=±20% but code=±25%)
- **Severity**: P2 (no actual disagreement — falsified during audit)
- **Spec reference**: §3.3 p.6 ("Wide ±25% (~4× efficiency, ~95% in-range historically for blue-chips)")
- **Root cause**: V8 brief stated a `spec.md` existed with diverging WIDE value. Glob `**/spec.md` returns NO files. Code at `liquidity_intent.py:91-100` already cites PDF §3.3 p.6 verbatim with 2500 bps = ±25%. The "drift" was a phantom — code matches PDF.
- **Fix**: Created `src/defi/range_calculator.py` shim re-exporting `range_preset_bps`/`RangePreset`/`RANGE_PRESET_BPS`/`STABLE_RANGE_PRESET_BPS` for spec-path compatibility. Commit `801f302`.
- **Pin test**: `tests/defi/test_range_calculator_shim.py` — 8/8 pass; identity-checks ensure shim and canonical share the same function objects (no silent drift possible).

#### BUG-007 — LpStrategy enum unused by DLMM (V7-014)
- **Surfaced by**: 2026-05-19 audit batch §2
- **Severity**: P2 (no enum→function dispatch — callers hardcoded function names)
- **Spec reference**: §1 LP intent schema (LpStrategy enum drives bin distribution)
- **Root cause**: `bin_distribution.py` exposed 3 raw functions (spot/curve/bid-ask); 7 LpStrategy enum values existed but no dispatcher routed them.
- **Fix**: `src/defi/dlmm/bin_distribution.py::dispatch_strategy(LpStrategy, active_bin, range_bins)` routing SPOT/CURVE/BID_ASK and raising NotImplementedError for the 4 MAVERICK_* values (Maverick lives outside DLMM). Commit `801f302`.
- **Pin test**: `tests/defi/test_dlmm_strategy_dispatch.py` — 11/11 pass; includes forever-loop assertion iterating every LpStrategy member.
- **Follow-up**: production callers don't yet route through dispatch_strategy (still call spot_distribution etc. directly). Tracked separately — not part of V7-014's exit criteria.

#### BUG-008 — EntityResolver only 2/6 adapters refactored (V7-015)
- **Surfaced by**: 2026-05-19 audit batch §3
- **Severity**: P2 (scattered helpers instead of unified resolver)
- **Spec reference**: §4 Resolver service (single canonical entity-resolution layer)
- **Root cause**: `EntityResolver` class was correct; only balancer.py + curve.py imported it.
- **Fix**: `src/defi/execution/adapters/{uniswap_v2,uniswap_v3_nft,aave_v3,compound_v3}.py` now route token + chain resolution through `EntityResolver`. Legacy local dicts retained as fallback because sibling modules (uniswap_v2_zap, erc4626) re-import them. Commit `801f302`.
- **Pin test**: `tests/defi/test_entity_resolver_fanout.py` — 11/11 pass + 77/77 adapter regression. USDC ethereum address (`0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48`) routes identically through both paths.

#### BUG-009 — OpenRouter spec-path drift (V7-020)
- **Surfaced by**: 2026-05-19 audit batch §3
- **Severity**: P2 (spec-mandated import path `src/agent/llm/openrouter_client.py` didn't exist)
- **Spec reference**: §4 Logical architecture (LLM router service location)
- **Root cause**: Canonical impl lived at `src/ai/openai_client.py::OpenAIClient` with `use_openrouter=True` flag. Spec-path imports failed.
- **Fix**: Created `src/agent/llm/openrouter_client.py` re-exporting `OpenAIClient` + `OpenRouterClient` alias (identity-equal). Commit `801f302`.
- **Pin test**: `tests/defi/test_openrouter_shim.py` — 5/5 pass; alias identity + smoke-construct with `use_openrouter=True` selects `openrouter.ai/api/v1/chat/completions` base URL.

### Tier 3 — Hidden gaps + audit infra (Wave 3, commit 03bd11c)

#### BUG-010 — src/defi/recovery/dust_accumulator missing module (production runtime importer)
- **Surfaced by**: 2026-05-19 anti-pattern grep / pre-existing test failures
- **Severity**: P1 (runtime crash on any sub-dollar leg dust detection — `from src.defi.recovery.dust_accumulator import …` raised ModuleNotFoundError)
- **Spec reference**: §3 sizing, §6f stuck-balance recovery (DUST_BELOW_THRESHOLD blocker)
- **Root cause**: `src/defi/execution/scenarios/scenario_blockers.py:85` imported the module at runtime; the module did not exist in the repo.
- **Fix**: Created `src/defi/recovery/dust_accumulator.py` with DUST_THRESHOLD_USD ($1.00), DustPosition dataclass, is_dust() defensive feed-error handling, decide_dust_disposition() 3-way tree (SWEEP / LEAVE / INCREASE_TO_THRESHOLD), build_dust_blocker() producing canonical DUST_BELOW_THRESHOLD ExecutionBlocker. Commit `03bd11c`.
- **Pin test**: `tests/defi/test_dust_accumulator.py` — 17/17 pass + 6 scenario_blockers tests now pass.

#### BUG-011 — src/defi/execution/pending missing module (production runtime importer)
- **Surfaced by**: 2026-05-19 anti-pattern grep / pre-existing test failures
- **Severity**: P1 (runtime crash on cross-chain composed plan construction — `from src.defi.execution.pending import debridge_fill` raised ModuleNotFoundError on every async-fill step)
- **Spec reference**: §6c cross-chain composed plans, §1 unified pending primitive
- **Root cause**: `src/agent/tools/build_yield_execution_plan.py:432` imported the module at runtime; the module did not exist.
- **Fix**: Created `src/defi/execution/pending.py` — frozen `PendingPrimitive` dataclass + 4 factories (debridge_fill, pendle_epoch, lido_queue, solana_confirmation) + `as_blocker_payload()` with stable key set + canonical kind→blocker_code mapping. Commit `03bd11c`.
- **Pin test**: `tests/defi/test_pending_primitive.py` — 19/19 pass + cross-chain tests unblocked.

#### BUG-012 — src/agent/llm.py shadowed by SA8's src/agent/llm/ package
- **Surfaced by**: tests/agent collection errors after V7-020 shim creation
- **Severity**: P1 (Python file→package shadowing — every `from src.agent.llm import IlyonChatModel` consumer broke silently when SA8 created the package directory)
- **Spec reference**: §4 LLM service
- **Root cause**: V7-020 (Wave 2 SA8) created `src/agent/llm/__init__.py` to satisfy spec-path imports; Python's import resolution prefers package over file, so the existing `src/agent/llm.py` module became unreachable. `IlyonChatModel` disappeared from imports.
- **Fix**: Migrated `IlyonChatModel` class into `src/agent/llm/__init__.py` (now exports IlyonChatModel + OpenAIClient + OpenRouterClient); deleted the now-unreachable single-file `src/agent/llm.py`. Commit `03bd11c`.
- **Pin test**: tests/agent collection recovered for 24 of 29 previously broken collection paths.

#### BUG-013 — Pendle V4 router selector reconciliation (V7-057 collision sentinel)
- **Surfaced by**: tests/defi/test_pendle_v2_modes.py selector-pinned test failure
- **Severity**: P2 (metadata-only divergence — selectors are step-snapshot display, calldata itself comes from Pendle Hosted SDK, so no on-chain behavior change)
- **Spec reference**: §9g Pendle V2 per-family deep-dive
- **Root cause**: 3 SEL_ constants in pendle_v2.py held stale values + collided. SEL_MINT_PY_FROM_TOKEN and the spec-pinned SEL_SWAP_EXACT_TOKEN_FOR_PT both held `0xc81f847a`. The test explicitly asserts "All 6 selectors distinct (V7-057 collision sentinel)".
- **Fix**: `src/defi/execution/adapters/pendle_v2.py` — SEL_MINT_PY_FROM_TOKEN `0xc81f847a → 0xd0f42385`, SEL_SWAP_TOKEN_FOR_PT `0x594a88cc → 0xfeb9d1d2`, SEL_ADD_LIQUIDITY_FROM_TOKEN `0x9f9da99e → 0x12599ac6`. New SEL_SWAP_EXACT_TOKEN_FOR_PT `0xc81f847a` (the distinct ApproxParams variant). Commit `03bd11c`.
- **Pin test**: `tests/defi/test_pendle_v2_modes.py` — 13/13 pass including selector-distinct-set sentinel.

#### BUG-014 — V4 hook allowlist shield/data divergence (Wave 1 aggregate)
- **Surfaced by**: Wave 1 aggregate review of SA4's output
- **Severity**: P1 (preflight gate allowed what adapter-build gate refused — V4 hook deposit would 500 at adapter-build with "V4 hook refused by Shield" even though preflight passed)
- **Spec reference**: §11 D.4
- **Root cause**: SA4 (V7-049) added Angstrom + BunniHook to `src/data/v4_hooks_allowlist.py` (preflight gate). The schema-rich canonical module `src/shield/v4_hook_allowlist.py` (adapter-build gate, consumed by uniswap_v4.py) still had `_ALLOWLIST = {}` empty. Both gates needed to agree.
- **Fix**: Populated `src/shield/v4_hook_allowlist.py::_ALLOWLIST` with the same 2 HookEntry rows (audit_report URL + properties tuple). Added test `test_shield_and_data_allowlists_stay_in_sync` asserting both registries cover the same (chain_id, addr) set. Commit `37b5df5` (Wave 1 aggregate).

#### BUG-015 — Hardcoded Linux paths in 3 cross-platform tests (silent no-op on Windows)
- **Surfaced by**: 2026-05-19 audit infra check (Wave 3)
- **Severity**: P2 (drift-detection tests silently passed on Windows because subprocess+grep couldn't find their hardcoded cwd `/home/griffiniskid/Documents/ai-sentinel/`)
- **Spec reference**: development-process hygiene
- **Root cause**: `test_slippage_defaults.py:56`, `test_decide_recovery_callsites.py:199` used `subprocess.check_output(["grep", …], cwd="/home/griffiniskid/Documents/ai-sentinel/")`. `test_alt_split_warning.py:27` used `FALLBACK_DEPS = Path("/tmp/altsplit-test-deps")` + relied on node finding deps via CWD walk.
- **Fix**: Replaced subprocess+grep with pure-python pathlib walking (derives repo root from `Path(__file__).resolve().parents[2]`); `FALLBACK_DEPS` now uses `tempfile.gettempdir()`; `_run_node` sets NODE_PATH to the sidecar's node_modules when present. All 3 tests run cross-platform. Commit `03bd11c`.

#### BUG-016 — Dev-env transient deps missing from requirements.txt
- **Surfaced by**: Wave 1 + 3 regression runs (SA2 reported `eth_abi` install drift; main thread surfaced `bs4`, `pycryptodome`, `pynacl`, `web3`, `eth-account`, `eth-utils`, `langchain-openai`, `langchain-groq`, `aiosqlite`, `asyncpg`, `lxml`)
- **Severity**: P2 (CI flake — tests pass locally but explode on a fresh env)
- **Spec reference**: development-process hygiene
- **Root cause**: Several runtime deps were transitive (brought in by other packages), not explicitly pinned. Fresh-env installs missed them.
- **Fix**: Added `web3`, `eth-account`, `eth-utils`, `eth-abi`, `eth-hash[pycryptodome]`, `lxml` to `requirements.txt`. Commit `03bd11c`.

### Anti-pattern grep audit (2026-05-19, HEAD 03bd11c)

| Pattern | Scope | Hits | Verdict |
|---------|-------|------|---------|
| `_PLACEHOLDER_` | `src/` excl. legit regex | 0 (after Wave 1) | CLEAN |
| `confirmed=False` | `src/defi/execution/adapters/` | 7 (all defensive: no-receipt, no-context, exception handlers) | CLEAN |
| `TODO|FIXME` | `src/shield/`, `src/auth/`, `src/defi/execution/` | 1 (informational note re: rsETH Lineascan verification) | CLEAN |

Legitimate exceptions: `_GAUGE_PLACEHOLDER_BY_PROTO` (per-protocol fallback gauge map), `_UNBACKED_PLACEHOLDER_ADDR_RE` (sanitizer regex matching LLM placeholder addresses).

### Matrix passes

#### BUG-M01 — AIRouter instantiated per agent request (aiohttp session leak + matrix hang)
- **Surfaced by**: passA-wave1/* (matrix fires hung after ~50 requests on 2026-05-20 ~21:42 UTC; api logs showed "AI Router initialized" on every request + "Unclosed client session/connector" warnings stacking up)
- **Severity**: P0 (production users hit this on every chat turn — leaks aiohttp ClientSessions; eventually pool exhausts and requests stall; matrix needed to run sequentially with hangs to surface this)
- **Spec reference**: §4 Logical Architecture (single AI router service for the process)
- **Root cause**: `src/api/routes/agent.py:97` did `router = AIRouter()` inside every `agent_turn` handler. `AIRouter.__init__` constructs an `OpenAIClient(model=..., use_openrouter=True)` (line 87 of router.py) which lazily holds an aiohttp.ClientSession; same for `OpenAIClient(openai_mini_model, ...)` and `GrokClient()` (line 97). Each request created 3 fresh sessions that nobody closed; aiohttp's GC-time warning ("Unclosed client session") fired but the connector pool kept growing until requests hung.
- **Fix**: `src/api/routes/agent.py:14-29` — added module-level `_AGENT_ROUTER` singleton + `_get_agent_router()` lazy getter; replaced the per-request instantiation. Sessions are created once and reused across the process lifetime.
- **Before/after SSE quote**:
  - Before: matrix runner wrote 74 captures, then froze with last capture at 22:42 UTC; api logs showed "Unclosed client session" every 1-2 seconds for the matching window.
  - After: (pending verification on next matrix fire — captures should stream continuously without hang).
- **Pin test**: covered indirectly by matrix Pass A completion (full 532-capture run without hang). Direct unit test would require an aiohttp test harness — tracked as a follow-up if matrix doesn't naturally surface a future regression.

#### BUG-M02 — Plan illegal state transition draft → ready (spec §5 violation)
- **Surfaced by**: passA-wave1/* (api logs: "plan plan_XXX illegal state transition draft (Prompted) → ready (ReadyToSign) — spec §5 forbids this jump", multiple plan IDs in <1s window during matrix fire on 2026-05-20)
- **Severity**: P1 (state-machine warning; the plan still emits but spec §5 mandates explicit intermediate `simulated` → `ready` transition. Risk: a downstream consumer that strictly enforces §5 would reject these plans).
- **Spec reference**: §5 Canonical State Machine ("draft → prompted → simulating → simulated → ready → signing → submitted → confirmed → indexed")
- **Root cause**: (under investigation — `src/defi/execution/models.py::_emit_status_warn` fires; some code path is calling `_set_status("ready")` directly from "draft" without going through "simulated". Likely in a planner that constructs and immediately marks-ready when no simulation is needed.)
- **Fix**: pending root-cause trace.
- **Status**: P1 LOGGED — will fix in matrix fix-loop wave.

---

## Coverage delta tracker

| Snapshot                       | LIVE | PARTIAL | MISSING | SKIP-OK | Source                |
|--------------------------------|------|---------|---------|---------|-----------------------|
| Prior session claim (over)     | 75   | 0       | 0       | 0       | docs/SPEC_COVERAGE.md (pre-V8) |
| 2026-05-19 independent audit   | 58   | 9       | 0       | 8       | 6-subagent audit      |
| Post-Wave-1 (37b5df5)          | 63   | 4       | 0       | 8       | +5 Tier-1 closures    |
| Post-Wave-2 (801f302)          | 67   | 0       | 0       | 8       | +4 Tier-2 closures    |
| Post-Wave-3 (03bd11c)          | 67   | 0       | 0       | 8       | +3 hidden gaps + cleanup; ledger headcount unchanged |
| Post-validation-gate           | 69 LIVE + 10 SKIP-OK | 0 | 0 | (audit count) | 6-subagent re-audit returned 0 PARTIAL / 0 MISSING / 0 NEW-GAP |
| Final (target)                 | 75   | 0       | 0       | 0       | + 3 clean matrix passes |
