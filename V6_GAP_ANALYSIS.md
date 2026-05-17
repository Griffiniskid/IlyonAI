# V6 GAP ANALYSIS — Full Spec/DevPlan Verification

Generated 2026-05-17 from 12 parallel verification subagents reading
`IlyonAi_LP_Execution_Spec.pdf` + `IlyonAi_Development_Plan.md` against
actual code. Each subagent grep'd the codebase + ran live curl where
applicable. **NOT mechanical analyzers** — hand-read by-section.

## Headline

**~70% complete, NOT 98%.** Conversational LP execution surface is the
big miss. Safety scaffolding (state machine, freshness, audit, composed
plan) is solid; typed intent model + simulator + indexer + many invariants
are missing.

## Per-section %

| Section | % | Status |
|---|---|---|
| Spec §1-§5 (foundations + agent loop + plan model + LP intent) | **35%** | LiquidityIntent type missing, no LP action enum, no calldata-hash bind, no Tenderly sim, no State Store, no Indexer service |
| Spec §6 (head-on issues + recovery) | 80% | Architecturally OK, blocker code casing inconsistent, decide_recovery only 2 callsites |
| Spec §7 S1-S15 funding | 67% | 7/15 fully done, 5/15 partial (S11/S14/S12 detector→adapter break), 3/15 not pin-tested (S4/S5/S6) |
| Spec §8-§10 (services) | 70% | allocate_plan + receipt watcher OK; position store missing 5 cols (redemption_program, lockup_end_ts, underlying_custody, position_nft, receipt_mint) |
| Spec §11 D.1-D.8 (safety preflights) | 95% | 7/8 fully live; D.1 topic0 placeholder only |
| Spec §12 PlanStatus | 100% | 12 canonical values present + legacy 7 aliases |
| Spec §13 27-row edge appendix | 55% | 11 GREEN + 12 PARTIAL + 4 RED |
| Spec §14 cross-cutting | 90% | EIP-7702/session keys/audit trail all live |
| DevPlan Phase 0-2 | 50% | Slippage default 100→50, verify() stubs, V3 USD hardcode, Tenderly absent, EntityResolver absent |
| DevPlan Phase 3-5 | 70% | Kamino JLP/JitoSOL fallback live (plan said drop); Phase 4 Indexer + Notifier ENTIRELY MISSING |
| DevPlan Phase 6-7 | 50% | 10 EVM chains missing ChainConfig + RPC + fallbacks — WILL FAIL AT RUNTIME |
| DevPlan Phase A (Enso) | 90% | 6/8 done, A.1 pacing 1.6s vs spec 1.15s, A.2 split across 3 modules |
| DevPlan Phase B (Solana native) | 95% | 4 deposit adapters fully pass 5-point check |
| DevPlan Phase C (lifecycle close) | 50% | 3/6 paths (Orca/Kamino/Marinade); Raydium CLMM/Meteora DLMM/JLP withdraw deferred |
| DevPlan Phase D/E/F/G | 85% | Berachain BEX + Sonic SwapX native adapters absent |

## CRITICAL FINANCIAL-SAFETY GAPS

### 1. No calldata-hash bind sim↔broadcast — §1 invariant violated
- Spec quote: "One Confirm button: produces an artifact hash; the wallet popup's calldata must hash-match this artifact, or signing is refused" + "Enforces simulated_calldata_hash == broadcast_calldata_hash"
- `grep -rn "calldata_hash\|artifact_hash\|hash_match"` returns 0
- Fix: Extend `src/defi/execution/models.py` `ExecutionStepV3` with `simulated_calldata_hash: str` populated by sim. Add `assert_calldata_match(simulated, broadcast)` called from `mark_step_status` before 'submitted'. Mirror in `web/lib/` signer popup.

### 2. S11 / S14 / S12 detector→adapter break (lifecycle BROKEN end-to-end)
- Detectors emit `action="refinance"` (simple_runtime.py:2114), `action="migrate"` (2271), `action="claim_compound"` (2191)
- `uniswap_v3_nft.py:156` actions frozenset = `{deposit_lp, provide_liquidity, add_liquidity, decrease_liquidity, collect, close_position}` — no "refinance"
- `uniswap_v2.py:213` = `{deposit_lp, add_liquidity, provide_liquidity, remove_liquidity, withdraw}` — no "migrate"
- No adapter has "claim_compound"
- `capabilities.py:24` gate REJECTS — adapter never runs
- Pin tests pass because detector-only assertions; end-to-end build fails
- Fix: Extend action frozensets + write multicall bundler for refinance/migrate; write claim+compound 2-step composer

