# Matrix Pass A — Wave 5 — Category A findings

`SUMMARY: CLOSED=2 STILL=7 MUTATED=3 NEW=4 P0_REMAINING=3 P1_REMAINING=11`

## CLOSED (2)
- **A01 t3 4 kB CoT after alloc table** — body-scan strong regex fired.
- **A15 t1+t2 "Your Swell Supply transaction for 0.05 ETH is ready"** — `_FREEFORM_TX_STATE_HALLUCINATION_RE` fires; both turns return canonical refusal.

## STILL — P0/P1 carry-over
- **A11 t2 WTG3 native-ETH double-count** (P0) — `assets_required:{"WETH":"0.1","ETH":"0.1"}` + INSUFFICIENT_BALANCE on WETH while step 0 wraps ETH → WETH. User with 0.1 ETH locked out.
- **A10 t3+t4 GAS_TOPUP math** (P1) — `Need ~69.606149 MATIC (~$6.30)` → implied $0.09/MATIC vs real $0.20-$0.25.
- **A05 t4 / A06 t3 90s outer-transport timeouts** (P1) — allocation Sentinel-decoration step still exceeds 90s on reused pools.
- **A07 t1 Spark DAI search empty filters** (P1) — search args `chains:[], product_types:[], risk_levels:[]`.
- **A03 t1 stablecoin classifier false-positives** (P1) — mainstreet/apyx/re/fx/falcon all `risk_level:"LOW"`.
- **A11/A15/A16/A17/A18 weth9-wrap link_only** (MUTATED P1) — now graceful link-only with notice but LST adapters for Swell/Kelp/Frax/Mantle still missing.
- **A02 t3 / A05 t3 inconsistencies** (MUTATED P1) — mezo `chain:"mainnet"`; "8 pools / 3 chains" wording vs 5 positions × 4 chains; `$1,065 ≈ 0.5 ETH` impossible.
- **A01/A06/A08 t3 reasoning template mismatch** (MUTATED P1) — A08 says "$31.25 across 8 pools / 6 chains" while table shows 5 × $50 / 5 chains.

## NEW wave-5 (4)

### NEW-A-W5-01 (P0) — A09 t3 multi-kB CoT after structured block
Body-scan strong regex did NOT fire. Final.content has clean alloc table + "Total $500 across 7 positions — blended APY ~80%" followed by 30+ lines: "We need to allocate $500 across the same pools surfaced in prior turn… No explicit weighting request, so default to even split. So 7 pools => weight = 100/7 ≈ 14.2857% each… Plug w=14.284, w_h=14.296" — same shape as A01 t3.
Root cause: body-scan only fires if no markdown-table comes first; once a valid table is emitted, the rest is treated as legitimate prose.
Fix: `_BODY_SCRATCHPAD_STRONG_RE` must scan past the markdown closing line, not stop at first table.

### NEW-A-W5-02 (P0) — A17 t2 instructional tx-flow hallucination bypasses guard
"approve the contract for 0.05 ETH, then submit the stake transaction. Staking on Mantle carries MEDIUM risk… Once signed, you'll receive a transaction hash you can track on a Mantle explorer." `card_ids:[]`. Future-tense ("you'll receive") evades the past-tense / present-tense patterns.
Fix: extend regex with `you('|')?ll\s+(?:receive|get)\s+a\s+(?:tx\s+|transaction\s+)?hash`, `submit\s+the\s+(?:stake|supply|deposit|swap|bridge)\s+transaction`, `approve\s+the\s+contract\s+for`.

### NEW-A-W5-03 (P1) — A02 t2 empty final.content
`"content":"","card_ids":[]` — refusal turn returns empty string. UX broken (blank assistant bubble).
Fix: post-sanitizer guard must substitute canonical refusal text when content collapses to empty.

### NEW-A-W5-04 (P1) — A16 t2 cross-protocol contradiction
Frax stake refusal recommends "Lido, Swell, Bifrost, or Stader" but in same wave-5 run A15 routes Swell to `link_only` (not supported) and A02 marks Lido "No verified adapter".
Fix: freeform LST suggestion list must filter to LST protocols with verified adapters.

## Verdict
2 closed (A01 + A15), 7 still, 3 mutated, 4 new. Body-scan strong regex still misses CoT that uses "we need to" stems after a markdown table (A09 t3). NEW-A-W5-02 reveals a guard-bypass class (future-tense narration).
