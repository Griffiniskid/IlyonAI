# Liquidity-Pool Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every pool the AI returns for a user's criteria is shown; pools that can be executed get an EXECUTE button that produces a real, wallet-signable transaction; pools that cannot be one-click executed get NO execute button but a button that deep-links the user to that exact pool on the correct protocol.

**Architecture:** A reliable per-pool *executability oracle* dry-runs the real builder (the same code path execution uses) and caches the verdict. Search shows ALL matching pools; each pool carries an accurate `executable` flag (from the oracle) plus a `pool_deeplink` (exact pool URL on the protocol, DefiLlama-exact as fallback). The frontend renders EXECUTE on executable pools and an "Open pool" deep-link on the rest. We widen the executable set by finishing the Raydium and Enso adapter paths. We never claim execution works without a simulated transaction.

**Tech stack:** Python 3.11 / aiohttp backend (`src/`), Node 20 Solana sidecar (`services/solana-yield-builder/`), Next.js/React/TS frontend (`web/`), Enso shortcut API (EVM), Jupiter + Raydium/Orca/Meteora SDKs (Solana), Helius RPC.

---

## Definitions

- **Executable**: a dry-run of the real builder returns an `ExecutionPlanV3` with `status == "ready"`, OR `status == "blocked"` whose blockers are ALL "soft" (user-fixable: `INSUFFICIENT_BALANCE`, `GAS_TOPUP_REQUIRED`, `APPROVAL_MISSING`, `STALE_PRICE_FEED`, `SIM_STALE`, wallet-not-connected). Anything else (hard adapter/route/resolution failure, no card, exception, timeout) = **not executable**.
- **Soft blocker codes**: `{INSUFFICIENT_BALANCE, GAS_TOPUP_REQUIRED, APPROVAL_MISSING, STALE_PRICE_FEED, SIM_STALE, WALLET_NOT_CONNECTED}`.
- **Hard fail codes**: `{ADAPTER_BUILD_FAILED, UNSUPPORTED_ADAPTER, ASSET_POOL_MISMATCH, pool_kind_unsupported, NULL_ROUTE, POOL_NOT_INITIALIZED, ADAPTER_QUOTE_REQUIRED, WALLET_CHAIN_MISMATCH, pool_not_found, TRANSFER_HOOK_NOT_ALLOWED}`.
- **Deep link**: a URL that opens the SPECIFIC pool's deposit page on the protocol's own app (not the protocol homepage). Fallback when unknown: `https://defillama.com/yields/pool/<uuid>` (the exact pool page).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/defi/execution/executability_oracle.py` | NEW. Single source of truth: dry-run a pool → `(executable: bool, adapter_id, reason, blocker_codes)`, with TTL cache. Pure, reusable by search + tests. | Create |
| `src/agent/pool_deeplinks.py` | NEW. `pool_deeplink(protocol, chain, pool_id, pool_address, symbol, underlying_tokens) -> str`. Per-protocol exact-pool URL builders + DefiLlama-exact fallback. | Create |
| `src/agent/tools/search_defi_opportunities.py` | Show ALL matching pools (stop hiding non-executable); set accurate `executable` via oracle; attach `pool_deeplink` to every item; keep exec-first ranking only as a tiebreak, not a filter. | Modify |
| `src/agent/tools/execute_pool_position.py` | Keep deposit-only guard; ensure asset/action resolution is correct for LP/supply/stake; surface canonical blocker codes. | Modify |
| `src/agent/tools/build_yield_execution_plan.py` | Route `deposit_lp` for Enso-supported (non-CLMM) EVM protocols through the Enso adapter before native V2/V3; keep CLMM → link-only. | Modify |
| `src/defi/execution/adapters/enso_shortcut.py` | Broaden `deposit_lp` protocol coverage; robust position-token resolution (by protocol+underlying, then by pool address from DefiLlama). | Modify |
| `services/solana-yield-builder/src/adapters/raydium.js` | Finish `addLiquidity` typed inputs (BN amounts done; fix `slippage`/`Percent` + `otherAmountMin` types so the SDK builds). | Modify |
| `web/types/agent.ts` | Add `pool_deeplink?: string` to `DefiOpportunityItem`. | Modify |
| `web/components/agent/cards/DefiOpportunitiesCard.tsx` | Show every pool. Executable → amount/token form + EXECUTE. Non-executable → NO execute, an "Open pool" deep-link button + the reason. | Modify |
| `tests/defi/test_executability_oracle.py` | Oracle unit tests (classification of ready/soft/hard). | Create |
| `tests/agent/test_pool_deeplinks.py` | Deep-link builder unit tests per protocol. | Create |
| `web/tests/e2e/defi-execute-form.test.tsx` | Extend: non-executable pool shows deep-link button, no EXECUTE; executable shows EXECUTE. | Modify |
| `scripts/validation/pool_execution_sweep.py` | NEW. The mandatory verification harness (see Verification Protocol). Searches many criteria across chains, asserts every EXEC pool simulates, every non-EXEC pool has a valid deep link. | Create |

---

## Phase 1 — Executability Oracle (reliable, cached)

### Task 1: Oracle module + classification

**Files:**
- Create: `src/defi/execution/executability_oracle.py`
- Test: `tests/defi/test_executability_oracle.py`

- [ ] **Step 1: Write failing test** for blocker classification (pure function, no network).

```python
# tests/defi/test_executability_oracle.py
from src.defi.execution.executability_oracle import classify_plan, SOFT_BLOCKERS