### 3. 10 EVM chains WILL FAIL at runtime
- `EVM_CHAIN_CONFIGS` (`src/chains/base.py:175-246`) has only 7 chains
- Missing: Linea, Scroll, Mantle, Blast, zkSync, Gnosis, Celo, Sonic, Berachain, Unichain
- `RPC_FALLBACKS` (`src/data/asset_registry.py:146-189`) same 7 only
- V3 pool resolver depends on RPC_FALLBACKS → V3 calls to new chains throw
- `src/config.py:47-89` missing `linea_rpc_url` etc.
- `icon_url` mapping missing for 10 new chains
- Fix: Add ChainConfig + RPC URL env-var + RPC_FALLBACKS + icon for each of 10 chains. Verify on-chain Aave V3 / Compound V3 / Curve / Balancer pools live first.

### 4. Solana position state lost on restart
- `solana_yield_builder.py:269-285` sets `step.transaction.redemption_program / receipt_mint / lockup_end_ts / underlying_custody / position_nft` at runtime
- `migrations/versions/20260515_pool_index.py:66` `user_positions` table has NO columns for any of those
- `insert_position` doesn't pull them in
- Result: JLP 1h lockup, Marinade delayed unstake, Sanctum INF redemption — all state lost between sessions
- Fix: Alembic agent_010 migration adds 5 columns. Update `insert_position` + UserPosition dataclass.

### 5. Phase 4 Indexer + Notifier service ENTIRELY MISSING
- Spec §4: "PositionHealth snapshots every 5 min: current value, HODL value, fees collected/uncollected, IL %, in-range bool, time-in-range, realized fee APR"
- `src/defi/position_monitor/` directory does NOT exist
- No PositionHealth model
- No `position_snapshots` / `position_alerts` tables
- No 5-min cadence cron/celery
- Fix: New `src/defi/indexer/position_health.py` + alembic agent_011 + celery beat schedule

### 6. EIP-1559 vs legacy gas auto-detect MISSING
- No `tx_type` / `maxFeePerGas` / `gasPrice` branching in `src/chains/evm/client.py`
- BSC requires legacy; will FAIL or overpay
- Fix: Add `src/chains/evm/gas_pricing.py` with per-chain `_LEGACY_CHAINS = {56, 137}` (etc.); detect baseFee support; route accordingly.

### 7. Self-trade detection MISSING
- Spec §13 row 26: blocker token `SELF_TRADE_AGAINST_OWN_LP` declared, ZERO detection logic
- User can sandwich own LP via pre-swap leg
- Fix: Pre-swap route inspection in `src/shield/self_trade.py` — assert pre-swap pool != user's open V3 NFT position pools.

### 8. Frozen-account preflight MISSING (SPL freeze authority)
- Spec §13 row 5: `FROZEN_ACCOUNT` blocker token, no `is_frozen` runtime check
- User may approve frozen tokens
- Fix: `src/data/solana.py` add `check_account_frozen(mint, owner)` using getMint + getTokenAccountInfo. Wire into Solana preflight.

### 9. JIT mempool monitor MISSING
- Spec §13 row 17: `JIT_ATTACK_ADJACENCY` token, zero implementation
- No 1-block delay, no re-sim-on-large-swap-queued
- Fix: WebSocket subscribe to pending pool, detect >$100k swap queued same block, emit JIT_ATTACK_ADJACENCY blocker + 1-block delay.

### 10. Kamino native SDK calls absent + JLP/JitoSOL Jupiter proxy still LIVE
- Plan §3.2: "Drop the JLP/JitoSOL-proxy fallback at kamino.js:119-138 entirely"
- `kamino.js:22-23` still defines JLP_MINT + JITOSOL_MINT
- `kamino.js:196-235` still routes via `buildSwap → outputMint=JITOSOL_MINT|JLP_MINT` on REST fail
- Plan §3.2: "Use @kamino-finance/kamino-sdk / klend-sdk native program calls"
- Current: REST-only, no native IX build
- Fix: Drop lines 196-235 entirely. Add native IX via `klend-sdk` or hand-roll Anchor disc for `lend.deposit` / `lend.withdraw`.

