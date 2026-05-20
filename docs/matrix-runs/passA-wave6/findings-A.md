# Matrix Pass A — Wave 6 — Category A findings

`SUMMARY: CLOSED=6 STILL=5 MUTATED=2 NEW=6 P0_REMAINING=3 P1_REMAINING=12`

## CLOSED (6)
- **A09 t3 4 kB CoT after structured block** — body-scan + second-heading sanitizer killed post-table CoT.
- **A17 t2 future-tense "you'll receive a transaction hash"** — UNGATED catch worked.
- **A02 t2 empty final.content** — full ExecutionPlanV3 card ships with lido stake via evm-lst-direct-mint.
- **A15 t1+t2 hallucinated tx state** — carry from wave-5, re-verified.
- **A06 t3 + A08 t3 reasoning template** — now match table positions/chains.

## STILL (5)
- **A11 t2 WTG3 native-ETH double-count** (P0) — `assets_required:{"WETH":"0.1","ETH":"0.1"}` + INSUFFICIENT_BALANCE.
- **A10 GAS_TOPUP MATIC math** (P1) — `~69.9 MATIC @ $6.30` implies $0.09/MATIC.
- **A07 t1 Spark DAI search dropped all filters** (P1) — args `chains:[], product_types:[], risk_levels:[]`.
- **A03 t1 stablecoin classifier false-positives** (P1) — mainstreet/apyx/re/fx/falcon all LOW.
- **A15/A16/A17/A18 weth9-wrap link_only + missing LST adapters** (P1).

## MUTATED (2)
- **Outer-transport 90s timeout** — moved from A05/A06 → A01 t4.
- **A02 t3 / A05 t3 inconsistencies** — A02 now consistent; A05 still `chain:"mainnet"` for mezo + new orphan "Low" token in markdown.

## NEW (6)
- **NEW-A-W6-01 (P0) A06 t2 fabricated allocation table in freeform body** — `card_ids:[]` but final.content contains full markdown allocation table with weighted APY + "ready via deterministic adapter (signable transaction can be generated)". Bypasses card sanitizer.
- **NEW-A-W6-02 (P1) A12/A14/A02 t3+t5 VERB_NOT_SUPPORTED for "supply" on LST** — Lido/etherfi refuse plain `supply` verb. UX-hostile; should auto-suggest stake.
- **NEW-A-W6-03 (P1) A04 t3 0%-APY pools top-ranked** — `morpho-blue/CBBTC apy:0.0`, `morpho-blue/WETH apy:0.0`, `aave-v3/CBBTC apy:0.02914`.
- **NEW-A-W6-04 (P1) A19/A17/A16 protocol-name dropped from search** — Marinade/Mantle/Frax keywords lost; returned pools have zero relevance.
- **NEW-A-W6-05 (P1) A05 t3 final.content artifact "Low\n\n_"** — orphan token between table and notice.
- **NEW-A-W6-06 (P1) A16 t2 cross-protocol contradiction** — recommends Swell/Bifrost as LST while adjacent turns mark them research-only.

## Verdict
Body-scan + future-tense + UNGATED-UI fixes held. Bare markdown-table-pretending-to-be-card (A06 t2) is the new bypass class needing closure. A11 WTG3 double-count + A10 MATIC oracle untouched.
