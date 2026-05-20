# Matrix Pass A — Wave 7 — Category A findings

`SUMMARY: CLOSED=4 STILL=8 MUTATED=3 NEW=8 P0_REMAINING=3 P1_REMAINING=13`

## CLOSED (4)
- **A06 t2 markdown-table-pretending-to-be-card** (was P0 NEW-A-W6-01) — refuser template fires, no card_ids, no allocation table.
- **A09 t3** body-scan held.
- **A17 t2** future-tense held.
- **A02 t2** empty content held.
- **NEW-A-W6-06 A16 t2 cross-protocol contradiction** — research-only / ready labels consistent.

## STILL (8)
- **A11 t2 WTG3 native-ETH double-count** (P0) — `assets_required:{"WETH":"0.1","ETH":"0.1"}`.
- **A10 GAS_TOPUP MATIC math** (P1) — `~$0.09/MATIC` implied.
- **A07 t1 Spark DAI** dropped all filters + spurious `stablecoin_only:true`.
- **A03 t1 stablecoin classifier** false-positives.
- **A15/A17/A18 weth9-wrap link_only** — LST adapters missing.
- **NEW-A-W6-04 A19/A17/A16 protocol-name dropped from search** (Marinade/Mantle/Frax).
- **NEW-A-W6-02 VERB_NOT_SUPPORTED on LST** — recovery buttons added (MUTATED) but still blocks.
- **NEW-A-W6-03 A04 t3 0%-APY top-ranked**.

## MUTATED (3)
- Outer-transport 90s timeout — A05 t3 + A02 t5 (was A01 t4).
- A05 t3 final.content orphan token (was "Low", now "$31.25").
- VERB_NOT_SUPPORTED LST — recovery buttons added.

## NEW (8)
- **NEW-A-W7-01 (P0) A06 t3 + A08 t4 execution_plan steps for unsupported protocols** — Supply steps for saturn/gmtrade/pharaoh-v3 marked `executable:false` in source defi_opportunities but shipped with `blocker:null`. Sign would route to wrong protocol via Enso.
- **NEW-A-W7-02 (P0) A03 t3 mainstreet pool_link routed despite "wrong-asset" notice** — notice admits historic financial loss but card still ships `draft / 0 signatures` for same path.
- **NEW-A-W7-03 (P0) A05 t3 mezo `chain:"mainnet"` in allocation + execution_plan** — chain-normaliser broken.
- **NEW-A-W7-04 (P1) A07 t1 search added spurious `stablecoin_only:true`**.
- **NEW-A-W7-05 (P1) A04 t1 reasoning-template mismatch** — Compound query routes to morpho-blue top-5.
- **NEW-A-W7-06 (P1) A05 t3 truncated execution_plan.steps array** — 5 alloc positions, 1 step.
- **NEW-A-W7-07 (P1) A01 t3 allocator weighted 40% into 0%-APY positions**.
- **NEW-A-W7-08 (P1) A05/A08 alloc Supply steps with transaction:null + requires_signature:false**.

## Verdict
Wave-7 closed several sanitizer evasions but introduced new P0s (executable:false protocols in exec_plan, chain mis-normalize, mainstreet routed-despite-notice).