## SPEC §1-§5 — 23 GAPS

(Conversational LP execution surface ~35% implemented)

1. No `LiquidityIntent` typed schema — `src/agent/intent/defi_intent.py` has `DefiIntent` (search-oriented), lacks LP fields (range, fee_tier, tick_spacing, bin_step, strategy, range bounds)
2. No LP action enum: `ADD · INCREASE · DECREASE · COLLECT · REBALANCE · CLOSE · ZAP_IN · ZAP_OUT · MIGRATE`
3. No pair field on intent; no ETH↔WETH / MATIC↔POL alias map
4. No fee_tier / tick_spacing / bin_step extraction from prompt
5. Only EXACT_USD amount mode (no EXACT_TOKEN0 / EXACT_TOKEN1 / EXACT_BOTH / PROPORTIONAL / PERCENT_OF_POSITION / ALL)
6. No source_token / source_chain typed fields (spec §6d)
7. No Range preset enum: FULL · WIDE · BALANCED · TIGHT · CUSTOM_TICKS · CUSTOM_PRICE
8. No Strategy enum: SPOT · CURVE · BID_ASK (DLMM); MAVERICK_STATIC / RIGHT / LEFT / BOTH
9. No deadline / MEV / stake-rewards toggle on intent
10. No clarifier emit when ambiguous
11. No EntityResolver service — adapter-local helpers scattered
12. No on-chain symbol()/decimals() cross-check
13. No TVL-tiebreak when protocol family head omitted
14. No pair-category fee-tier defaults (stable/stable → 1bp; etc.)
15. `_LiquidityAmounts.getLiquidityForAmount0/1` BigInt math approximated (not full SDK)
16. DLMM bin distribution + V2 1:1 not implemented (no Meteora Python adapter)
17. No slippage budget splitter (15/15/20 split across legs)
18. No dust tracker (per-leg + cumulative > $1 → sweep/leave/increase)
19. **No Tenderly bundle simulator (EVM) / simulateTransaction (Solana) with replaceRecentBlockhash**
20. No typed PreviewCard schema with 6 panels
21. **No calldata-hash bind invariant (spec §1)**
22. StepStatus missing `queued` and `verified` states
23. **No unified State Store keyed by intent_id** — state sharded across DB tables

## SPEC §6 — Blocker code inconsistencies

1. `KNOWN_BLOCKER_CODES` UPPER_SNAKE; emitters lowercase (`unsupported_adapter`, `adapter_build_failed`, `wallet_chain_mismatch`, `aggregator_circuit`) — UI/sanitizer may miss
2. `GAS_TOP_UP` (emitter) ≠ `GAS_TOPUP_REQUIRED` (canonical enum)
3. `AGGREGATOR_CIRCUIT` (emitter) ≠ `AGGREGATOR_CIRCUIT_BREAKER` (canonical)
4. `NULL_ROUTE` not in KNOWN_BLOCKER_CODES; comment-only in `swap_simulate.py`
5. `ADAPTER_QUOTE_REQUIRED` declared, never emitted (dead code)
6. `decide_recovery` invoked from only 2 callsites — per-leg failures in execute_pool_position / wallet_swap don't route through it
7. FailureKind enum missing entries: NULL_ROUTE, AGGREGATOR_CIRCUIT_BREAKER, WALLET_CHAIN_MISMATCH, INSUFFICIENT_BALANCE, GAS_TOPUP_REQUIRED
8. No global "never auto-refund-swap-back" guard (§6f hard rule)

## SPEC §7 S1-S15 — gap details

