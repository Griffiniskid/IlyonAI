# IlyonAi Development Plan v2 — 75 V7-XXX Gap Closures

**Source of truth:** `V6_GAP_ANALYSIS.md` (12-subagent verification, 2026-05-17).
**Headline:** Real measured completion ~70%. This plan closes all 75 gaps to 100%.
**Validation gate:** Re-run same 12-subagent verification → 0 ❌ + 0 ⚠️ across all sections + 3 consecutive clean matrix passes (120 chains × ≥4 turns, hand-read).

---

## Dispatch Protocol

- 8-12 subagents per wave. Independent file sets only.
- Each subagent: code + pin test + run pytest itself + return diff list.
- Main thread aggregates → stage → commit → push → redeploy after each wave.
- Full regression sweep stays green before push: `pytest tests/agent tests/defi -q --deselect <3 known>`.
- Forbidden ETA: never claim "done" until 12-subagent re-verification returns 0 ❌ + 0 ⚠️.

---

## BATCH 1 — CRITICAL SAFETY (10 tasks)

### V7-001 — calldata-hash bind sim↔broadcast (§1 invariant)
- **Spec quote:** "One Confirm button: produces an artifact hash; the wallet popup's calldata must hash-match this artifact, or signing is refused" + "Enforces simulated_calldata_hash == broadcast_calldata_hash"
- **Current:** `grep -rn "calldata_hash\|artifact_hash"` returns 0
- **Target:** `ExecutionStepV3.simulated_calldata_hash: str` populated by sim. `assert_calldata_match(sim, broadcast)` called from `mark_step_status` before status='submitted'.
- **Files:** `src/defi/execution/models.py`, `src/defi/execution/state_machine.py`, `web/lib/signer.ts`
- **Pin test:** `tests/defi/test_calldata_hash_bind.py` asserts mismatch raises CalldataHashMismatchError
- **Exit:** pytest green + grep returns ≥6 hits

### V7-002 — S11/S14/S12 adapter action sets + multicall bundler
- **Spec quote:** §7 S11 refinance, S14 migrate, S12 claim_compound
- **Current:** detectors emit those actions; adapter frozenset rejects; capability gate refuses
- **Target:** add `refinance` + `migrate` to `uniswap_v3_nft.py` + `uniswap_v2.py` actions; add `claim_compound` to compound/aave/aerodrome/slipstream adapters; write multicall bundler `src/defi/adapters/multicall_bundler.py` for refinance/migrate; write `src/defi/adapters/claim_compound_composer.py` 2-step composer
- **Files:** `src/defi/adapters/uniswap_v3_nft.py:156`, `src/defi/adapters/uniswap_v2.py:213`, new `multicall_bundler.py`, new `claim_compound_composer.py`, `src/defi/capabilities.py:24`
- **Pin test:** `tests/defi/test_s11_s14_s12_end_to_end.py` runs full detector→build→sim, asserts no capability rejection
- **Exit:** capability gate accepts; pytest green

### V7-003 — 10 EVM chains ChainConfig + RPC + RPC_FALLBACKS
- **Chains:** Linea (59144), Scroll (534352), Mantle (5000), Blast (81457), zkSync (324), Gnosis (100), Celo (42220), Sonic (146), Berachain (80094), Unichain (130)
- **Current:** enum + V3 factories only; ChainConfig + RPC missing → runtime AttributeError on Aave/Compound supply
- **Target:** add ChainConfig + RPC URL env-var + RPC_FALLBACKS + icon_url + native token alias for each
- **Files:** `src/chains/base.py:175-246` (EVM_CHAIN_CONFIGS), `src/data/asset_registry.py:146-189` (RPC_FALLBACKS), `src/config.py:47-89` (Settings), `src/data/icons.py` or wherever icon_url lives
- **Pin test:** `tests/chains/test_new_chain_configs.py` asserts each chain has full ChainConfig + RPC + fallback + icon + native alias
- **Exit:** integration test instantiates `EvmClient(linea)`; no AttributeError

### V7-004 — Solana position store 5 cols + alembic agent_010
- **Current:** runtime sets `redemption_program / receipt_mint / lockup_end_ts / underlying_custody / position_nft` but DB has no cols
- **Target:** alembic `20260517_agent_010_solana_position_state.py` adds 5 cols (TEXT nullable except lockup_end_ts BIGINT). Update `UserPosition` dataclass. Update `insert_position` to persist.
- **Files:** `src/storage/migrations/versions/20260517_agent_010_solana_position_state.py`, `src/storage/models/user_position.py`, `src/storage/repositories/position.py` (insert_position)
- **Pin test:** `tests/storage/test_solana_position_state.py` writes+reads, asserts roundtrip
- **Exit:** alembic upgrade applies clean; roundtrip green