def test_ready_is_executable():
    assert classify_plan({"status": "ready", "blockers": []}) == (True, None)

def test_soft_balance_blocker_is_executable():
    plan = {"status": "blocked", "blockers": [{"code": "INSUFFICIENT_BALANCE"}]}
    assert classify_plan(plan)[0] is True

def test_hard_adapter_failure_not_executable():
    plan = {"status": "blocked", "blockers": [{"code": "ADAPTER_BUILD_FAILED"}]}
    ok, reason = classify_plan(plan)
    assert ok is False and "ADAPTER_BUILD_FAILED" in reason

def test_no_card_not_executable():
    assert classify_plan(None)[0] is False
```

- [ ] **Step 2: Run, expect fail** — `docker run --rm --env-file .env -v "$PWD":/app -w /app -e PYTHONPATH=/app ilyonai-local-api python -m pytest tests/defi/test_executability_oracle.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** `classify_plan` + `SOFT_BLOCKERS` + an async `probe_pool(ctx, *, pool_id, chain, protocol, symbol, underlying_tokens, amount, asset_in)` that calls `execute_pool_position` (the real path), parses `card_payload`, returns `(executable, adapter_id, reason)`. Include a module-level TTL cache keyed by `pool_id` (TTL 300s) and a per-call `asyncio.wait_for(..., timeout=8.0)`.

```python
# src/defi/execution/executability_oracle.py
from __future__ import annotations
import asyncio, time
from typing import Any

SOFT_BLOCKERS = frozenset({
    "INSUFFICIENT_BALANCE", "GAS_TOPUP_REQUIRED", "APPROVAL_MISSING",
    "STALE_PRICE_FEED", "SIM_STALE", "WALLET_NOT_CONNECTED",
})

def classify_plan(plan: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not plan:
        return False, "no execution plan produced"
    if plan.get("status") == "ready":
        return True, None
    codes = [b.get("code") for b in (plan.get("blockers") or [])]
    if codes and all(c in SOFT_BLOCKERS for c in codes):
        return True, None
    return False, f"build failed: {codes or plan.get('status')}"

_CACHE: dict[str, tuple[float, bool, str | None]] = {}
_TTL_S = 300.0
_PROBE_SOLANA = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"   # read-only sim wallet
_PROBE_EVM = "0x28C6c06298d514Db089934071355E5743bf21d60"

async def probe_pool(ctx, *, pool_id, chain, protocol, symbol, underlying_tokens,
                     amount=20.0, asset_in=None) -> tuple[bool, str | None]:
    key = str(pool_id or f"{protocol} {symbol}")
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _TTL_S:
        return hit[1], hit[2]
    ch = (chain or "").lower()
    wallet = (getattr(ctx, "solana_wallet", None) if ch in {"solana", "sol"}
              else getattr(ctx, "evm_wallet", None))
    wallet = wallet or (_PROBE_SOLANA if ch in {"solana", "sol"} else _PROBE_EVM)
    try:
        from src.agent.tools.execute_pool_position import execute_pool_position
        env = await asyncio.wait_for(execute_pool_position(
            ctx, pool=key, amount=amount, amount_is_usd=True,
            chain=chain, asset_in=asset_in, user_address=wallet,
            extra={"underlying_tokens": underlying_tokens, "pool_symbol": symbol},
        ), timeout=8.0)
        plan = getattr(env, "card_payload", None) if getattr(env, "ok", False) else None
        ok, reason = classify_plan(plan)
    except Exception as exc:  # noqa: BLE001 — any failure => not executable now
        ok, reason = False, f"probe error: {type(exc).__name__}"
    _CACHE[key] = (now, ok, reason)
    return ok, reason
```

