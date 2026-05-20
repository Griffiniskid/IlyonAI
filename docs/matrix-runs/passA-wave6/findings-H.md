# Matrix Pass A — Wave 6 — Category H findings

`SUMMARY: CLOSED=5 STILL=8 MUTATED=2 NEW=2 P0_REMAINING=6 P1_REMAINING=3`

## CLOSED (5)
- **NEW-W5-01 H04 t2 freeform bridge-fee fabrication** — chokepoint refused.
- **NEW-W5-02 H07 t2/t3 wallet-state assertions** — "you already hold 50 USDC, 50 USDT" + "dust mix confirmed" never reach user.
- **P1-H-02 H05 t2 JLP composition hallucination** — refused.
- **MUTATED-01 H02 t2 tx-state hallucination** — remains closed.
- **MUTATED-02 H15 wallet-balance infra** — t2 returns full JSON within SLO.

## STILL (8)

### P0 (6)
- **P0-H-01 H09 "Top-up confirmed" + GAS_TOPUP table** — H09 t2 emits full markdown table with `~0.001 ETH (~$2)` / `~0.005 AVAX (~$0.15)` fabricated; H09 t3 emits literal "Top-up confirmed". Sanitizer regex still doesn't match.
- **P0-H-03 H14 backticked Solidity verbs** — `removeLiquidity`, `**Mint**`, fee=0.05%, tickLower/tickUpper recipe with 0 tool calls.
- **P0-H-04 H12 claim+compound flow absent**.
- **P0-H-05 H11 NFT LP refinance composed plan missing**.
- **P0-H-06 H15 WALLET_KIND_MISMATCH detector missing**.
- **P0-H-08 H06 + H02 composed plan status=ready with transaction:null** — H06 t3 + H02 t4 both emit alloc cards with all `transaction:null` steps. Wider blast radius than wave-5.

### P1 (3)
- **P1-H-03 H04 deBridge misrouted as pool_link** — `title:"Debridge-Dln · Supply"`.
- **P1-H-04 intent parser FP residue / APY band inverted** — H11 t1 `min_apy:0.5, max_apy:0.48`.
- **NEW-03 H08 mixed-chain spender leak + bare 40-hex** — H08 t2 leaks `0x833589fCD…` (Base USDC) + `0x794a61358D…` (Ethereum Aave Pool) + `Amount: 50,000,000 (6 decimals)` with 0 tool calls. H08 t3 leaks both + literal `calldata: approve(address spender, uint256 amount)` template.

## MUTATED (2)
- **MUTATED-N01 NEW-01 chain-name-as-asset regression spread to H13** — H13 t1 wave-6 parses `asset_in:"BASE"` again (was CLOSED wave-5). H08 same.
- **MUTATED-N02 composed-plan transaction:null bug surfaces in H02 t4** — was scoped to H06; now wider.

## NEW (2)
- **NEW-W6-01 (P1) H02 t2/t3 freeform swap-leg fabrication** — `**Swap leg** – Swap 93.84 USDC → WETH on Base via Aerodrome Slipstream (USDC-WETH pool) - **Estimated gas:** ~0.00045 ETH (≈ $0.80)` with 0 tool calls. `**Split confirmed**` follow-on.
- **NEW-W6-02 (P2) H06 t2 partial-sanitizer cycle** — refusal → user retries verb → composed-plan null-tx ready state.

## Verdict
Wave-6 sanitizer fix landed for three priority items (bridge-fee, wallet-state, JLP composition). Two PRIORITY CHECKS in brief did NOT close: P0-H-01 "Top-up confirmed" (both still emit verbatim despite brief claiming wave-6 regex catches them). Six §7 detectors unimplemented. Composed-plan finalize bug visible in two scenarios — escalate from single-scenario to systemic. Parser regression NEW-01 spread from H08 to H13.

Wave-7 priorities:
1. Verify sanitizer for `\btop[\s-]?up\s+confirmed\b` actually fires (brief claimed wave-6; evidence contradicts).
2. Ship §7 detectors.
3. Composed-plan finalize: downgrade `status:"ready"` to `"blocked"` when ANY step has `transaction:null` — generalize beyond H06.
4. Trace H08/H13 parser regression.
5. Extend chokepoint with `\bswap\s+leg\b`, `\bsplit\s+confirmed\b`, bare `0x[40-hex]` in freeform with 0 tool calls.
