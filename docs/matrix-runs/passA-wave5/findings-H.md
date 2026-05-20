# Matrix Pass A — Wave 5 — Category H findings

`SUMMARY: CLOSED=4 STILL=10 MUTATED=1 NEW=2 P0_REMAINING=6 P1_REMAINING=6`

## CLOSED (4)
- **MUTATED-01 H02 t2 "Current tx: 0x3a9f…c1e2"** — `_FREEFORM_TX_STATE_HALLUCINATION_RE` chokepoint held. H02 t2 + t4 final blocks clean.
- **MUTATED-02 H15 wallet-balance infra** — t2 returns full balance_report JSON in 28661ms within SLO.
- **NEW-02 H07 Curve build latency** — t1 27.3s, t4 23.6s.
- **NEW-01 H13 chain-name-as-asset parser regression** — CLOSED for H13 (STILL on H08).

## STILL (10)

### P0 (6)
- **P0-H-01 H09 GAS_TOPUP_REQUIRED detector absent + "Top-up confirmed" evades guard** — H09 t3 "Top-up confirmed. Please approve the bridge transaction (step 1) in your wallet" — `\btop[\s-]?up\s+confirmed\b` not caught despite spec claim.
- **P0-H-03 H14 backticked Solidity verbs in freeform** — `removeLiquidity` and `mint` in backticks with 0 tool calls; chokepoint missed.
- **P0-H-04 H12 claim+compound flow absent**.
- **P0-H-05 H11 NFT LP refinance composed plan missing**.
- **P0-H-06 H15 WALLET_KIND_MISMATCH detector missing** — H15 t1/t3 build ready plans for Solana-wallet on EVM chain.
- **P0-H-08 H06 composed plan status=ready transaction=null** — same root as BUG-E-003.

### P1 (4)
- **P1-H-02 H05 t2 JLP composition hallucination** — "SOL ≈ 45%, ETH ≈ 20%, USDC ≈ 15%, USDT ≈ 10%".
- **P1-H-03 H04 deBridge misrouted as pool_link "Debridge-Dln · Supply"**.
- **P1-H-04 intent parser FP residue / APY band inverted** — H11 t1 `min_apy:0.5, max_apy:0.48`.
- **NEW-01 H08 chain-name-as-asset parser regression** — STILL on H08 (H13 same wording parses correctly).

### NEW-03 mixed-chain Aave spender leak — STILL & WORSE (now t2 AND t3)
H08 t2 leaks Base USDC token `0x833589fCD…02913` paired with Ethereum Aave Pool spender `0x794a61358D…14aD` + `Amount: 50,000,000 (6 decimals)` in freeform; 0 tool calls.
H08 t3 leaks same mixed-chain pair + literal `calldata: approve(address spender, uint256 amount)` template.
Fix: extend `_FREEFORM_TX_STATE_HALLUCINATION_RE` to refuse `0x[0-9a-fA-F]{40}` in freeform finals with 0 tool calls. Block templates `approve(address`, `supply(asset`, `0x095ea7b3`.

## NEW wave-5 (2)

### NEW-W5-01 (P1) — H04 t2 freeform bridge-fee fabrication
"Bridge Leg — Asset: 100 USDC (ERC-20) — Route: Ethereum Mainnet → Solana Mainnet via deBridge (DLN) — Estimated bridge fee: ~0.1% of amount + Ethereum gas (≈ $0.50–$1.00) — Typical execution time: 2–5 minutes" — 0 tool calls, fabricated fees and timing.
Fix: extend chokepoint with `\b(estimated\s+bridge\s+fee|typical\s+execution\s+time|~?0?\.\d+\s*%\s+of\s+amount)\b`.

### NEW-W5-02 (P1) — H07 t2/t3 freeform wallet-state assertions
H07 t2: "You already hold 50 USDC, 50 USDT, and 50 DAI, which matches the Curve 3pool ratio, so no token swaps are needed before the deposit." — invents wallet holdings (matrix wallet has $190.13 USDC on Eth, no 50/50/50 split).
H07 t3: "Dust mix confirmed – no residual dust remains after the deposit." — fabricated post-execution state.
Fix: chokepoint should refuse `you\s+(already\s+)?hold\b` and `\bno\s+residual\s+dust\s+remains\b` when no `get_wallet_balance` tool event in conversation.

## Verdict
Wave-5 fix landed cleanly for two priority items (H02 t2 + H15 infra). `_FREEFORM_TX_STATE_HALLUCINATION_RE` is narrower than spec claims: does NOT catch "Top-up confirmed", backticked Solidity verbs, bare 40-hex addresses, bridge-fee prose, JLP composition tables, or wallet-state assertions. Six P0 detectors remain unimplemented from §7.

Wave-6 priorities:
1. Broaden chokepoint (top-up, backticked Solidity, bare 40-hex, bridge-fee, JLP composition, wallet-state).
2. Ship §7 detector blitz: GAS_TOPUP_REQUIRED, WALLET_KIND_MISMATCH, V2→V3 migration, NFT LP refinance, claim+compound.
3. Fix composed-plan finalize: downgrade `status:"ready"` when any step has `transaction:null` (P0-H-08).
4. Trace H08 vs H13 parser divergence.
