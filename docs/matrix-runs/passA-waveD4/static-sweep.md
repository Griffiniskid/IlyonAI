# Static sweep — passA-waveD4

Scanned: 532 turn files
Files with ≥1 hit: 60
Total pattern hits: 116

## Top patterns (by file count)

| ID | Sev | Files | Hits | Description |
|----|-----|-------|------|-------------|
| AP-140 | P1 | 50 | 105 | 40-hex address (verify if backed by card or freeform) |
| AP-130 | P0 | 10 | 10 | Empty final content with empty card_ids (G03 T4, I03 T3, I05) |
| AP-190 | P0 | 1 | 1 | Backticked Solidity call signatures (H14 t3/t4) |

## Per-category breakdown

| Cat | Total files w/ hits | Top pattern (files) |
|-----|---------------------|---------------------|
| A | 7 | AP-140 (7 files) |
| B | 5 | AP-130 (3 files) |
| C | 9 | AP-140 (8 files) |
| D | 3 | AP-140 (3 files) |
| E | 11 | AP-140 (10 files) |
| F | 2 | AP-140 (2 files) |
| G | 11 | AP-140 (10 files) |
| H | 9 | AP-140 (8 files) |
| I | 2 | AP-130 (2 files) |
| e | 1 | AP-130 (1 files) |

## Top-30 most-affected files

- `B09_morpho_blueprint\turn_4.txt` — 3 hits — AP-140
- `C02_aave_eth_native_refine\turn_1.txt` — 3 hits — AP-140
- `C04_slipstream_base\turn_4.txt` — 3 hits — AP-140
- `C11_compound_base_refine\turn_4.txt` — 3 hits — AP-140, AP-190
- `C12_pancake_v3\turn_4.txt` — 3 hits — AP-140
- `C14_meteora_dlmm\turn_3.txt` — 3 hits — AP-140
- `D08_aave_borrow_repay\turn_3.txt` — 3 hits — AP-140
- `F02_wallet_chain_mismatch\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_4.txt` — 3 hits — AP-140
- `H15_S15_wrong_wallet\turn_2.txt` — 3 hits — AP-140
- `A04_compound_base\turn_4.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_4.txt` — 2 hits — AP-140
- `A08_sky_savings_rate\turn_4.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_1.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_2.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_5.txt` — 2 hits — AP-140
- `D06_curve_withdraw_3pool\turn_3.txt` — 2 hits — AP-140
- `E04_eth_to_opt_aave_usdt\turn_3.txt` — 2 hits — AP-140
- `E04_eth_to_opt_aave_usdt\turn_4.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_3.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_4.txt` — 2 hits — AP-140
- `E06_base_to_arb_yearn\turn_1.txt` — 2 hits — AP-140
- `E09_eth_to_arb_morpho\turn_4.txt` — 2 hits — AP-140
- `E12_eth_to_polygon_aave_usdt\turn_4.txt` — 2 hits — AP-140
- `E13_eth_to_polygon_aave_dai\turn_2.txt` — 2 hits — AP-140
- `E13_eth_to_polygon_aave_dai\turn_4.txt` — 2 hits — AP-140
- `E14_eth_to_avax_aave\turn_4.txt` — 2 hits — AP-140
- `F06_curve_volatile_blocker\turn_1.txt` — 2 hits — AP-140

## Sample evidence (top-5 patterns)

### AP-140 [P1] — 40-hex address (verify if backed by card or freeform)

- `A03_low_risk_only\turn_4.txt`: `0x23238f20b894f29041f48D88eE91131C395Aaa71`
- `A04_compound_base\turn_4.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A07_spark_dai\turn_3.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`
- `A07_spark_dai\turn_4.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`
- `A08_sky_savings_rate\turn_4.txt`: `0xdc035d45d973e3ec169d2276ddab16f1e407384f`

### AP-130 [P0] — Empty final content with empty card_ids (G03 T4, I03 T3, I05)

- `B05_low_risk_only\turn_3.txt`: `"content":"","card_ids":[]`
- `B05_low_risk_only\turn_4.txt`: `"content":"","card_ids":[]`
- `B15_pendle_yt_speculate\turn_3.txt`: `"content":"","card_ids":[]`
- `C05_velodrome_cl\turn_4.txt`: `"content":"","card_ids":[]`
- `E01_eth_to_base_aave\turn_2.txt`: `"content":"","card_ids":[]`

### AP-190 [P0] — Backticked Solidity call signatures (H14 t3/t4)

- `C11_compound_base_refine\turn_4.txt`: ``mint(uint256 amount)``