| # | Status | Gap |
|---|---|---|
| S1-S3 | ✅ done + tested | — |
| S4-S6 | ✅ wired, ⚠️ no scenario-specific pin | composed_plan path generic only |
| S7 | ✅ done + tested | — |
| S8 | ✅ done + tested | — |
| S9 | ⚠️ partial | `_NATIVE_BY_CHAIN` (build_yield_execution_plan.py:1124) missing Sonic "S" native; no GAS_TOP_UP pin asserting code |
| S10 | ⚠️ partial | `_LST_UNWRAP_CHAIN_RE` only matches "Use my X stETH"; spec example "wstETH → ETH/USDC LP" + harness H10 unsupported |
| S11 | ⚠️ DETECTOR→ADAPTER BREAK | uniswap_v3_nft action set lacks "refinance"; capability gate rejects |
| S12 | ⚠️ DETECTOR→ADAPTER BREAK + fragile phrasing | "claim_compound" no adapter; only Aave AAVE→stkAAVE phrasing, not Slipstream/AERO or Compound/COMP |
| S13 | ✅ done + tested | — |
| S14 | ⚠️ DETECTOR→ADAPTER BREAK | uniswap_v2/v3_nft action set lacks "migrate" |
| S15 | ✅ done + tested | — |

## SPEC §13 — 27-row appendix gaps

**RED (4):**
- Row 5: FROZEN_ACCOUNT — token only, no is_frozen check
- Row 17: JIT_ATTACK_ADJACENCY — token only, no monitor
- Row 21: EIP-1559 vs legacy gas — no auto-detect (BSC fails/overpays)
- Row 26: SELF_TRADE_AGAINST_OWN_LP — token only, no detection

**PARTIAL (12):**
- Row 1: STALE_PRICE_FEED — sim-staleness yes, no Pyth/Chainlink 60s feed-age preflight
- Row 4: Token-2022 transfer-hook — only Meteora refuses; no global allowlist enforcement across jlp/orca/raydium/kamino/marinade/sanctum
- Row 6: WSOL wrap/sync-native+close — only JLP verified; other 6 Solana adapters need check
- Row 10: PERMISSIONED_POOL_KYC — token defined, no runtime emit path
- Row 12: Multi-reward APR live pricing — Merkl is stub point
- Row 13: 3-of-5 aggregator failure — code is N-consecutive, not rolling 3-of-5; no Enso→1inch→0x→Kyber chain
- Row 15: ALT split — only count check at 28, no actual tx splitter producing multiple signed txs; no Ledger ~7 outer-IX
- Row 16: MEV_FORCE_PRIVATE_LANE — token only, no auto-flip to MEVBlocker/Jito on >30bps OR >$5k
- Row 20: Permit2 fallback to ERC-20 approve — no wallet-capability detect-and-fallback
- Row 22: Pending-nonce mgmt — auth nonces handled, no broadcast-time `getTransactionCount` next-available
- Row 23: Gas-topup auto-bundle — refuse-only, no opt-in bridge-and-topup
- Row 25: Pool not initialized — V4 only; Whirlpool / Raydium CLMM detection missing

## DEVPLAN PHASE 0-2 GAPS

- P0.1: slippage default still 100bps at `uniswap_v2.py:299,536`; should be 50bps; no `SLIPPAGE.md`
- P0.2: `adapter.verify()` all return `confirmed=False` stubs — not tied to receipt
- P0.3: V3 NFT hardcodes WETH 2300 / WBTC 80000 USD in `uniswap_v3_nft.py:319-325`
- P1.2: Entity Resolver dir `src/defi/resolver/` doesn't exist
- P1.4: No OpenRouter `response_format={"type":"json_schema",...}` structured-output parser
- P1.4: No `CANONICAL_TOOLS.md` allowlist file
- P1.5: `web/hooks/useWalletSigning.ts` absent
- P1.5: `simulated_calldata_hash` field absent (== broadcast_calldata_hash invariant violated)
- P1.5: 30s re-sim freshness not enforced on broadcast path
- P2.0: PipelineState observable pipeline depth unverified
- P2.1: CLGauge fee-vs-emission toggle absent
- P2.2: V4 hook allowlist + frontend `signPermit2Typed` not verified
- P2.3: Orca still uses `prep_swap` at `orca.js:326` after SDK import at :80
- P2.8: full 20-row receipt verification not done (verify() stubs)
- Simulator harness: `src/defi/simulator/` doesn't exist; no Tenderly client; only closed-form `scenario_engine.py`

## DEVPLAN PHASE 3-5 GAPS

