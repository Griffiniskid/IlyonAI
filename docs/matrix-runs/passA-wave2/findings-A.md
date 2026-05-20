# findings-A — matrix Pass A wave 2, category A (research + filter + execute)

**Scope**: `docs/matrix-runs/passA-wave2/A01..A20/turn_*.txt` — 20 chains, 82 turns.
**Verdict**: FINDINGS. **7 CLOSED · 1 PARTIALLY-CLOSED · 4 STILL · 6 NEW** (of 12 wave-1 items + new surface).

**Fix verification**: zero TOOL_TIMEOUT in category A (grep verified across 82 files), zero projection-jump warnings, all blocker codes canonical UPPER_SNAKE.

## Wave 1 → Wave 2 disposition

| Wave 1 finding | Status | Evidence |
|---|---|---|
| P0-A-01 chain mismatch (A01 t3 op vs chain_id:1) | **CLOSED** | A01 t4: chain_id:10, USDC `0x0b2c639c…` (OP), Aave Pool `0x794a6135…` (OP) — fully consistent |
| P0-A-02 A01 t3 three identical approves no supply | **CLOSED** | A01 t4/t5 emit one approve + one supply, distinct selectors |
| P0-A-03/04/05 `0xaaaa…` test wallet | **CLOSED** (carve-out) | Matrix test wallet, not a bug |
| P1-A-01 TOOL_TIMEOUT (A01 t1/t5, A09 t4) | **CLOSED** | A01 t1=18.9s, A01 t5=6ms, A09 t4=14.6s. No TOOL_TIMEOUT anywhere |
| P1-A-02 LLM scratchpad leak (A06 t3) | **STILL + BROADER → escalated P0** | A06 t3 still leaks; A09 t3 now also leaks |
| P1-A-03 dup+truncated tables (A07 t4) | **PARTIAL** | A07 t4 clean; same shape now in A01 t3, A08 t3 |
| P1-A-04 70 MATIC = $6.30 math | **STILL** | A10 t3+t4 same wrong math |
| P1-A-05 INSUFFICIENT_BALANCE WETH on native-ETH path | **STILL + WORSE → escalated P0** | A11 t2 plan now has wrap step + native-ETH gateway, yet still blocks on WETH balance + double-counts |
| P1-A-06 weth9-wrap → link_only | **STILL + BROADER** | A11 t3/t4, A15 t4, A16 t3/t4, A17 t3, A18 t3, A03 t3/t4 |
| P1-A-07 A19 t3 narrated fake plan | **CLOSED** | Now refuses cleanly |
| P1-A-08 Renzo despite Lido filter (A02 t5) | **CLOSED** | A02 t5 routes to lido + VERB_NOT_SUPPORTED refusal |
| P1-A-09 $1,000 placeholder after AMOUNT_NOT_CONFIRMED | **CLOSED** | AMOUNT_NOT_CONFIRMED fires correctly (no card) |

## P0 (wave 2, 2)

### P0-A-W2-01 — A11 t2 WrappedTokenGatewayV3 plan still triggers WETH-balance blocker on native-ETH path
- **Quote**: `"blockers":[{"code":"INSUFFICIENT_BALANCE","title":"Not enough WETH","detail":"Need 0.1 WETH, wallet has 0 WETH."}],...,"steps":[{"action":"approve","title":"Wrap ETH → WETH",...},{"action":"supply","title":"Supply native ETH to Aave V3","transaction":{"to":"0x60eE8b61a13c67d0191c851BEC8F0bc850160710","data":"0x474cf53d…","value":"0x16345785d8a0000"}}],"totals":{"assets_required":{"WETH":"0.1","ETH":"0.1"}}`
- Plan emits wrap-ETH PLUS WrappedTokenGatewayV3.depositETH (both msg.value=0.1 ETH). Preflight asks for ERC-20 WETH balance AND assets_required double-counts. Severity raised because user with 0.1 ETH is locked out of a path the calldata is willing to execute.

### P0-A-W2-02 — Allocation t3 final.content leaks LLM scratchpad verbatim
- **Chains**: A06 t3, A09 t3.
- **Quote (A09 t3)**: `"…We need to allocate $500 across the same pools from prior turn… No explicit weighting bias requested, so default to even split…\n\nWe'll compute: 110.0 + 95.5 = 205.5; +82.1 = 287.6…\n\nNext steps: three short bullets: (a) review allocations, (b) sign transactions one at a time…"`
- Final renderer concatenates LLM thinking trace into published `final.content`. Now systemic across multiple chains. Internal prompt-engineering instructions and CoT visible to end users.

## P1 (wave 2, 7)

- **P1-A-W2-01** GAS_TOPUP_REQUIRED math still wrong (A10 t3+t4: 70 MATIC = $6.30)
- **P1-A-W2-02** weth9-wrap → pool_link link_only (broader: A11/A15/A16/A17/A18/A03)
- **P1-A-W2-03** Truncated final.content (A01 t3 ends `aave-v3 · USD`; A08 t3 ends ` $31.`)
- **P1-A-W2-04** A05 t3 allocation card inconsistencies (mezo `chain:"mainnet"`, blended_apy 54.8% vs final 40.6%, narrative 12.5%×8 vs table 20%×5)
- **P1-A-W2-05** `execute_pool_position` defaults `supply` verb for LST pools (A19 marinade, A20 jito — should pre-translate to `stake`)
- **P1-A-W2-06** Frax intent re-routed to weth9-wrap (A16 t3+t4) — resolver still over-matches generic wrappers
- **P1-A-W2-07** Rocket Pool stake calldata targets rETH ERC-20 (`0xae78736c…`) instead of RocketDepositPool (A13 t4) — **suspected P0, recommend hand-verify against RocketStorage `0x1d8f8f00cfa6758d7bE78336684788Fb0ee0Fa46` → RocketDepositPool before next wave**

## Summary
- Chains: 20, Turns: 82
- Wave-1 disposition: 7 CLOSED, 1 PARTIAL, 4 STILL (of 12)
- Wave-2 P0: 2 (both escalated from wave-1 P1)
- Wave-2 P1: 7
- Verdict: **FINDINGS** — 3 landed fixes hold cleanly, LLM scratchpad leak escalated to systemic P0, WETH-balance preflight regressed to P0