### V7-005 — EIP-1559 vs legacy gas auto-detect
- **Current:** no tx_type branching; BSC will overpay or fail
- **Target:** `src/chains/evm/gas_pricing.py` with `_LEGACY_CHAINS = {56, 137}`, baseFee probe via `eth_feeHistory`, route accordingly
- **Files:** new `src/chains/evm/gas_pricing.py`, `src/chains/evm/client.py` (wire into tx-build)
- **Pin test:** `tests/chains/test_gas_pricing.py` with mocked `eth_feeHistory` for BSC (no baseFee) vs Ethereum (has baseFee)
- **Exit:** BSC emits legacy `gasPrice`; ETH emits `maxFeePerGas`

### V7-006 — Self-trade detection (§13 row 26)
- **Current:** SELF_TRADE_AGAINST_OWN_LP token, no detection
- **Target:** `src/shield/self_trade.py` — assert pre-swap pool != user's open V3 NFT position pools
- **Files:** new `src/shield/self_trade.py`, wire into `src/defi/execution/preflight.py`
- **Pin test:** `tests/shield/test_self_trade.py` — user owns USDC/WETH 0.05% NFT; pre-swap routes through same pool → blocker fires
- **Exit:** blocker emits; preflight refuses

### V7-007 — Frozen-account preflight (§13 row 5)
- **Current:** FROZEN_ACCOUNT token, no is_frozen check
- **Target:** `src/data/solana.py` add `check_account_frozen(mint, owner)` using getMint + getTokenAccountInfo. Wire into Solana preflight.
- **Files:** `src/data/solana.py`, `src/shield/preflight_solana.py`
- **Pin test:** `tests/shield/test_frozen_account.py` — mocked getMint returns freezeAuthority + frozen state
- **Exit:** Solana preflight refuses; emit FROZEN_ACCOUNT blocker

### V7-008 — JIT mempool monitor (§13 row 17)
- **Current:** JIT_ATTACK_ADJACENCY token, zero impl
- **Target:** WebSocket `eth_subscribe(newPendingTransactions)`, decode for >$100k swap queued same block, emit blocker + 1-block delay
- **Files:** new `src/shield/jit_monitor.py`, wire into `src/defi/execution/preflight.py`
- **Pin test:** `tests/shield/test_jit_monitor.py` — mocked pending tx queue with $200k swap → blocker fires
- **Exit:** blocker emits; preflight requests 1-block delay

### V7-009 — Kamino native SDK + drop JLP/JitoSOL proxy
- **Plan §3.2:** "Drop the JLP/JitoSOL-proxy fallback at kamino.js:119-138 entirely"
- **Current:** kamino.js:196-235 routes via buildSwap → outputMint=JITOSOL_MINT|JLP_MINT
- **Target:** delete proxy lines; add native IX via @kamino-finance/klend-sdk (or hand-rolled Anchor `lend.deposit`/`lend.withdraw`)
- **Files:** `services/solana-yield-builder/src/adapters/kamino.js`, package.json (add klend-sdk)
- **Pin test:** `tests/services/test_kamino_native.js` — builds native deposit IX, asserts program_id == KLend2g3...
- **Exit:** proxy deleted; native IX built

### V7-010 — Tenderly bundle simulator + Solana simulateTransaction
- **Spec quote:** §4 simulator
- **Current:** `src/defi/simulator/` doesn't exist; only closed-form scenario_engine.py
- **Target:** `src/defi/simulator/tenderly_client.py` POSTs bundle to Tenderly `/simulate-bundle`; `src/defi/simulator/solana_simulator.py` calls RPC `simulateTransaction` with `replaceRecentBlockhash`
- **Files:** new `src/defi/simulator/__init__.py`, `tenderly_client.py`, `solana_simulator.py`, wire into broadcast path
- **Pin test:** `tests/simulator/test_tenderly_bundle.py` mocked, `test_solana_sim.py` mocked
- **Exit:** bundle sim called before broadcast; calldata_hash extracted (feeds V7-001)

---

## BATCH 2 — LP Intent Schema (§1-§5) (10 tasks)