- Kamino native SDK (`klend-sdk`) not wired — REST-only
- Kamino JLP/JitoSOL proxy fallback at `kamino.js:196-235` still LIVE (plan §3.2 said drop entirely)
- Adapter base class missing 8 lifecycle methods: `build_increase / build_decrease / build_collect / build_close / build_rebalance / build_withdraw / build_unstake / build_claim`
- **Indexer + Notifier service ENTIRELY MISSING**: no `src/defi/position_monitor/`, no PositionHealth model, no `position_snapshots`/`position_alerts` tables
- `compound_card` / `rebalance_card` / `migrate_card` frontend types absent
- V3 range picker not wired to rebalance flow (no rebalance card type)

## DEVPLAN PHASE 6-7 GAPS

- 10 EVM chains have enum + V3 factories but ZERO ChainConfig + ZERO RPC URLs + ZERO RPC_FALLBACKS + ZERO icon
- LST registry 9 protocols all Ethereum-only (plan called for chains 8453/42161/10/59144 per-chain receipt overrides)
- V2 single-sided zap not shipped (V2 dual-token only)
- Pendle V2 adapter = scaffolding only (3-mode dispatch depth needs verification)
- No standalone `src/auth/solana_session.py` per plan; Solana session signer inline at `eip7702_auth.py:324`

## CHECKLIST — items confirmed DONE

- Spec §5 state machine (23 states, transitions, freshness, composed-plan rebuild)
- Spec §11 D.2-D.8 preflights all fire live on staging
- Spec §12 PlanStatus canonical 12 values
- Spec §14 EIP-7702 + session keys + audit trail
- DevPlan Phase A (Enso) 6/8
- DevPlan Phase B Solana hand-rolled deposits (JLP/Sanctum INF/Raydium native/Meteora DAMM v2 + Vault) — all 4 pass 5-point check
- DevPlan Phase C 3/6 close paths (Orca/Kamino/Marinade)
- DevPlan Phase D/E/G frontend wire + Nexus + Kernel + alembic agent_009 + EIP-7702 routes
- Pool Index ranking formula (exact spec match)
- Position store basics (UserPosition table, insert/find/close helpers)
- Sanitizer for contextual-fallback fabrication (6 classes)
- Cross-chain composed plan (deBridge + LI.FI + Socket)

## ESTIMATED EFFORT TO 100%

Each gap below = subagent-shippable (1-3 hours via parallel dispatch).

- **Critical safety (15 items)**: calldata-hash bind, Tenderly sim, State Store, position store cols, Indexer service, S11/S14/S12 adapter actions, 10 chain ChainConfig+RPC, EIP-1559 detect, self-trade, frozen-account, JIT monitor, Kamino native + drop JLP proxy, GAS_TOP_UP Sonic, S10 phrasing extension, S12 multi-protocol
- **Spec §1-§5 LP intent (23 items)**: LiquidityIntent type, LP action enum, range/strategy enums, EntityResolver, slippage/deadline defaults, dust tracker, slippage budget, alias map, etc.
- **§13 PARTIAL (12 items)**: rolling 3-of-5, MEV auto-flip, ALT splitter, KYC emit, Merkl rewards, etc.
- **Phase 0-2 polish (12 items)**: slippage default, verify() real, USD hardcode, useWalletSigning hook, structured-decoding, CANONICAL_TOOLS, etc.
- **Phase 3-5 (6 items)**: 8 lifecycle methods, Indexer service, compound/rebalance/migrate cards
- **Phase 6-7 (5 items)**: ChainConfig for 10 chains, LST per-chain, V2 zap, Pendle deep, Solana session module
- **Phase B/C remainder (3 items)**: Raydium CLMM close, Meteora DLMM remove, JLP withdraw

**Total: ~75 discrete items.** Parallelizable: ~20 batches of 4-6 items, each batch = 1 hour. **Realistic ETA: 20-30 hours of focused parallel-subagent work.**

## VALIDATION GATE

After all 75 items shipped:
1. Re-run THIS 12-subagent verification sweep
2. Each subagent returns 0 ❌ + 0 ⚠️ for its section
3. Then 3 consecutive clean matrix sweeps with all blockers HONEST per `tests/harness/v4_gaps.py`
4. Then claim 100% complete
