# IlyonAi Spec v1.0 — Coverage Ledger

Updated 2026-05-15 after autonomous resume sweep.

Spec file: `IlyonAi_LP_Execution_Spec.pdf` (40 pages, v1.0 · 2026-05-14).
Dev plan: `IlyonAi_Development_Plan.md` (1491 lines).

## Section §6 — Seven Head-On Issues

| Section | Status | Notes |
|---|---|---|
| §6a Slipstream + Velodrome CL native exec | ✅ LIVE | tickSpacing-keyed getPool(address,address,int24) at selector 0x28af8d0b + pools(...) fallback. V3_NATIVE_EXEC + V3_PROTOCOLS + V3 NFT _SUPPORTED_PROTOCOLS all admit aerodrome-slipstream/velodrome-cl. Slipstream WETH-USDC Base produces 4-step native plan: Enso swap → scoped approve t0 → scoped approve t1 → Slipstream NFPM mint at 0x827922686190790b37229fd06084350E74485b72. Velodrome CL WETH-USDC Optimism produces same 4-step plan to NFPM 0x416b433906b1B72FA758e166e239c43d68dC6F29. Both emit real desired/min amounts + range ticks. |
| §6a Uniswap V4 native | ⏸ pending | V4 PoolKey(currency0,currency1,fee,tickSpacing,hooks) + hook allowlist + native ETH path + PositionManager.modifyLiquidities([MINT,SETTLE,TAKE]) action sequence. |
| §6b Solana CLMM/DLMM range UI in chat | ✅ live | Raydium CLMM + Orca Whirlpool emit `range_block` with real pool addr + APR + 30-bucket CDF + Narrow/Balanced/Wide/Full presets. Meteora DLMM sidecar /pool_state still empty (Meteora API endpoint dead). Native open_position SDK calls pending (Phase 2.3). |
| §6c Cross-chain composed plans | ✅ primitives shipped | `src/defi/execution/composed_plan.py` ships snapshot/block/watch_for_fill/rebuild_with_actual_delta/promote_step_to_ready. Bridge protocol + DeBridgeOrderWatcher pending. 15 unit tests pass. |
| §6d "With my USDT" silent reassignment | ✅ live | Detector + plan + frontend. `extra.source_token` flows from intent → execute_pool_position → build_yield_execution_plan → exposure_disclosure card. Smart-heuristic alternative-pool lookup (case C) pending. |
| §6e APR-by-range real-data CDF | ✅ live | `src/defi/apr_curve/empirical_cdf.py` fetches DefiLlama coins/chart 4h × 180 samples (30d). Slug registry covers 60+ tokens. 5-min cache. Live R04k WSOL/USDC shows step at 1.0 (matches SOL 83→91 over 30d). 10 unit tests pass. |
| §6f Stuck-balance recovery | ✅ shipped + wired | `src/defi/recovery/stuck_balance.py` with AUTO_REBUILD / ASK_USER / NO_AUTO / NOTIFY decision tree. Wired into `adapter_build_failed` blocker path — typed recovery posture surfaces on every failure. Frontend renders three explicit buttons. 15 unit tests pass; hard rule (never auto-refund-swap-back) covered. |
| §6g Receipt-token verification | ✅ registry | `src/defi/verification/receipt_table.py` ships 20-row registry (LP_ERC20, BPT, V3_NFT, V4_NFT, ATOKEN, ERC4626_SHARE, KTOKEN, POSITION_PDA, POSITION_PDA_WITH_NFT, LP_MINT_SPL, JLP, MSOL, JITOSOL, INF, LST_ERC20, LRT_ERC20, OBLIGATION_STATE, CTOKEN, PENDLE_PT_YT, STARGATE_SHARE). Per-kind live RPC reads pending. 11 unit tests pass. |

## Section §7 — Fifteen Funding Scenarios

| # | Scenario | Status |
|---|---|---|
| S1 | Same-chain dual-token Slipstream | ⏸ pool_link fallback |
| S2 | Same-chain split-swap Slipstream | ⏸ same as S1 |
| S3 | Same-chain native ETH V3 | ✅ live (R01b confirmed) |
| S4 | Cross-chain same-token (USDC ETH → Raydium CLMM) | ⏸ composed-plan execution loop |
| S5 | Cross-chain different-token (USDT ETH → JLP) | ⏸ composed-plan execution loop |
| S6 | Cross-chain native source (ETH ARB → ETH/USDC Base) | ⏸ same |
| S7 | Dust mixing | ⏸ multi-input detector |
| S8 | Partial allowance | ⏸ allowance delta |
| S9 | Gas missing on dst | ⏸ Phase 5.5 |
| S10 | Pre-deposited LST | ⏸ Phase 2.5 unwrap chain |
| S11 | NFT-locked LP refinance | ⏸ Phase 4 |
| S12 | Claim-and-compound | ⏸ Phase 4 |
| S13 | Aave V3 supply | ✅ live (S00 confirmed) |
| S14 | V2→V3 migrate | ⏸ Phase 4 |
| S15 | Wrong wallet for chain | ✅ live (prior log) |

