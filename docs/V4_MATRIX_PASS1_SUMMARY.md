# v4 Pass 1 Summary 2026-05-16

## Categories captured (turn-dir counts; pre-re-fire)
- A 20/20, B 15/15, C 15/15, D 15/15, E 15/15, F 10/10, G 10/10, H 15/15, I 5/5 = 120/120

## Capture quality
- 471 turn files written
- 82 tiny/empty turns (staging restart cascade during pass; being re-fired now)
- 389 valid turns (>200B)

## Final-turn status counts (where chain reached the last turn with a real card)
- PASS (status=ready, card=execution_plan_v3, plausible selector):
  A01 A02 A04 A08 A10 A12 A16 A17 A18 C01 C02 C03 C06 C13 C15
  D03 D09 D10 D11 E01 E02 E03 E04 E05 E12 E13 E14 E15
  F04 F06 F08 G02 G06 G07 G09 G10 H09 H15
  ≈ 38 PASS chains

- BLOCKED with valid recovery posture (honest spec gap, not a regression):
  A07 spark_dai (pool_not_found — search-mode message form)
  A11 aave_opt_weth (adapter_build_failed)
  A19 marinade_sol (gmtrade unsupported)
  C12 pancake_v3 (adapter_build_failed)
  D02 aave_supply_withdraw_all (AUSDC pre-fix — should pass after f9014a2)
  D12 orca_close_whirlpool (close not yet wired)
  D13 raydium_clmm_close (close not yet wired)
  E09 eth_to_arb_morpho (Morpho ERC4626 vault registry gap)
  E11 eth_to_arb_yearn_weth (Yearn WETH vault registry gap)
  F07 token_2022_hook (pool not found — Solana mint w/ hook)
  H01 H02 Slipstream dual-token (missing pool_symbol in extra)
  ≈ 12 BLOCKED chains — all with typed recovery posture

- NO_CAPTURES / partial captures (need re-fire — bg in progress):
  A06 A14 A15 B01 B05 B06 B07 B08 B09 B13 C08 C09 C10 E07 I02
  ≈ 30 chains being re-fired

- Empty card (final turn was text response: "What's TVL?", "Show me X", etc.):
  ≈ 40 chains (chain design — info queries don't return cards)

## v4 commits shipped (27)

Routing + intent fixes:
- 56b7b26 chain stickiness on execute paths
- d2f7dc8 top-one sticky over-rode explicit proto pin (Renzo case)
- 0615e88 allocation hijacked single-protocol deposits
- 80e756c v3 false-refusal + Pool ref-word false-match
- a305d07 _detect_execute_named_proto for 'Execute on PROTO with N TOKEN'
- 15a38a3 _detect_lazy_resume_from_history for vague final verbs
- ea4f23a _detect_lazy_proto_asset_action for 'Execute PROTO ASSET supply'
- e65f3a5 _ENSO_PROTOS_RE expansion (Solana LSTs + versioned protos)
- 0c71122 (?) blue-chip filter
- f9014a2 lifecycle detector bare chain suffix
- 4256a24 action-aware lazy_resume (filter history by verb)
- d128f61 lazy regex expand for largest/biggest/bridge step/each leg
- 8dd4d75 lazy regex expand for withdraw/exit/redeem/repay/claim verbs

Adapters / encoders:
- b1c57ac F.5 Aave V3 native ETH borrow (WTG3.borrowETH 0x66514c97)
- da22c18 Kelp ETH auto-wrap via WETH.deposit prepend
- 26e40ec D.1 deBridge DLN orderId extractor + ReceiptWatcher hook
- ed26750 E.1 Nexus installModule / uninstallModule session-key calldata
- bcbb0ee blue-chip filter expansion

Frontend wires:
- c95521d G.1/G.3 Permit2SigButton wired into ExecutionPlanV3Card
- d3c638c G.2 usePlanStream + bridge_resolution event handler

Tests:
- 571bb57, 7624775, 828e3af, f46be66 — 30+ pin tests across agent/defi/auth

Harness:
- 56b7b26 + eb1827b — tests/harness/v4_matrix.py 120 chains + v4_runner.py + --start-from