### V7-011 — LiquidityIntent typed schema
- **Spec §3:** typed intent envelope
- **Current:** only DefiIntent (search-oriented); no LP fields
- **Target:** `src/agent/intent/liquidity_intent.py` with pydantic BaseModel — fields: action, pair, fee_tier, tick_spacing, bin_step, strategy, range_preset, range_bounds, amount_mode, amounts, source_token, source_chain, deadline, mev_protection, stake_rewards
- **Files:** new file; update `src/agent/intent/__init__.py` exports
- **Pin test:** roundtrip serialization + validation errors
- **Exit:** import + validate works

### V7-012 — LP action enum
- **Target:** `LpAction` enum `ADD / INCREASE / DECREASE / COLLECT / REBALANCE / CLOSE / ZAP_IN / ZAP_OUT / MIGRATE`
- **Files:** `src/agent/intent/liquidity_intent.py`
- **Pin test:** enum membership
- **Exit:** all 9 values defined

### V7-013 — Range preset enum
- **Target:** `RangePreset` enum `FULL / WIDE / BALANCED / TIGHT / CUSTOM_TICKS / CUSTOM_PRICE` with bps mapping (FULL=∞, WIDE=±20%, BALANCED=±10%, TIGHT=±5%)
- **Files:** `src/agent/intent/liquidity_intent.py`, `src/defi/range_calculator.py`
- **Pin test:** preset→bps mapping
- **Exit:** mapping returns correct bps per preset

### V7-014 — Strategy enum
- **Target:** `LpStrategy` enum `SPOT / CURVE / BID_ASK / MAVERICK_STATIC / MAVERICK_RIGHT / MAVERICK_LEFT / MAVERICK_BOTH`
- **Files:** `src/agent/intent/liquidity_intent.py`
- **Pin test:** enum membership + DLMM mode-dispatch
- **Exit:** enum used by Meteora DLMM adapter

### V7-015 — EntityResolver service
- **Spec §3:** centralized resolver
- **Current:** adapter-local helpers scattered
- **Target:** `src/defi/resolver/entity_resolver.py` — single class with `resolve_token`, `resolve_protocol`, `resolve_pool`, `resolve_chain`
- **Files:** new dir + file, refactor 6 adapter callsites to use it
- **Pin test:** resolves WETH↔ETH alias, MATIC↔POL alias, USDC.e↔USDC chain-disambiguation
- **Exit:** all 6 adapters import EntityResolver; no scattered helpers

### V7-016 — slippage/deadline defaults (50bps + 600s + clamp 10-500)
- **Current:** uniswap_v2.py:299,536 has 100bps
- **Target:** `src/defi/defaults.py` — `DEFAULT_SLIPPAGE_BPS=50`, `DEFAULT_DEADLINE_SEC=600`, `MIN_SLIPPAGE_BPS=10`, `MAX_SLIPPAGE_BPS=500`, `clamp_slippage()`
- **Files:** new `src/defi/defaults.py`, update `uniswap_v2.py`, `uniswap_v3_nft.py`, `aerodrome.py`, `velodrome.py`, `pancake_v3.py`, `kodiak.py`, `slipstream.py`, `swapx.py`
- **Pin test:** `tests/defi/test_slippage_defaults.py`
- **Exit:** grep `slippage_bps=100\b` returns 0 across adapters

### V7-017 — Pair-category fee-tier defaults
- **Spec §3:** stable/stable→1bp, stable/blue→5bp, blue/blue→30bp, exotic→100bp
- **Target:** `src/defi/fee_tier_defaults.py` returning default fee_tier per pair category
- **Files:** new file, wire into V3 LP entry
- **Pin test:** USDC/USDT→100 (1bp), USDC/WETH→500, WETH/WBTC→3000, PEPE/WETH→10000
- **Exit:** all 4 cases pass

### V7-018 — Dust tracker
- **Spec §5e:** per-leg dust + cumulative > $1 prompts sweep/leave/increase
- **Target:** `src/defi/dust_tracker.py` — accumulates per-step deltas, emits DustResolveCard when total > $1
- **Files:** new file, wire into execution post-step
- **Pin test:** 3 legs accumulate $1.20 dust → card emitted
- **Exit:** card type emitted