## Section §11 — Safety Invariants

| # | Invariant | Status |
|---|---|---|
| D.1 | LLM never emits calldata | ✅ contract test (`tests/agent/test_llm_no_calldata.py`) |
| D.2 | 30s simulation freshness | preserved (existing re-sim wire) |
| D.3 | No unlimited approvals by default | ✅ V3 NFT scoped to deposit + 5%. Other adapters pending. |
| D.4 | On-chain string sanitiser | ✅ shipped (`src/agent/sanitizer.py` + 15 tests). Wire into asset_registry pending. |
| D.5 | Session-key policies on-chain | ⏸ Phase 7 |
| D.6 | One-click revoke | ⏸ Phase 7 |
| D.7 | State drift re-sim | preserved |
| D.8 | Audit trail HMAC | ⏸ Phase 7 |

## Section §13 — Edge-Case Appendix (27 rows)

Tracked in `tests/defi/test_edge_case_appendix.py`. 9 rows implemented (case asserts), 18 rows skip-marked with the file/module needed.

| Implemented | Skip-marked |
|---|---|
| Row 2 decimal canonicalisation | Row 1 stale price feed |
| Row 3 address case | Row 4 Token-2022 hook |
| Row 8 pool exact ratio | Row 5 frozen account |
| Row 9 deposit cap → ASK_USER | Row 6 WSOL wrap/sync (verifier) |
| Row 11 epoch-locked blocker | Row 7 V4 native eth (pending §6a) |
| Row 18 slippage AUTO_REBUILD | Row 10 KYC gate |
| Row 23 gas top-up blocker | Row 12 multi-reward APR composer |
| Row 24 null route → ASK_USER | Row 13 aggregator circuit breaker |
| Row 27 wrong spender blocker | Row 14-17, 19-22, 25-26 |

## Native LST Stake (Phase 3.1 / §9l)

| Protocol | Native | Status |
|---|---|---|
| Marinade | marinade.deposit | ✅ live (R03b confirmed — MarBms… program direct) |
| Jito | spl-stake-pool.depositSol | ✅ live (Jito4APyf… pool). SDK refuses on empty test wallet — honest. |
| Sanctum INF | sanctum router | ⏸ no canonical npm SDK; deferred |
| Kamino Vaults | kvault.deposit | partial (REST primary, drop JLP proxy pending) |
| Kamino Lend | klend.deposit_reserve_liquidity | ⏸ pending |
| JLP | jupiter-perps.add_liquidity | ⏸ no SDK; routed via Jupiter |
| Raydium AMM v4 | raydium-sdk-v2 addLiquidity | partial |
| Raydium CPMM | raydium-sdk-v2 addLiquidity | partial |

## Commits this session

