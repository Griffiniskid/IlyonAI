# Phase C — 11-batch codebase re-audit summary (v1)

**Date**: 2026-05-21
**HEAD**: `16ca4f1` (post Phase B closure, post-wave-12 backend)
**Audit method**: 11 parallel general-purpose subagents, one per batch (A–K)
**Spec source of truth**: `IlyonAi_LP_Execution_Spec.pdf` v1.0

## Per-batch verdict matrix

| Batch | Scope | Verdict | LIVE | PARTIAL | MISSING |
|-------|-------|---------|------|---------|---------|
| A | §1-§3 (Mission, Intent, Dispatcher) | PARTIAL | 19 | 5 | 0 |
| B | §4-§5 (Architecture, State Machine, Card Schema) | PARTIAL | 2 | 2 | 0 |
| C | §6a-§6c (V3/V4 native, composed plans) | LIVE | 11 | 0 | 0 |
| D | §6d-§6g (source-token, APR-CDF, recovery, verify) | LIVE | 3 | 1 | 0 |
| E | §7 S1-S15 funding scenarios | LIVE | 15 | 0 | 0 |
| F | §8 chains (17 EVM + Solana) + §9 notifier | PARTIAL | 19 | 10 EVM | 0 |
| G | §10 wallets + AA + session keys | PARTIAL | 8 | 1 | 1 |
| H | §11 D.1-D.8 safety invariants | PARTIAL | 5 | 2 | 1 |
| I | §12 deployment + §14 monitoring | LIVE | 8 | 0 | 0 |
| J | §13 27-row edge case appendix | PARTIAL | 19 | 5 | 0 |
| K | cross-cutting (BUG_LEDGER receipts, anti-pattern grep, CardType↔Renderer) | PARTIAL | 4 | 1 | 0 |

**Aggregate: 113 items LIVE, 30 PARTIAL, 2 MISSING.**

## P0 findings (must fix for tester-ready)

### P0-C-001 — Sign-gate bypass in MainApp handleSignStep (Batch G)
- `web/components/agent-app/MainApp.tsx::handleSignStep` (lines 5278-5449) implements a **two-tier signing path**:
  - **Tier 1 gated** (lines 5234-5277): when `simHash && simAt > 0`, routes through `useWalletSigning.sign()` → 30s freshness + calldata-hash enforced.
  - **Tier 2 UNGATED LEGACY** (lines 5278-5449): when sim metadata absent OR hook errors for a non-gate reason, calls `eth.request({method: "eth_sendTransaction"})` at line 5423 / `sol.signAndSendTransaction(vtx)` at line 5296 **with NO freshness check and NO calldata-hash check**.
- The bypass is documented as "richer-error fallback" but is the **only callsite outside `useWalletSigning` doing raw broadcasts against user funds**.
- **Fix**: either (a) make `simulated_calldata_hash` + `simulated_at` mandatory on every emitted `UnsignedStepTransaction` and treat absence as a hard refuse, or (b) remove the Tier-2 fallback entirely and let the hook be the only signer.

### P0-C-002 — invariant_violation card renders as raw JSON FallbackCard (Batch K)
- `src/agent/runtime_invariants.py:435` emits `card_type="invariant_violation"` when I1/I2/I3/I4/I6 enforces a P0 refusal (this is the LAST-RESORT safety override that REPLACES a broken plan payload).
- `web/components/agent/cards/CardRenderer.tsx` switch (lines 612-671) has **NO case for "invariant_violation"** → falls through to `FallbackCard` (lines 598-605) which renders a raw `<pre>` JSON dump.
- **User impact**: when the runtime invariant layer fires (the most critical safety mechanism), the tester sees a wall of unstructured JSON instead of a clean refusal explaining what was prevented.
- **Fix**: add `case "invariant_violation"` in CardRenderer with a structured refusal UI (typed code, affected_step_ids, recovery CTA).

## P1 findings (should fix)