### V7-019 — Slippage budget splitter
- **Spec §3:** total slippage budget split 15/15/20 across legs (swap/swap/LP-add)
- **Target:** `src/defi/slippage_budget.py` — given total + leg count, returns per-leg
- **Files:** new file
- **Pin test:** 50bps total / 3 legs → 15/15/20 or proportional
- **Exit:** mapping verified

### V7-020 — OpenRouter JSON-schema constrained decoding
- **Plan P1.4:** structured outputs via `response_format={"type":"json_schema",...}`
- **Target:** wrap OpenRouter calls so LP intent extraction uses JSON schema
- **Files:** `src/agent/llm/openrouter_client.py`, `src/agent/intent/lp_intent_extractor.py`
- **Pin test:** request includes `response_format` matching LiquidityIntent schema
- **Exit:** request body includes schema

---

## BATCH 3 — Indexer + Notifier (Phase 4) (5 tasks)

### V7-021 — PositionHealth model + 5-min cadence
- **Spec §4:** PositionHealth snapshots every 5 min
- **Current:** `src/defi/position_monitor/` does not exist
- **Target:** dataclass `PositionHealth(current_value_usd, hodl_value_usd, fees_collected_usd, fees_uncollected_usd, il_pct, in_range, time_in_range_pct, realized_fee_apr)`. Cron via APScheduler 5-min interval.
- **Files:** new `src/defi/position_monitor/__init__.py`, `position_health.py`, `cron.py`
- **Pin test:** dataclass roundtrip + cron registration
- **Exit:** APScheduler job registered

### V7-022 — position_snapshots table + alembic agent_011
- **Target:** `20260517_agent_011_position_snapshots.py` — cols id, position_id FK, snapshot_at, payload JSONB
- **Files:** new migration, new `src/storage/models/position_snapshot.py`, repo
- **Pin test:** insert + query
- **Exit:** alembic upgrade clean

### V7-023 — position_alerts table + alembic agent_012
- **Target:** cols id, position_id FK, alert_type, fired_at, payload JSONB, dismissed_at
- **Files:** new migration, new `src/storage/models/position_alert.py`, repo
- **Pin test:** insert + query alerts not dismissed
- **Exit:** alembic upgrade clean

### V7-024 — out-of-range / fee-APR-drop / TVL-exodus / gas-favorable detectors
- **Target:** `src/defi/position_monitor/detectors.py` — each detector reads recent snapshots, emits PositionAlert if threshold breached (out-of-range >24h, fee-APR drop >50%, TVL exodus >30% in 24h, gas <30 gwei on EVM rebalance candidate)
- **Files:** new file
- **Pin test:** synthetic snapshots → each detector fires correctly
- **Exit:** all 4 detectors tested

### V7-025 — compound_card / rebalance_card / migrate_card frontend types
- **Target:** `web/types/cards.ts` add 3 new card types with discriminated union; renderer in `web/components/cards/`
- **Files:** new TS types + new React renderers
- **Pin test:** Jest snapshot
- **Exit:** TypeScript compiles

---

## BATCH 4 — §13 RED rows (4 tasks — overlaps Batch 1)

### V7-026 — EIP-1559/legacy gas (alias of V7-005)
SKIP — handled in V7-005.

### V7-027 — JIT monitor (alias of V7-008)
SKIP — handled in V7-008.

### V7-028 — Self-trade (alias of V7-006)
SKIP — handled in V7-006.

### V7-029 — Frozen-account (alias of V7-007)
SKIP — handled in V7-007.

---

## BATCH 5 — §13 PARTIAL rows (12 tasks)

### V7-030 — Pyth/Chainlink 60s feed-age check
- **Target:** `src/shield/feed_age.py` — read Pyth/Chainlink feed publishTime; if >60s → emit STALE_PRICE_FEED blocker
- **Files:** new file, wire into preflight
- **Pin test:** mocked feed publishTime 70s old → blocker fires
- **Exit:** blocker fires

### V7-031 — Token-2022 transfer-hook global allowlist
- **Current:** only Meteora refuses; jlp/orca/raydium/kamino/marinade/sanctum lack check
- **Target:** `src/data/solana.py` add `check_transfer_hook(mint)` returning hook program; check against allowlist `{Confidential Transfer, Memo}`. Wire into 6 Solana adapters.
- **Files:** `src/data/solana.py`, 6 adapter files in `services/solana-yield-builder/src/adapters/`
- **Pin test:** mocked mint with unknown hook → refuses
- **Exit:** all 6 adapters call it

