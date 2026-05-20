# findings-B — matrix Pass A wave 2, category B (strategy composition)

**Scope**: 15 chains, 60 turns. **Baseline**: wave 1 (11 P0 + 17 P1; 0/15 clean).
**Verdict**: FINDINGS. **0/15 chains clean. P0=9 (was 11), P1=14 (was 17), -2 P0 / -3 P1.**

## CLOSED (5)

- **P0-B-03 sanitizer 50-line scratchpad leak** — gone.
- **P0-B-09 70-line scratchpad leak (B14 t4)** — gone (truncation now P1-B-14, different form).
- **P0-B-08 cross-turn hallucinated registry** — partially closed (B12 ADPUSDC/ETH-UPEG/ETH-ASTEROID fake set gone; B09 ADPUSDC/CSYUSDC still in cached stub).
- **P1-B-09 wallet-signing prose for Aave V3 Polygon (wave-1 B05 t4)** — gone.
- **P1-B-13 raydium-amm empty-symbol (wave-1 B13 t4)** — gone.

## STILL-PRESENT (22) — wave-1 cluster status

| Cluster | Wave 2 status |
|---|---|
| BSC WBETH stake uses BNB price | STILL (B01/B02/B10/B15 t1; $619/ETH on BSC vs $3,076/ETH mainnet) |
| `verb:"Supply" asset:"USDC"` for every pool | STILL (7 t4 chains uniformly templated) |
| `executable:false` → plan step with `blocker:null` | STILL, **BROADENED** (saturn, camelot-v3, curve-llamalend, pharaoh-v3, yearn-finance, zeebu) |
| Sanitizer leak of chain-of-thought | **CLOSED** ✓ |
| Hallucinated cross-turn pool registry | PARTIALLY CLOSED (B12 closed; B09/B10/B15 still) |
| `requires_signature` decoupled from per-step blockers | STILL (polarity flipped — now `false` while plan has unblocked steps) |
| Raw `curl: (28) timed out` leak | STILL (moved from B02 t2/B08 t2 to B06 t3, B07 t3, B11 t4, B12 t1) |
| Silent cross-chain substitution language | STILL, LATENT (B07 t3 timed out; intent in B07 t2/B08 t1/B13 t1 unchanged) |
| Placeholder `total_usd:"$1,000"` w/ real-$ steps | STILL (all multi-position t4 chains) |

## NEW (1)

### P1-B-NEW-01 — Footer self-contradiction
Hard-coded footer `_⚠ N of N positions cannot be signed automatically… The remaining position(s) will produce a wallet popup._` is contradictory when N=N (e.g. "5 of 5 cannot be signed" + "remaining positions will produce popup"). Affects B03/B04/B06/B12/B13/B14 t4.

## P0 (active, 9)

1. P0-B-01 BSC WBETH BNB-price
2. P0-B-02 executable:false → blocker:null
3. P0-B-03 silent cross-chain substitution (B07)
4. P0-B-04 duplicate calldata across distinct morpho-blue markets (B09)
5. P0-B-05 hallucinated PT-USDC maturity (B10)
6. P0-B-06 hallucinated Pendle YT-USDe ladder (B15)
7. P0-B-07 hyper-APY pools accepted at face value
8. P0-B-08 narrative recommends pool NOT in allocation (B14)
9. P0-B-09 plan/narrative contradiction (B12)

## P1 (active, 14) — 13 carried + 1 NEW (P1-B-NEW-01 footer self-contradiction)

## Verdict

**FINDINGS** — measurable progress on sanitizer leak class (BUG-M01 / BUG-M02 / blocker normalizer all confirmed working). No progress on the 4 wave-1 cross-cluster root causes (BSC ETH-price, executable:false bypass, silent cross-chain substitution, hallucinated Pendle ladders). Category B remains the worst.