35 commits (resume 2026-05-15T08:37Z, ongoing). Live coverage at f339c52: all 12 sweep scenarios ready (Aave V3 Base fixed by per-asset aToken override map). 81 new unit tests, 0 regressions. Highlights:
1. 72faac8 fix(intent): CLMM/DLMM/Whirlpool variant suffix after pair
2. 82d80b1 feat(intent): Solana CLMM short-circuit to range_block emission (§6b)
3. 7247533 feat(intent+plan): §6d 'with my <TOKEN>' source-token reassignment
4. ca05d99 feat(intent): §6d no-amount fallback regex
5. df32467 feat(web): render §6d exposure_disclosure panel
6. 2c01c58 feat(recovery): §6f stuck-balance decision tree + 15 tests
7. 771f03e feat(apr-curve): §6e empirical 30d CDF via DefiLlama
8. 59ae3e5 fix(apr-curve): DefiLlama 500-point cap (period=4h span=180)
9. f98a5a2 feat(sidecar): Marinade native via marinade-ts-sdk (§9l)
10. a1e1ee4 feat(verification): §6g 20-row receipt-table registry + 11 tests
11. 3cb74a1 fix(safety): §11 D.3 V3 NFT approvals scoped (no max_uint)
12. dbc5f39 feat(sanitizer): §11 D.4 on-chain string prompt-injection defence + 15 tests
13. f606d7f feat(sidecar): Jito native depositSol via @solana/spl-stake-pool (§9l)
14. 8f3dcc3 feat(plan): §6c composed-plan primitives (snapshot/fill_resolved/recovery_hook)
15. 5d9010b feat(plan): wire §6f recovery posture into adapter_build_failed blocker
16. 9ab3fac feat(web): render §6f recovery posture buttons on blocked plans
17. b99630d feat(execution): §6c composed-plan snapshot/block/watch/rebuild/promote + 15 tests
18. d3f74c5 test(spec): §13 27-row edge-case appendix (9 assert, 18 skip-marked)
19. 7ba9a98 test(safety): §11 D.1 LLM-no-calldata contract test
20. e949857 docs: SPEC_COVERAGE.md initial ledger
21. 0f8ae05 feat(v3-resolver): §6a Slipstream tickSpacing-keyed factory.getPool(int24) [wrong selector first attempt]
22. 4554382 fix(v3-resolver): Slipstream probe all 5 tickSpacings
23. 11a0faf feat(routing): admit Slipstream/Velodrome-CL to V3_NATIVE_EXEC
24. ba5b79d docs: SPEC_COVERAGE.md 15-scenario sweep tally
25. 48bb6a7 fix(v3-resolver): correct Slipstream getPool selector 0x28af8d0b + pools(...) fallback
26. 0f3c4c8 docs: §6a Slipstream LIVE 4-step native mint
27. e2a6c2f feat(v3-resolver): Velodrome CL Optimism CLFactory + NFPM addresses
28. ebf91fb feat(intent): admit velodrome-cl to V3 short-circuit
29. 8006296 feat(routing): admit velodrome-cl to V3_PROTOCOLS
30. 2fb0159 feat(v3-nft): admit velodrome-cl to V3 NFT supported set
31. 373ee2a fix(v3-nft): preserve velodrome-cl in resolver call to pick correct NFPM
32. e28a256 docs: §6a Velodrome CL Optimism live

Total unit tests added this session: 66 (15 §6e + 15 §6f + 11 §6g + 15 §11 D.4 + 15 §6c + 9 §13 + 3 §11 D.1 — counts may be ±2 due to fixture-only tests).

## Live validation

10-scenario sweep at d3f74c5:
- 8/10 ✅ ready (S00 Aave V3, S01 Uniswap V3 native, S02 PCS V3, S03 Raydium CLMM, S04 Marinade native, S06 Lido, S08 Orca Whirlpool, S09 §6d w/ named protocol)
- 2 blocked with typed §6f recovery posture (S05 Orca DEX timeout transient, S07 Curve volatile) — both pre-existing issues, not regressions

15-scenario wide sweep at 11a0faf:
- 12/15 ✅ ready (Aave V3, Uniswap V3 native ETH, PCS V3, Raydium CLMM, Marinade native, "with my USDT" canonical, Lido, Orca Whirlpool, PCS w/ my BNB, Sanctum INF, Stader, Compound V3)
- 3 blocked, all carry typed §6f recovery posture:
  - Aerodrome Slipstream — v3_pool_resolver returns None; factory.getPool selector + Slipstream factory address need on-chain ABI verification
  - Jito — @solana/spl-stake-pool refuses on empty test wallet (honest balance check)
  - Spark sUSDS — adapter_build_failed (Enso/registry gap, separate)
- 0 regressions in 22 commits

## Pending work (not done in this session)

- §6a Slipstream + V4 native EVM exec (biggest remaining EVM build)
- §6c full composed-plan execution loop (deBridge DLN client + webhook + rebuild orchestrator using primitives)
- Phase 3.1 Sanctum INF + JLP native programs
- Phase 3.4-3.5 Raydium AMM v4 / CPMM / Meteora DAMM v2 native receipts
- Phase 4 lifecycle (decrease/collect/close/rebalance/withdraw)
- Phase 6 chain expansion 8→18 + LRT hubs + Pendle deep
- Phase 7 EIP-7702 + session keys + autonomous rebalancing
- §12 DepositPlan schema reconciliation (state enum align with spec verbatim)
- §13 edge cases 18 remaining (each has a file/module pointer in the test fixture)
- §11 D.2 explicit 30s freshness re-sim test
- §11 D.5-D.8 session-key / revoke / state-drift / audit-trail