### V7-032 — WSOL sync+close across all Solana adapters
- **Current:** only JLP verified
- **Target:** verify orca/raydium/meteora/kamino/marinade/sanctum all emit syncNative+closeAccount IXs around WSOL usage
- **Files:** 6 adapter files
- **Pin test:** `tests/services/test_wsol_lifecycle.js` per adapter
- **Exit:** 6 adapters pass

### V7-033 — PERMISSIONED_POOL_KYC blocker emit path
- **Target:** detect KYC-gated pool (Aave Arc, Compound III KYC variants, Maple); emit blocker pre-build
- **Files:** `src/shield/kyc_pool.py` new, wire into preflight
- **Pin test:** Aave Arc pool address → blocker fires
- **Exit:** blocker fires

### V7-034 — Merkl rewards live pricing
- **Current:** stub
- **Target:** `src/data/merkl_client.py` — fetch live reward token prices via Merkl API + DefiLlama fallback
- **Files:** new file, wire into APR calc
- **Pin test:** mocked Merkl response → APR includes rewards
- **Exit:** Merkl APR shows non-zero

### V7-035 — Rolling 3-of-5 aggregator fallback chain
- **Current:** N-consecutive only
- **Target:** rolling window 3-of-5 fail; chain Enso → 1inch → 0x → Kyber → Paraswap; circuit-break only after 3 of last 5 fail
- **Files:** `src/defi/aggregators/circuit_breaker.py`, `src/defi/aggregators/fallback_chain.py`
- **Pin test:** sequence 3 fail in 5 → break; 2 fail in 5 → continue
- **Exit:** circuit-break logic matches

### V7-036 — Real ALT splitter (multi-signed-tx output)
- **Current:** count check at 28 only
- **Target:** `services/solana-yield-builder/src/adapters/altSplit.js` — real splitter producing multi-signed-tx output; Ledger ~7 outer-IX limit
- **Files:** `services/solana-yield-builder/src/adapters/altSplit.js` (rewrite)
- **Pin test:** input with 35 IXs → 2 txs (each ≤28 IX, ≤7 outer for Ledger)
- **Exit:** multi-tx output returned

### V7-037 — MEV auto-flip to MEVBlocker/Jito on >30bps OR >$5k
- **Current:** MEV_FORCE_PRIVATE_LANE token only
- **Target:** `src/shield/mev_router.py` — if slippage_bps>30 OR notional_usd>5000 → route through MEVBlocker (EVM) or Jito tip (Solana)
- **Files:** new file, wire into broadcast
- **Pin test:** $6000 swap → MEVBlocker URL returned
- **Exit:** routing returns private RPC

### V7-038 — Permit2 wallet-capability fallback to ERC-20 approve
- **Current:** no wallet-capability detect
- **Target:** detect wallet support for Permit2 via `wallet_getCapabilities` (EIP-5792); fallback to ERC-20 approve if unsupported
- **Files:** `src/defi/permit2_fallback.py`, `web/lib/wallet_capabilities.ts`
- **Pin test:** mocked wallet without Permit2 → fallback emits approve IX
- **Exit:** fallback path tested

### V7-039 — Pending-nonce mgmt via getTransactionCount next-available
- **Current:** auth nonces only; broadcast uses static
- **Target:** `eth_getTransactionCount(addr, 'pending')` before broadcast
- **Files:** `src/chains/evm/client.py` broadcast path
- **Pin test:** mocked pending=5 → tx built with nonce=5
- **Exit:** pending-nonce used

### V7-040 — Gas-topup auto-bundle (bridge-and-topup)
- **Current:** refuse-only
- **Target:** opt-in bundle: bridge $X USDC → swap to native gas → original tx
- **Files:** `src/defi/composed/gas_topup_bundler.py`
- **Pin test:** insufficient gas on Arbitrum → bundle suggests bridge $5 from Ethereum
- **Exit:** bundle emitted

### V7-041 — Whirlpool / Raydium CLMM init detection
- **Current:** V4 only
- **Target:** call `whirlpool::getWhirlpool` + `raydium::getPoolState`; if pool absent → emit POOL_NOT_INITIALIZED blocker
- **Files:** `services/solana-yield-builder/src/adapters/orca.js` + `raydium.js`
- **Pin test:** mocked missing pool → blocker fires
- **Exit:** blocker fires

---

## BATCH 6 — Phase 0-2 polish (9 tasks)

