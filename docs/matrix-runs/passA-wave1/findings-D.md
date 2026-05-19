# findings-D — matrix Pass A wave 1, category D (lifecycle: close / withdraw / migrate / refinance)

**Scope**: `docs/matrix-runs/passA-wave1/D01..D15/turn_*.txt` — 15 chains, 60 turns.
**Verdict**: FINDINGS. P0=7, P1=10, P2=4.

EXPECTED_BLOCKED chains (D05 t1+2, D12 t3, D13 t3, D14 t4, D15 t3) verified and excluded from bug counts.

## P0 (Blocker / Calldata wrong / Hallucinated / Spec violation)

### D-P0-01 — `0xaaaa…aaaa` placeholder wallet baked into live calldata (FALSE POSITIVE)
- **Hit**: D02 t4 (Aave V3 withdraw Base USDC), D05 t2/t4 (Balancer Vault joinPool sender + recipient), D06 t2/t4 (Curve Enso shortcut recipient), D07 t2/t3 (Yearn ERC-4626 withdraw receiver+owner), D08 t1/t2/t3/t4 (Aave V3 supply onBehalfOf), D09 t2 (WrappedTokenGatewayV3.withdrawETH), D09 t3 (depositETH).
- **Aggregator note**: `0xaaaa…aaaa` IS the matrix test wallet (`tests/harness/v4_runner.py:35`). Plans correctly substitute it. **DISMISSED** (same triage as P0-A-03/04/05).

### D-P0-02 — D01 close_position blocked by `invalid_amount` validator (spec §13 V3 NFT close broken)
- D01 turn 3: `{action:"close_position", token_id:12345, amount_in:0}` rejected with `invalid_amount: amount_in must be a positive decimal value`. Close-with-token-id should bypass positive-amount gate — close burns the NFT entirely (decreaseLiquidity + collect + closePosition, no fresh amount).
- **Fix**: whitelist `action ∈ {close_position, withdraw_all, redeem_max}` past positive-amount gate.

### D-P0-03 — D03 Compound claim+withdraw never bundled atomically
- D03 turns 2/3/4: user asked for claim then withdraw, but every turn parsed as `action=supply`. T2 freeform refusal; t3+t4 duplicate `Compound V3 Supply` plan. No `claimRewards()` → `withdraw()` bundle emitted.
- **Fix**: verb router must recognize "claim and then withdraw" as `multi_step_plan`.

### D-P0-04 — D11 t3 hallucinated protocol slug + wrong chain_id
- D11 t3 execution_plan_v2: `protocol="via-secondary-market-on-jupiter"`, title "Stake JITOSOL on Via Secondary Market On Jupiter", `chain_id=1` (Ethereum), `estimated_gas_usd=8.0`. JITOSOL is Solana-only; no such protocol id exists.
- **Fix**: protocol-slug allowlist + chain-kind consistency check (`asset.chain_kind == params.chain_kind`).

### D-P0-05 — D09 t3 false INSUFFICIENT_BALANCE on native-ETH wrap-then-deposit
- D09 t3: user supplies 0.05 ETH; plan emits step 0 = wrap ETH→WETH, step 1 = Aave deposit. Blocker fires: "Need 0.05 WETH, wallet has 0 WETH" — but the wrap step IS the WETH source.
- **Fix**: balance preflight must walk the dependency DAG and credit downstream outputs from prior steps.

### D-P0-06 — D14 t1 raw JS error leaked to user
- D14 t1 (Meteora DLMM deposit) blocker detail: `meteora-dlmm deposit could not be built (Cannot read properties of undefined (reading '_bn')).` Raw `@solana/web3.js` PublicKey error.
- **Fix**: adapter-build wrapper must catch + translate to deterministic error code.

### D-P0-07 — D10 Marinade liquid unstake never produced deterministic plan
- D10 t4: "Unstake 0.5 mSOL via Marinade" → freeform fallback ("open the Marinade app…"). Marinade liquidUnstake is a single IX call and t1 advertised `solana-yield-builder` adapter.
- **Fix**: verb router must dispatch `unstake | liquid_unstake` to solana-yield-builder when adapter advertises support.

## P1 (Logic / Consistency / UX)

- **D-P1-01** Card flag vs footer contradiction ("research only" + "ready via deterministic") in D10/D11/D12/D13 t1 cards.
- **D-P1-02** D13 t1 blended_apy mismatch (319.4% in card vs 296.3% in reasoning text).
- **D-P1-03** D13 t1 reasoning text references "12.5% allocation to each of the eight pools" while card shows 5×20%.
- **D-P1-04** D07 yearn t2 contradicts t1 (UNSUPPORTED_ADAPTER → suddenly ready ERC-4626 withdraw).
- **D-P1-05** D07 t2 description says `withdraw(0)` but calldata uses MAX_UINT256 (withdraw-all). User expects no-op, would drain vault.
- **D-P1-06** D09 t3 `assets_required` double-counts ({WETH:0.05, ETH:0.05}). Real cost 0.05 ETH (wrap internal).
- **D-P1-07** D09 t1+t4 weth9-wrap mis-routed as V2 pool link.
- **D-P1-08** D15 t3 wrong-verb error message + internal debug leak ("kamino-lend deposit could not be built (Kamino REST unreachable… Pass obligation/lendingMarket/lendingMarketAuthority/reserve/reserveSourceColl)").
- **D-P1-09** D09 t3 step labeled `action="approve"` is actually a wrap. UI renders wrong icon.
- **D-P1-10** D02 t1+t3 build_yield_execution_plan TOOL_TIMEOUT (54s and 45s) on Aave V3 Base USDC.

## P2

- **D-P2-01** D12 t2 item 8 symbol `"SOL-"` (sanitizer leaves dangling dash).
- **D-P2-02** D12 t3 protocol slug `"orca-usdc-"` (slugifier trailing-punctuation glitch).
- **D-P2-03** D12 t3 recovery suggests "Try Aave V3" / "Try Compound V3" for a Solana Orca whirlpool CLOSE — wrong category.
- **D-P2-04** D04 t2/t3 V2 remove parsed as `action=supply` (pool_link gate works but verb wrong).

## Summary
- Chains reviewed: 15
- P0 (real): 6 (after dismissing D-P0-01 test-wallet false positive)
- P1: 10
- P2: 4

**Top fixes**:
1. D-P0-02 close-position amount-validator carve-out (blocks entire spec §13 V3 NFT close lifecycle)
2. D-P0-05 balance-preflight DAG-walking (false-blocks every native-token-wrap-then-deposit plan)
3. D-P0-04 protocol-slug allowlist + chain-kind consistency check