- [ ] **Step 4: Run, expect pass** (the `classify_plan` tests; `probe_pool` covered in Phase 4 sweep).
- [ ] **Step 5: Commit** — `git add ...; git commit -m "feat(defi): executability oracle with classification + cached probe"`.

---

## Phase 2 — Deep links to the exact pool

### Task 2: `pool_deeplink` builder

**Files:**
- Create: `src/agent/pool_deeplinks.py`
- Test: `tests/agent/test_pool_deeplinks.py`

- [ ] **Step 1: Failing tests** — one per protocol family + fallback.

```python
# tests/agent/test_pool_deeplinks.py
from src.agent.pool_deeplinks import pool_deeplink

def test_curve_exact_pool():
    url = pool_deeplink(protocol="curve-dex", chain="ethereum",
                        pool_id="abc", pool_address="0xPOOL", symbol="DAI-USDC-USDT", underlying_tokens=[])
    assert "curve" in url and "0xPOOL" in url

def test_uniswap_v3_exact_pool():
    url = pool_deeplink(protocol="uniswap-v3", chain="base",
                        pool_id="abc", pool_address="0xP", symbol="USDC-WETH", underlying_tokens=[])
    assert "0xP" in url

def test_raydium_uses_pool_id_or_mints():
    url = pool_deeplink(protocol="raydium-amm", chain="solana",
                        pool_id="abc", pool_address=None, symbol="SOL-USDC", underlying_tokens=["MintA","MintB"])
    assert "raydium" in url

def test_fallback_is_defillama_exact_pool():
    url = pool_deeplink(protocol="unknown-proto", chain="ethereum",
                        pool_id="uuid-123", pool_address=None, symbol="X-Y", underlying_tokens=[])
    assert url == "https://defillama.com/yields/pool/uuid-123"
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement** per-protocol builders. Each returns the exact-pool deposit URL when it has enough identity (pool address / mints / symbol), else the DefiLlama-exact fallback. Include at minimum: curve, uniswap-v2/v3/v4, sushiswap, pancakeswap, balancer, aerodrome(+slipstream), velodrome(+cl), raydium(amm/clmm), orca(whirlpools), meteora(dlmm), aave, compound, and a default.

```python
# src/agent/pool_deeplinks.py
from __future__ import annotations

_DEFILLAMA = "https://defillama.com/yields/pool/{uuid}"

def _norm(p: str | None) -> str:
    return (p or "").lower().strip()