### V7-042 — Slippage default 100→50 across all adapters
- **Files:** `uniswap_v2.py:299,536` + all V2/V3 adapters
- **Pin test:** grep `slippage_bps=100\b` returns 0
- **Exit:** all use V7-016 defaults

### V7-043 — verify() real per adapter (tied to receipt watcher)
- **Current:** all return confirmed=False stubs
- **Target:** `BaseAdapter.verify(step, receipt)` parses receipt logs, asserts canonical event signatures emitted (Deposit, IncreaseLiquidity, etc.)
- **Files:** 12 adapter files
- **Pin test:** mocked receipt with Deposit log → confirmed=True
- **Exit:** verify() returns True on real receipt

### V7-044 — V3 NFT USD hardcode kill + live DefiLlama price + 60s cache
- **Current:** `uniswap_v3_nft.py:319-325` hardcodes WETH 2300 / WBTC 80000
- **Target:** `src/data/price_oracle.py` — DefiLlama `/prices/current/<chain>:<addr>` with 60s LRU cache
- **Files:** new `price_oracle.py`, `uniswap_v3_nft.py`
- **Pin test:** mocked DefiLlama response → uses live price
- **Exit:** hardcodes removed

### V7-045 — useWalletSigning.ts extracted hook
- **Plan P1.5:** absent
- **Target:** `web/hooks/useWalletSigning.ts` — wraps wagmi/Solana wallet sign+broadcast with 30s freshness gate
- **Files:** new hook + refactor 3-4 callsites in `web/components/`
- **Pin test:** Jest hook test
- **Exit:** hook used by signer component

### V7-046 — simulated_calldata_hash invariant in PlanStepV2
- **(Covered by V7-001 model change)**
- Confirm model field present + serialization
- **Exit:** field round-trips

### V7-047 — 30s re-sim freshness on broadcast path
- **Target:** if `time.time() - step.simulated_at > 30` → re-sim before broadcast
- **Files:** `src/defi/execution/broadcast.py` (or state_machine.py if inline)
- **Pin test:** 35s old sim → re-sim fires
- **Exit:** re-sim invoked

### V7-048 — CLGauge fee-vs-emission toggle (Slipstream/Aerodrome)
- **Target:** Slipstream + Aerodrome adapters expose `stake_in_gauge: bool` option; route LP NFT to gauge for emission rewards vs keep in wallet for fees only
- **Files:** `src/defi/adapters/slipstream.py`, `aerodrome_v3.py`
- **Pin test:** stake_in_gauge=True → IncreaseLiquidity + Stake bundled
- **Exit:** toggle works

### V7-049 — V4 hook allowlist + Permit2 frontend
- **Target:** V4 hook addresses allowlist `src/data/v4_hooks_allowlist.py` (rebase, dynamic-fee, hook-less); `web/lib/permit2.ts` signPermit2Typed
- **Files:** new files
- **Pin test:** disallowed hook → blocker
- **Exit:** allowlist enforced

### V7-050 — Orca native open_position+increaseLiquidity (drop prep_swap)
- **Current:** `orca.js:326` still uses prep_swap after SDK import at :80
- **Target:** drop prep_swap; use `WhirlpoolClient.openPosition + increaseLiquidity` native IX
- **Files:** `services/solana-yield-builder/src/adapters/orca.js`
- **Pin test:** built IX program_id == Whirlpool program
- **Exit:** prep_swap deleted

---

## BATCH 7 — Phase 6-7 chain coverage (8 tasks)

### V7-051 — ChainConfig 10 chains (covered by V7-003)
SKIP — V7-003.

### V7-052 — RPC env-vars (covered by V7-003)
SKIP — V7-003.

### V7-053 — RPC_FALLBACKS (covered by V7-003)
SKIP — V7-003.

### V7-054 — icon_url 10 chains (covered by V7-003)
SKIP — V7-003.

### V7-055 — LST registry per-chain expansion
- **Plan:** chains 8453/42161/10/59144 per-chain receipt overrides
- **Target:** `src/data/lst_registry.py` — chain-keyed dict; for Base add cbETH receipt 0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22, etc.
- **Files:** `src/data/lst_registry.py`
- **Pin test:** lookup cbETH on Base returns Base address (not Ethereum)
- **Exit:** chain-specific lookup works

