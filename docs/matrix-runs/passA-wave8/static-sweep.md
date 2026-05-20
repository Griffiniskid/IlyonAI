# Static sweep — passA-wave8

Scanned: 532 turn files
Files with ≥1 hit: 112
Total pattern hits: 214

## Top patterns (by file count)

| ID | Sev | Files | Hits | Description |
|----|-----|-------|------|-------------|
| AP-140 | P1 | 97 | 198 | 40-hex address (verify if backed by card or freeform) |
| AP-050 | P0 | 5 | 5 | 'slippage band 0.5%' / 'protocol fee ~0.10%' fabrication (E02, E05) |
| AP-190 | P0 | 5 | 5 | Backticked Solidity call signatures (H14 t3/t4) |
| AP-130 | P0 | 4 | 4 | Empty final content with empty card_ids (G03 T4, I03 T3, I05) |
| AP-170 | P0 | 2 | 2 | Card 'status:ready' with 'transaction:null' (composed-plan E07 t4, H06) |

## Per-category breakdown

| Cat | Total files w/ hits | Top pattern (files) |
|-----|---------------------|---------------------|
| A | 16 | AP-140 (16 files) |
| B | 8 | AP-050 (5 files) |
| C | 10 | AP-140 (10 files) |
| D | 13 | AP-140 (13 files) |
| E | 19 | AP-140 (18 files) |
| F | 6 | AP-140 (6 files) |
| G | 16 | AP-140 (16 files) |
| H | 16 | AP-140 (15 files) |
| I | 1 | AP-130 (1 files) |
| e | 7 | AP-130 (3 files) |

## Top-30 most-affected files

- `A11_aave_opt_weth\turn_2.txt` — 3 hits — AP-140
- `B09_morpho_blueprint\turn_4.txt` — 3 hits — AP-140
- `C03_uniswap_v3_native\turn_4.txt` — 3 hits — AP-140
- `C04_slipstream_base\turn_4.txt` — 3 hits — AP-140
- `C12_pancake_v3\turn_4.txt` — 3 hits — AP-140
- `C14_meteora_dlmm\turn_3.txt` — 3 hits — AP-140
- `D09_aave_native_full_cycle\turn_3.txt` — 3 hits — AP-140
- `D09_aave_native_full_cycle\turn_4.txt` — 3 hits — AP-140
- `F02_wallet_chain_mismatch\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_4.txt` — 3 hits — AP-140
- `H08_S8_partial_allowance\turn_3.txt` — 3 hits — AP-140, AP-190
- `H15_S15_wrong_wallet\turn_2.txt` — 3 hits — AP-140
- `A01_aave_base_usdc\turn_1.txt` — 2 hits — AP-140
- `A01_aave_base_usdc\turn_4.txt` — 2 hits — AP-140
- `A01_aave_base_usdc\turn_5.txt` — 2 hits — AP-140
- `A04_compound_base\turn_4.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_4.txt` — 2 hits — AP-140
- `A08_sky_savings_rate\turn_4.txt` — 2 hits — AP-140
- `A09_aave_arb_usdt\turn_4.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_3.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_4.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_1.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_2.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_5.txt` — 2 hits — AP-140
- `D02_aave_supply_withdraw_all\turn_1.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_1.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_3.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_4.txt` — 2 hits — AP-140

## Sample evidence (top-5 patterns)

### AP-140 [P1] — 40-hex address (verify if backed by card or freeform)

- `A01_aave_base_usdc\turn_1.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A01_aave_base_usdc\turn_4.txt`: `0x0b2c639c533813f4aa9d7837caf62653d097ff85`
- `A01_aave_base_usdc\turn_5.txt`: `0x0b2c639c533813f4aa9d7837caf62653d097ff85`
- `A02_steth_lido_filter\turn_2.txt`: `0xae7ab96520de3a18e5e111b5eaab095312d7fe84`
- `A03_low_risk_only\turn_4.txt`: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`

### AP-050 [P0] — 'slippage band 0.5%' / 'protocol fee ~0.10%' fabrication (E02, E05)

- `B01_stable_strategy\turn_1.txt`: `gas estimates, and 0.5%`
- `B02_bear_strategy\turn_1.txt`: `gas estimates, and 0.5%`
- `B06_eth_solana_split\turn_1.txt`: `gas estimates, and 0.5%`
- `B10_pendle_pt\turn_1.txt`: `gas estimates, and 0.5%`
- `B15_pendle_yt_speculate\turn_1.txt`: `gas estimates, and 0.5%`

### AP-190 [P0] — Backticked Solidity call signatures (H14 t3/t4)

- `B06_eth_solana_split\turn_3.txt`: ``deposit(0.2 ETH)``
- `B06_eth_solana_split\turn_4.txt`: ``deposit(0.2\u202fETH)``
- `enso-05\turn_3.txt`: ``deposit(uint256 amount)``
- `enso-10\turn_2.txt`: ``supply(uint256 amount0,uint256 amount1,address to,uint256 deadline)``
- `H08_S8_partial_allowance\turn_3.txt`: ``approve(address spender, uint256 amount)``

### AP-130 [P0] — Empty final content with empty card_ids (G03 T4, I03 T3, I05)

- `enso-10\turn_1.txt`: `"content":"","card_ids":[]`
- `enso-10\turn_3.txt`: `"content":"","card_ids":[]`
- `enso-12\turn_3.txt`: `"content":"","card_ids":[]`
- `I05_session_key_kernel\turn_4.txt`: `"content":"","card_ids":[]`

### AP-170 [P0] — Card 'status:ready' with 'transaction:null' (composed-plan E07 t4, H06)

- `E07_eth_to_base_curve\turn_4.txt`: `"status":"ready","blocker_codes":[],"transaction":null`
- `H06_S6_xchain_native\turn_3.txt`: `"status":"ready","blocker_codes":[],"transaction":null`