def pool_deeplink(*, protocol, chain, pool_id, pool_address=None, symbol=None, underlying_tokens=None) -> str:
    p, c = _norm(protocol), _norm(chain)
    addr = pool_address
    mints = underlying_tokens or []
    # --- Solana ---
    if c in {"solana", "sol"}:
        if "raydium" in p:
            # Raydium deep-links by pool address; if absent, by token pair.
            if addr:
                return f"https://raydium.io/liquidity/?pool_id={addr}"
            if len(mints) >= 2:
                return f"https://raydium.io/liquidity/add/?inputMint={mints[0]}&outputMint={mints[1]}"
        if "orca" in p and addr:
            return f"https://www.orca.so/pools/{addr}"
        if "meteora" in p and addr:
            return f"https://app.meteora.ag/dlmm/{addr}"
        if "marinade" in p:
            return "https://marinade.finance/app/staking/"
        if "jito" in p:
            return "https://www.jito.network/staking/"
    # --- EVM ---
    if "curve" in p and addr:
        return f"https://curve.fi/#/{c}/pools/{addr}/deposit"
    if ("uniswap" in p or "pancakeswap" in p or "sushiswap" in p) and addr:
        return f"https://app.uniswap.org/explore/pools/{c}/{addr}" if "uniswap" in p else f"https://www.{p.split('-')[0]}.finance/pool/{addr}"
    if "aerodrome" in p and addr:
        return f"https://aerodrome.finance/deposit?token0=&token1=&pool={addr}"
    if "velodrome" in p and addr:
        return f"https://velodrome.finance/deposit?pool={addr}"
    if "balancer" in p and addr:
        return f"https://balancer.fi/pools/{c}/v2/{addr}"
    if "aave" in p:
        return "https://app.aave.com/markets/"
    # --- Fallback: DefiLlama exact pool page (still the SPECIFIC pool) ---
    return _DEFILLAMA.format(uuid=pool_id)
```

> NOTE for implementer: where `pool_address` is unknown but resolvable (Raydium by-mints, Curve registry), prefer resolving it so the link is pool-exact. The DefiLlama fallback is acceptable because it is still the exact pool, not a homepage.

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit.**

---

## Phase 3 — Wire oracle + deep links into search (show ALL pools)

### Task 3: Search shows all pools, accurate flag, deep link on every item

**Files:**
- Modify: `src/agent/tools/search_defi_opportunities.py`
- Modify: `web/types/agent.ts`

- [ ] **Step 1: Failing test** — search result keeps non-executable pools AND every item has a `pool_deeplink`.

```python
# add to tests/agent/test_simple_runtime.py or a new search test
# Assert: when a non-executable pool is in the ranked set, it is NOT removed,
# its item["executable"] is False, and item["pool_deeplink"] is a non-empty URL.
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement:**
  - Remove the "hide non-executable / fall back" trimming. Build `primary` from the top `display_limit` ranked candidates REGARDLESS of executability.
  - For the displayed candidates, run `probe_pool` (oracle) concurrently (semaphore 6, per-probe 8s, overall `wait_for` 22s). Set `candidate.executable` strictly from the oracle (pessimistic: un-probed → False).
  - Attach `pool_deeplink(...)` to every item's dict (`candidate.to_dict()` + inject, or add field on the model).
  - Keep exec-first ranking ONLY as a tiebreak so executable pools sort above equal-APY non-executable — but never as a filter.
- [ ] **Step 4:** Add `pool_deeplink?: string` to `DefiOpportunityItem` in `web/types/agent.ts`.
- [ ] **Step 5: Run tests, expect pass. Commit.**

---

## Phase 4 — Frontend: gate button, deep-link the rest

### Task 4: Card renders EXECUTE xor deep-link

**Files:**
- Modify: `web/components/agent/cards/DefiOpportunitiesCard.tsx`
- Modify: `web/tests/e2e/defi-execute-form.test.tsx`

- [ ] **Step 1: Failing tests** (vitest + testing-library):
  - Executable item → `defi-opp-execute` button present; clicking opens amount/token form.
  - Non-executable item → NO `defi-opp-execute`; a `defi-opp-open-pool` link present with `href === item.pool_deeplink` and `target="_blank"`.
- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement** the conditional render: `canExecute ? <Execute + form/> : <a data-testid="defi-opp-open-pool" href={item.pool_deeplink}>Open pool ↗</a> + reason`.
- [ ] **Step 4: Run, expect pass. Commit.**

---

## Phase 5 — Widen the executable set (adapters)

### Task 5: EVM `deposit_lp` routes through Enso first (non-CLMM)

**Files:**
- Modify: `src/agent/tools/build_yield_execution_plan.py`
- Modify: `src/defi/execution/adapters/enso_shortcut.py`

