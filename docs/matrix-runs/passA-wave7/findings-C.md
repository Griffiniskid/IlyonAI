# Matrix Pass A — Wave 7 — Category C findings

`SUMMARY: CLOSED=4 STILL=10 MUTATED=2 NEW=5 P0_REMAINING=3 P1_REMAINING=7`

## CLOSED (4)
- **P0-C-01 Velodrome "Approvals are already in place"** — zero hits across all 60 wave-7 turns.
- **N-C-W5-01 JSON over-scrub** — wallet JSON intact.
- **P0-C-02 Raydium freeform (C15)** — wave-7 emits proper ADAPTER_BUILD_FAILED blocker (en-dash regex + freeform guard caught C15 path).
- **NEW: Lido `supply` verb-guard (C13 T4)** — VERB_NOT_SUPPORTED blocker.

## STILL (10)
### P0
- **P0-C-W4-01 PancakeSwap V3 token0/token1 ADDRESS↔SYMBOL inversion** — C12 T4 still ships wrong-side mint calldata to BSC mainnet.
- **P0-C-04 verb/asset/calldata desync** — C05/C07/C08/C09/C10/C06 T2/T3 all desynced.
- **P0-C-02 MUTATED Raydium freeform on C14** — STILL fabricates Raydium pool address + fake Phantom approval (sanitizer fixed C15 but not C14).

### P1
- P1-C-01..03 degenerate V3 self-paired drafts.
- P1-C-04 range_preset "narrow" ignored.
- P1-C-09 pool_id:null in every alloc step.
- N-C-01 *-fallback executable:true (44 wave-7 files).
- N-C-W6-01 90s outer-transport timeout (C09 T2 + C10 T3).
- **N-C-W6-02 (P0) C10 T3/T4 false footer "3 of 5 cannot be signed"** — all 5 alloc rows executable:true, footer hard-coded stale count.
- N-C-W6-04 C15 T1 `usd_equivalent:1.0` for 1 SOL.
- **N-C-W4-02 Plan-cache replay** — 6 of 15 turns affected.

## MUTATED (2)
- N-C-W6-02 footer moved from T3 to T4 (T3 timed out).
- P0-C-02 Raydium MUTATED — C15 fixed, C14 not.

## NEW (5)
- **N-C-W7-01 (P0) C14 T3 `usd_value:4.99808435474501e+30`** — spark token (5310 units × 9.4e+26 per token); pollutes downstream USD gates.
- **N-C-W7-02 (P1) C13 T1 TOOL_TIMEOUT 45s on Lido stake** — canonical happy-path regression.
- **N-C-W7-03 (P0) C08 FX-perp pools ship `executable:true`** — gmtrade USDCHF/USDCAD/USDJPY tagged solana-yield-builder-fallback executable:true; allocated $50 each Supply USDC.
- **N-C-W7-04 (P1) C14 T2/T4 freeform Raydium Phantom-approval persists** — fake ERC20-style approval prescribed on Solana.
- **N-C-W7-05 (P2) C13 T2/T3 message says "Arbitrum-specific pool data"** when context was Compound Base — cross-thread context leak.

## Verdict
Velodrome + JSON closures held. Lido verb-guard works. PancakeSwap V3 inversion STILL on BSC mainnet calldata. C14 Raydium freeform still invents pool address + Phantom approval. Two fresh P0s: USD overflow + FX-perp executable:true.