### V7-056 — V2 single-sided zap adapter
- **Plan:** V2 dual-token only currently
- **Target:** `src/defi/adapters/uniswap_v2_zap.py` — zapInETH/zapInToken: single-side input → swap half → addLiquidity
- **Files:** new file
- **Pin test:** zapInETH 1 ETH → 0.5 ETH swap to USDC + 0.5 ETH + USDC LP add
- **Exit:** zap builds

### V7-057 — Pendle V2 3-mode deep depth verify + fix
- **Current:** scaffolding only
- **Target:** verify Mint/Redeem/SwapExactPtForToken/SwapExactTokenForPt all dispatch correctly through hosted SDK
- **Files:** `src/defi/adapters/pendle_v2.py`
- **Pin test:** each mode returns valid calldata
- **Exit:** all 4 modes tested

### V7-058 — src/auth/solana_session.py standalone module
- **Current:** inline at eip7702_auth.py:324
- **Target:** extract to `src/auth/solana_session.py` with ed25519 keypair handling, Phantom encryption format
- **Files:** new file + extraction
- **Pin test:** keypair roundtrip
- **Exit:** module standalone

---

## BATCH 8 — Phase B/C remainder (3 tasks)

### V7-059 — Raydium CLMM close (close_position via raydium-sdk-v2)
- **Target:** `services/solana-yield-builder/src/adapters/raydium.js` add `buildClose(positionNft)` using raydium-sdk-v2 `clmm.closePosition`
- **Pin test:** built IX programId == CLMM
- **Exit:** close IX built

### V7-060 — Meteora DLMM removeLiquidityByRange
- **Target:** `services/solana-yield-builder/src/adapters/meteora.js` add `buildRemoveByRange(positionPubkey, binIdFrom, binIdTo)`
- **Pin test:** built IX includes range bounds
- **Exit:** remove IX built

### V7-061 — JLP withdraw (1h lockup gating)
- **Target:** `services/solana-yield-builder/src/adapters/jlp.js` add `buildWithdraw(amount)` gated by lockup_end_ts check
- **Pin test:** lockup not expired → emit JLP_LOCKED blocker; expired → withdraw IX
- **Exit:** gating works

---

## BATCH 9 — §6 blocker code normalization (7 tasks)

### V7-062 — Normalize blocker code casing UPPER_SNAKE
- **Target:** rename lowercase emitters: `unsupported_adapter`→`UNSUPPORTED_ADAPTER`, `adapter_build_failed`→`ADAPTER_BUILD_FAILED`, `wallet_chain_mismatch`→`WALLET_CHAIN_MISMATCH`, `aggregator_circuit`→`AGGREGATOR_CIRCUIT_BREAKER`
- **Files:** grep + replace across `simple_runtime.py`, `swap_simulate.py`, `composed_plan.py`
- **Pin test:** emit each → assert UPPER_SNAKE
- **Exit:** no lowercase blocker codes

### V7-063 — GAS_TOP_UP → GAS_TOPUP_REQUIRED canonical
- **Files:** `build_yield_execution_plan.py:1082-1162` + emit sites
- **Pin test:** emits GAS_TOPUP_REQUIRED
- **Exit:** rename complete

### V7-064 — AGGREGATOR_CIRCUIT → AGGREGATOR_CIRCUIT_BREAKER
- **Covered by V7-062**
- **Exit:** confirmed

### V7-065 — Add NULL_ROUTE to KNOWN_BLOCKER_CODES
- **File:** `src/defi/execution/blocker_codes.py` or wherever KNOWN_BLOCKER_CODES lives
- **Pin test:** NULL_ROUTE in KNOWN_BLOCKER_CODES
- **Exit:** added

### V7-066 — Wire decide_recovery into all blocker callsites
- **Current:** only 2 callsites
- **Target:** per-leg failures in execute_pool_position + wallet_swap route through decide_recovery
- **Files:** `src/defi/execution/pool_executor.py`, `src/defi/execution/wallet_swap.py`
- **Pin test:** failure → decide_recovery called
- **Exit:** callsite count ≥6

### V7-067 — FailureKind enum missing entries
- **Target:** add NULL_ROUTE, AGGREGATOR_CIRCUIT_BREAKER, WALLET_CHAIN_MISMATCH, INSUFFICIENT_BALANCE, GAS_TOPUP_REQUIRED
- **Files:** `src/defi/execution/failure_kind.py`
- **Pin test:** enum membership
- **Exit:** 5 added