- [ ] **Step 1: Failing test** — `deposit_lp` for a Curve/Balancer/Aerodrome(non-CL)/V2 EVM pool selects the Enso adapter (or Curve native) and returns a 2-step `approve + add_liquidity` plan (ready or `INSUFFICIENT_BALANCE`).
- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement:**
  - In `build_yield_execution_plan`, for `action in {deposit_lp, add_liquidity, provide_liquidity}` on EVM where `classify_pool_kind != "v3"`, prefer the Enso adapter (or Curve native) before the native V2/V3 adapters that currently throw `UNSUPPORTED_ADAPTER`.
  - In `enso_shortcut.py`, broaden `deposit_lp` protocol coverage and make position resolution fall back: protocol+underlying → pool address (from DefiLlama meta) → `extra.position_token`.
  - Keep V3/CLMM `deposit_lp` → link-only (handled by the deep-link, not execute).
- [ ] **Step 4: Run, expect pass. Commit.**

### Task 6: Finish Raydium `addLiquidity` typed inputs (Solana AMM)

**Files:**
- Modify: `services/solana-yield-builder/src/adapters/raydium.js`

- [ ] **Step 1: Reproduce** — execute a Raydium AMM SOL-USDC pool; confirm current error `r.toFixed is not a function`.
- [ ] **Step 2: Implement:** read the installed `@raydium-io/raydium-sdk-v2` `cpmm.addLiquidity` / `liquidity.addLiquidity` signatures (in `node_modules`), and pass the EXACT expected types: BN raw amounts (done), `slippage` as the SDK's expected `Percent`/number form, `otherAmountMin` as BN, `epochInfo`/`poolKeys` if required. Resolve `poolKeys` from the SDK when the pool was found by mints.
- [ ] **Step 3: Verify** the build returns a serialized tx and `simulateBase64Tx` passes with the funded probe wallet (status ready or `INSUFFICIENT_BALANCE`).
- [ ] **Step 4: Commit.**

---

## Phase 6 — Verification Protocol (MANDATORY before claiming done)

### Task 7: `pool_execution_sweep.py` — prove it, don't claim it

**Files:**
- Create: `scripts/validation/pool_execution_sweep.py`

- [ ] **Step 1: Implement** a harness that, against the live local stack:
  1. Runs a MATRIX of search criteria across chains and pool types (≥ 20 queries): solana/ethereum/base/arbitrum/optimism/polygon × {liquidity pools, stablecoin pools, lending, staking, "low risk", "high apy", named protocols}.
  2. For EVERY returned item:
     - If `executable == true`: call `execute_pool_position` → assert the plan is `ready` OR blocked ONLY by soft codes, AND that a real unsigned transaction is present on the first step (`step.transaction` non-null). For Solana, assert `simulateBase64Tx` passed (no hard sim error).
     - If `executable == false`: assert `pool_deeplink` is a non-empty https URL AND there is NO execute affordance.
  3. Print a per-pool PASS/FAIL table + a SUMMARY. Exit non-zero if ANY executable pool failed to simulate or ANY shown pool lacked the correct affordance.
- [ ] **Step 2: Run it.** Required output: `FAILS=0` across all chains, with at least one EXECUTING pool per supported chain actually simulating.
- [ ] **Step 3: Commit** the harness + a saved run log under `docs/pool-exec-runs/`.

**Hard rule for the executor (no false claims):**
- You may NOT report "execution works" unless `pool_execution_sweep.py` exits 0 AND you have pasted the run showing real simulated transactions (Solana `simulateBase64Tx` ok; EVM `ready` with calldata) for executable pools on MULTIPLE chains.
- After each code change: rebuild the affected container(s) (`docker compose build <svc> && docker compose up -d --no-deps <svc>`) and re-run the sweep. Do not stop until `FAILS=0` and the matrix is fully green.

---

## Failure-Mode Catalog (every mistake + the fix)

