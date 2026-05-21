# Static sweep — passA-waveD3

Scanned: 532 turn files
Files with ≥1 hit: 54
Total pattern hits: 112

## Top patterns (by file count)

| ID | Sev | Files | Hits | Description |
|----|-----|-------|------|-------------|
| AP-140 | P1 | 51 | 109 | 40-hex address (verify if backed by card or freeform) |
| AP-130 | P0 | 3 | 3 | Empty final content with empty card_ids (G03 T4, I03 T3, I05) |

## Per-category breakdown

| Cat | Total files w/ hits | Top pattern (files) |
|-----|---------------------|---------------------|
| A | 8 | AP-140 (8 files) |
| B | 1 | AP-140 (1 files) |
| C | 8 | AP-140 (7 files) |
| D | 5 | AP-140 (5 files) |
| E | 10 | AP-140 (10 files) |
| F | 3 | AP-140 (3 files) |
| G | 9 | AP-140 (9 files) |
| H | 8 | AP-140 (8 files) |
| e | 2 | AP-130 (2 files) |

## Top-30 most-affected files

- `A11_aave_opt_weth\turn_2.txt` — 3 hits — AP-140
- `B09_morpho_blueprint\turn_4.txt` — 3 hits — AP-140
- `C04_slipstream_base\turn_4.txt` — 3 hits — AP-140
- `C09_yearn_v3_usdc\turn_4.txt` — 3 hits — AP-140
- `C12_pancake_v3\turn_4.txt` — 3 hits — AP-140
- `C14_meteora_dlmm\turn_3.txt` — 3 hits — AP-140
- `F02_wallet_chain_mismatch\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_4.txt` — 3 hits — AP-140
- `H15_S15_wrong_wallet\turn_2.txt` — 3 hits — AP-140
- `A06_morpho_blue\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_4.txt` — 2 hits — AP-140
- `A08_sky_savings_rate\turn_4.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_4.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_1.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_2.txt` — 2 hits — AP-140
- `D02_aave_supply_withdraw_all\turn_1.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_4.txt` — 2 hits — AP-140
- `D06_curve_withdraw_3pool\turn_3.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_2.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_3.txt` — 2 hits — AP-140
- `E04_eth_to_opt_aave_usdt\turn_4.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_1.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_4.txt` — 2 hits — AP-140
- `E09_eth_to_arb_morpho\turn_4.txt` — 2 hits — AP-140
- `E12_eth_to_polygon_aave_usdt\turn_3.txt` — 2 hits — AP-140
- `E12_eth_to_polygon_aave_usdt\turn_4.txt` — 2 hits — AP-140
- `E13_eth_to_polygon_aave_dai\turn_2.txt` — 2 hits — AP-140
- `E13_eth_to_polygon_aave_dai\turn_4.txt` — 2 hits — AP-140

## Sample evidence (top-5 patterns)

### AP-140 [P1] — 40-hex address (verify if backed by card or freeform)

- `A02_steth_lido_filter\turn_2.txt`: `0xae7ab96520de3a18e5e111b5eaab095312d7fe84`
- `A03_low_risk_only\turn_4.txt`: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- `A06_morpho_blue\turn_3.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A07_spark_dai\turn_3.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`
- `A07_spark_dai\turn_4.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`

### AP-130 [P0] — Empty final content with empty card_ids (G03 T4, I03 T3, I05)

- `C08_morpho_blue_market\turn_3.txt`: `"content":"","card_ids":[]`
- `enso-05\turn_4.txt`: `"content":"","card_ids":[]`
- `enso-11\turn_2.txt`: `"content":"","card_ids":[]`