### V7-068 — Global "never auto-refund-swap-back" guard
- **Spec §6f:** hard rule
- **Target:** `src/shield/refund_guard.py` — if recovery suggests swapping output back to input → refuse
- **Files:** new file, wire into decide_recovery
- **Pin test:** synthetic refund-swap-back attempt → guard refuses
- **Exit:** refuses

---

## BATCH 10 — §7 phrasing extensions (3 tasks)

### V7-069 — Sonic native + GAS_TOP_UP pin
- **Target:** add `"sonic": "S"` to `_NATIVE_BY_CHAIN` in `build_yield_execution_plan.py:1124`; write `test_sonic_gas_topup_pin.py`
- **Pin test:** Sonic native gas exhausted → GAS_TOPUP_REQUIRED for "S"
- **Exit:** Sonic blocker fires with "S" token

### V7-070 — _LST_UNWRAP_CHAIN_RE for wstETH→LP + harness H10
- **Current:** only "Use my X stETH"
- **Target:** extend regex to match "wstETH → ETH/USDC LP" + H10 phrasing
- **Files:** `src/agent/simple_runtime.py` (regex)
- **Pin test:** H10 phrasing → unwrap detected
- **Exit:** regex matches both phrasings

### V7-071 — _CLAIM_COMPOUND_RE Slipstream/AERO + Compound/COMP
- **Current:** only Aave AAVE→stkAAVE
- **Target:** regex matches "claim AERO and re-stake", "claim COMP and compound"
- **Files:** `src/agent/simple_runtime.py`
- **Pin test:** 3 protocols → all match
- **Exit:** regex matches all 3

---

## BATCH 11 — Spec §1 invariants (4 tasks)

### V7-072 — Global "LLM never emits calldata" runtime gate
- **Spec §1:** hard invariant
- **Target:** sanitizer enhancement — if LLM output includes `0x[a-f0-9]{40,}` outside backed-card-context → strip + log violation
- **Files:** `src/agent/simple_runtime.py` `_strip_unbacked_claims`
- **Pin test:** LLM emits `0xabc…` without card → sanitized
- **Exit:** sanitizer strips

### V7-073 — Session-key mirror on-chain check
- **Spec §14:** session-key state must mirror on-chain
- **Target:** before claiming "session key revoked" — call Nexus `isModuleInstalled` and assert false
- **Files:** `src/auth/session_key_mirror.py`
- **Pin test:** mocked Nexus says installed → "revoked" claim refused
- **Exit:** mirror check works

### V7-074 — One-click revoke action + StepAction enum + adapter
- **Target:** add `StepAction.REVOKE_SESSION_KEY` enum value; Nexus adapter builds uninstallModule calldata
- **Files:** `src/defi/execution/step_action.py`, `src/defi/adapters/nexus.py`
- **Pin test:** revoke action → uninstallModule selector 0xa71763a8
- **Exit:** revoke builds

### V7-075 — Unified State Store keyed by intent_id
- **Spec §1:** state sharded across DB tables currently
- **Target:** `src/storage/state_store.py` + alembic agent_013 `intent_state` table (intent_id PK, status, current_step, payload JSONB, updated_at). Wire as single source of truth for execution.
- **Files:** new migration + new module
- **Pin test:** create, update, read intent state roundtrip
- **Exit:** alembic clean + roundtrip green

---

## Validation Gate (after all 75)

1. Re-run 12-subagent verification (same prompts as V6).
2. Aggregate: each returns 0 ❌ + 0 ⚠️. If any returns issues → dispatch fix-subagent + loop.
3. Fire matrix Pass A: 120 chains × ≥4 turns. Hand-read via 9 category subagents (A/B/C/D/E/F/G/H/I). All blockers HONEST per `tests/harness/v4_gaps.py`.
4. Pass B (re-fire same matrix; expect zero new issues).
5. Pass C (third consecutive clean).
6. `docs/SPEC_COVERAGE.md` updated to 100%.
7. Final commit: `spec(complete): all 75 V6_GAP_ANALYSIS items closed + 12-subagent verification clean + 3 consecutive matrix passes`.

## Hard Rules

- NEVER skip pytest after subagent commit
- NEVER force-push main, NEVER skip hooks/signing, NEVER commit secrets, NEVER deploy prod
- NEVER guess on-chain addresses (WebFetch official docs/explorers)
- NEVER claim 100% without re-running ALL 12 verification subagents + 3 consecutive clean matrix passes
- Mid-pass redeploy = cascade kill. ONE push + ONE redeploy + ONE refire per cycle.