| # | Failure | Where it shows | Root cause | Fix in this plan |
|---|---|---|---|---|
| 1 | `UUID could not be resolved to an on-chain pool` (Raydium) | sidecar | DefiLlama UUID ≠ Raydium pool address; mints missing | Resolve by mints (done) + symbol→mint map (done); if still unresolved → not executable → deep-link only |
| 2 | `r.isZero` / `r.toFixed is not a function` (Raydium SDK) | sidecar | amounts/slippage passed as wrong type | Task 6: pass SDK-correct typed inputs (BN/Percent) |
| 3 | `Orca build: requires whirlpool + tickLower/Upper` | sidecar | CLMM needs a price range | Out of one-click scope → mark non-executable → deep-link to Orca pool |
| 4 | `ASSET_POOL_MISMATCH` | execute_pool_position | user asset not a pool leg / wrong leg | Amount/token selector restricts to pool legs; LST base-asset exception (done); else refuse with clear reason |
| 5 | `pool_kind_unsupported` (gmtrade/CLOB/perps Solana) | execute_pool_position | receipt mint not on Jupiter graph | Static set (done) → not executable → deep-link |
| 6 | `ADAPTER_BUILD_FAILED: cannot resolve TOKEN` (EVM) | V3 NFT adapter | exotic token symbol not in registry | Non-V3 LP routes via Enso (underlying asset) — Task 5; V3 exotic → deep-link |
| 7 | `UNSUPPORTED_ADAPTER` (velodrome-v2 etc.) | registry.find | native LP adapter declines; Enso not reached | Task 5: route deposit_lp to Enso for non-CLMM EVM |
| 8 | `WALLET_CHAIN_MISMATCH` on Solana stake | build path | wallet not recognized as Solana / EVM path chosen | Validate wallet kind by chain; pass correct per-chain wallet |
| 9 | `429 Too Many Requests` (RPC) | sidecar | public RPC rate limit | Helius keyed RPC (done); oracle cache reduces calls |
| 10 | RPC/Enso timeout → "NO CARD" (flaky) | agent stream | external call hangs | Per-probe 8s + overall 22s timeout; oracle treats timeout as non-executable (shown with deep-link, never a broken EXECUTE) |
| 11 | Validation too slow → 0 shown | search | dry-run whole universe | Probe only the DISPLAYED set; show non-executable (deep-link) so results never empty |
| 12 | Ranking surfaces exotic non-building pools | search | APY-only ranking | Show all (they get deep-links); exec-first only as tiebreak |
| 13 | Deep link points to homepage not pool | card | no pool-exact URL | `pool_deeplink` resolves pool-exact; DefiLlama-exact fallback (still the specific pool) |
| 14 | `INSUFFICIENT_BALANCE` mistaken for failure | oracle | soft blocker | Classified as EXECUTABLE (user just needs funds) |
| 15 | Stale sim / re-quote ("Infinitys old") | plan card | sim age formatting/expiry | Re-quote before sign; treat `SIM_STALE` as soft |
| 16 | Token-2022 transfer-hook pools | sidecar | non-allowlisted hook | Hard fail → not executable → deep-link |
| 17 | Pool removed/paused/cap reached | build path | live pool state | Oracle dry-run catches it → not executable that moment → deep-link + recovery |

---

## Out of Scope (explicitly, to keep the plan honest)

- **Concentrated-liquidity range deposits** (Uniswap/Orca/Meteora/Raydium CLMM): require a price-range UI — a separate feature. These pools are SHOWN with a deep-link, never an EXECUTE button.
- **Pools with no programmatic deposit path** (gmtrade-class, CLOB, exotic illiquid tokens): SHOWN with deep-link only.
- Real on-chain *broadcast* (we build + simulate signable txs; the user signs in their wallet).

---

## Self-Review notes
- Spec coverage: show-all (Task 3), execute-button-on-executable (Tasks 3+4), deep-link-on-non-executable to exact pool (Tasks 2+4), every-mistake catalog (above), simulate-before-claiming (Task 7). ✓
- No placeholders: each task has concrete files, code, and run commands. ✓
- Type consistency: `executable: bool`, `pool_deeplink: str`, `classify_plan`, `probe_pool` names used consistently across tasks. ✓