### P1-C-003 — 6 backend CardTypes have no TS type AND no CardRenderer case (Batches B, K)
- `web/types/agent.ts:496-504` Literal MISSING from Python `src/api/schemas/agent.py:522-533`: `transfer`, `lp`, `preferences`, `text`, `invariant_violation`, `balance_report`, `no_change`, `pool_deposit_v3`.
- `web/components/agent/cards/CardRenderer.tsx` MISSING cases: same set above + `transfer` already emitted by `src/agent/tools/wallet_transfer.py:144`, `lp` by `src/agent/tools/wallet_lp.py:150`, `preferences` by `src/agent/tools/update_preference.py:43`, `text` by `src/agent/tools/rebalance_portfolio.py:25,45`, `balance_report` emit verified.
- Plus 3 RENDERER-only types (`compound_card`, `rebalance_card`, `migrate_card`, `sentinel`) declared in CardRenderer with no Python schema declaration → schema drift in the OTHER direction.
- Generator `scripts/gen_agent_types.py` has not been re-run since wave-8.
- **Fix**: re-run schema generator + add the 7-8 missing CardRenderer cases. (P0-C-002 is the most critical of these — invariant_violation must render structured.)

### P1-C-004 — 10 EVM chains have configs but ChainRegistry can't initialize them (Batch F)
- `src/chains/base.py` has full EVM_CHAIN_CONFIGS entries for: Linea, Scroll, Mantle, Blast, zkSync, Gnosis, Celo, Sonic, Berachain, Unichain.
- `src/chains/registry.py:73-81` `rpc_mapping` only includes the original 7 (ETHEREUM/BASE/ARBITRUM/BSC/POLYGON/OPTIMISM/AVALANCHE).
- Any caller doing `ChainRegistry.get_instance().get_config(ChainType.LINEA)` raises `ValueError("Chain 'linea' is not configured. Available: [...7...]")`.
- Static tests (`tests/chains/test_new_chain_configs.py`) pass because they probe Settings/RPC_FALLBACKS/EVM_CHAIN_CONFIGS directly, never going through ChainRegistry.
- Aave V3 + Compound V3 adapter `_CHAIN_IDS` sets also only cover the original 7.
- **Fix**: extend `ChainRegistry.initialize()` rpc_mapping with the 10 new settings fields + add settings_field_fallback path. Extend Aave V3 + Compound V3 chain sets where the protocol has live deployments.

### P1-C-005 — D.5 session-key per-action cap MISSING (Batch H)
- `src/auth/session_keys.py:22` `SessionKeyPolicy` has `spend_cap_24h_usd` + `spend_cap_total_usd` only.
- `can_authorise` at `:73` only checks 24h-rolling + lifetime totals.
- Grep for `per_action|per-action|action_cap|max_per_tx|max_per_action|cap_per_action`: **0 hits across `src/`**.
- Spec D.5 mandates "per-action cap" — current implementation is per-period only.
- **Fix**: add `spend_cap_single_tx_usd` field to `SessionKeyPolicy`, check at `can_authorise`, expose in install endpoint, surface in revoke + audit UI.

### P1-C-006 — §3.1 LiquidityIntent typed envelope is orphaned (Batch A)
- `src/agent/intent/lp_intent_extractor.py::extract_lp_intent` exists with proper OpenRouter constrained-decode JSON-schema setup.
- **Never called by runtime.** Production path uses 30+ regex `_detect_*` dispatchers in `src/agent/simple_runtime.py` (e.g. `_detect_aave_supply` at line 3043).
- Spec §3.1 explicitly says: "Planner extracts a partial LiquidityIntent... outputs are typed structures." Current architecture bypasses this.
- **Fix**: wire `extract_lp_intent` as the primary planner in `simple_runtime.py`. Significant refactor; defer to Phase C v3.

### P1-C-007 — §6d source-token B-path heuristic orphaned (Batch D)
- `src/defi/strategy/source_token_heuristic.py::pick_smart_heuristic_alternative` + `build_redirect_recommendation_card` exist + tested.
- **No `src/` callsite invokes them.** Spec mandates "suggest USDT-native pool with ≥20% APR + ≥50% TVL share" — only the (A)-path exposure_disclosure card is live.
- **Fix**: wire into `build_yield_execution_plan.py` between source-token detection and plan emission.

### P1-C-008 — Coinbase Wallet adapter MISSING (Batch G)
- `web/components/providers/WalletProvider.tsx:68-74` declares `coinbaseEvmAdapter` with `available: false` and `connect/signMessage = missing("@coinbase/wallet-sdk", "Coinbase Wallet")`.
- Spec §10 lists MetaMask/Phantom/Coinbase as supported wallets; adapter shell present but SDK integration stubbed.
- **Fix**: `npm i @coinbase/wallet-sdk`, implement connect/signMessage methods, register in WalletProvider.

### P1-C-009 — §13 row 25 V4 pool-not-init silent fallthrough (Batch J)
- Code `POOL_NOT_INITIALIZED` registered at `src/defi/execution/models.py:129` but NO EMITTER anywhere.
- V4 adapter handles slot0 revert silently (no blocker, placeholder tick falls through).
- Spec says "offer to initialize (warn that the user becomes the de-facto price-setter — high risk)" — current behavior is silent malformed-range risk.
- **Fix**: V4 adapter must emit `POOL_NOT_INITIALIZED` blocker with a structured "initialize or refuse" CTA.

### P1-C-010 — §13 row 27 wrong-spender detector MISSING (Batch J)
- Spec mandates "Builder asserts spender matches the router being used in the next step; if mismatch, refuses."
- No such assertion exists. `APPROVAL_MISSING` is unrelated.
- **Fix**: add preflight check in `src/defi/execution/preflight.py` that diff-checks `step[i].transaction.target` against `step[i+1].transaction.target` (when step[i].action=="approve").

### P1-C-011 — 2 blocker code mismatches (Batch J)
- F07 matrix expects `TOKEN_2022_HOOK`, code emits `TOKEN_2022_HOOK_UNTRUSTED`.
- F10 matrix expects `AGGREGATOR_CIRCUIT`, code emits `AGGREGATOR_CIRCUIT_BREAKER`.
- **Fix**: align matrix expected_blockers with what code actually emits (the longer codes are more descriptive).

### P1-C-012 — D.7 receipt verify uses balance-read, not Transfer-log decode (Batch H)
- `src/defi/verification/receipt_reader.py::verify_receipt` uses ERC20 `balanceOf` after the fact, NPM `positions` RPC, V4 `getPositionInfo`, SPL `getTokenAccountsByOwner`.
- Spec §6g calls this "real log parsing" — current impl is balance-check, not `eth_getLogs` / Transfer-event decode.
- Status depends on spec wording interpretation: if balance-check suffices (semantic equivalence), LIVE; if literal log decode required, PARTIAL.

## P2 findings (track, deferred)

- **§13 17 of 27 rows have NO matrix coverage** — only `test_edge_case_appendix.py` constants sweep. Affects rows: 1, 2, 3, 5, 6, 8, 9, 10, 12, 15, 16, 17, 19, 20, 22, 25, 26.
- **Dead blocker codes**: MEV_FORCE_PRIVATE_LANE, GAS_MODEL_MISMATCH, APPROVAL_MISSING registered in `KNOWN_BLOCKER_CODES` with zero emit sites. Risk: code rot.
- **`/api/v1/agent-health` route name drift** (Batch I) — only `/health` and `/api/v1/health` exposed. Functionally equivalent; spec literal name missing.
- **State machine soft-warn default** (Batch B) — `IL_STRICT_STATE=1` env required for hard refusal; default is logging-only.
- **invariant-violations.log only has test-fixture entries** (Batch H) — no production card_ids logged post-wave-9. Either production traffic is clean OR upstream hasn't sent enough traffic to staging. Not a bug per se but worth noting.

## Phase C v2 fix wave plan

**Wave C2-α (P0, critical)**:
1. Fix `handleSignStep` Tier-2 bypass (P0-C-001) — make sim metadata mandatory.
2. Add `invariant_violation` CardRenderer case (P0-C-002) with structured refusal UI.

**Wave C2-β (P1, important)**:
3. Add 5-7 missing CardRenderer cases + TS types: transfer, lp, preferences, text, balance_report, no_change, pool_deposit_v3 (P1-C-003).
4. Extend `ChainRegistry.initialize()` rpc_mapping for the 10 new EVM chains (P1-C-004).
5. Add `spend_cap_single_tx_usd` to SessionKeyPolicy (P1-C-005).
6. Add `POOL_NOT_INITIALIZED` emitter to V4 adapter (P1-C-009).
7. Add wrong-spender preflight detector (P1-C-010).
8. Fix matrix v4_matrix.py blocker codes for F07/F10 (P1-C-011).

**Wave C2-γ (P2, follow-up)**:
9. Wire `extract_lp_intent` as primary planner (P1-C-006).
10. Wire B-path source-token heuristic (P1-C-007).
11. Coinbase Wallet SDK integration (P1-C-008).
12. Add matrix chains for the 17 uncovered §13 rows.
13. Remove or implement dead blocker codes.

After Wave C2-α + C2-β + retest, Phase C v2 should be 0 PARTIAL / 0 MISSING on the critical P0/P1 set (with P2 items in a documented follow-up backlog).
