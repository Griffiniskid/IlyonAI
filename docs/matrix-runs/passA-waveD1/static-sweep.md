# Static sweep — passA-waveD1

Scanned: 532 turn files
Files with ≥1 hit: 76
Total pattern hits: 155

## Top patterns (by file count)

| ID | Sev | Files | Hits | Description |
|----|-----|-------|------|-------------|
| AP-140 | P1 | 73 | 152 | 40-hex address (verify if backed by card or freeform) |
| AP-130 | P0 | 3 | 3 | Empty final content with empty card_ids (G03 T4, I03 T3, I05) |

## Per-category breakdown

| Cat | Total files w/ hits | Top pattern (files) |
|-----|---------------------|---------------------|
| A | 14 | AP-140 (13 files) |
| B | 3 | AP-140 (2 files) |
| C | 11 | AP-140 (11 files) |
| D | 6 | AP-140 (6 files) |
| E | 12 | AP-140 (12 files) |
| F | 5 | AP-140 (5 files) |
| G | 11 | AP-140 (11 files) |
| H | 12 | AP-140 (12 files) |
| I | 1 | AP-130 (1 files) |
| e | 1 | AP-140 (1 files) |

## Top-30 most-affected files

- `A11_aave_opt_weth\turn_2.txt` — 3 hits — AP-140
- `B09_morpho_blueprint\turn_4.txt` — 3 hits — AP-140
- `C04_slipstream_base\turn_4.txt` — 3 hits — AP-140
- `C05_velodrome_cl\turn_4.txt` — 3 hits — AP-140
- `C08_morpho_blue_market\turn_4.txt` — 3 hits — AP-140
- `C09_yearn_v3_usdc\turn_4.txt` — 3 hits — AP-140
- `C12_pancake_v3\turn_4.txt` — 3 hits — AP-140
- `C14_meteora_dlmm\turn_3.txt` — 3 hits — AP-140
- `F02_wallet_chain_mismatch\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_4.txt` — 3 hits — AP-140
- `H15_S15_wrong_wallet\turn_2.txt` — 3 hits — AP-140
- `A01_aave_base_usdc\turn_1.txt` — 2 hits — AP-140
- `A01_aave_base_usdc\turn_4.txt` — 2 hits — AP-140
- `A01_aave_base_usdc\turn_5.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_4.txt` — 2 hits — AP-140
- `A08_sky_savings_rate\turn_4.txt` — 2 hits — AP-140
- `A09_aave_arb_usdt\turn_4.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_3.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_4.txt` — 2 hits — AP-140
- `B12_lrt_only\turn_4.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_1.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_2.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_5.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_1.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_4.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_1.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_2.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_3.txt` — 2 hits — AP-140

## Sample evidence (top-5 patterns)

### AP-140 [P1] — 40-hex address (verify if backed by card or freeform)

- `A01_aave_base_usdc\turn_1.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A01_aave_base_usdc\turn_4.txt`: `0x0b2c639c533813f4aa9d7837caf62653d097ff85`
- `A01_aave_base_usdc\turn_5.txt`: `0x0b2c639c533813f4aa9d7837caf62653d097ff85`
- `A02_steth_lido_filter\turn_5.txt`: `0x74a09653a083691711cf8215a6ab074bb4e99ef5`
- `A03_low_risk_only\turn_4.txt`: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`

### AP-130 [P0] — Empty final content with empty card_ids (G03 T4, I03 T3, I05)

- `A02_steth_lido_filter\turn_2.txt`: `"content":"","card_ids":[]`
- `B15_pendle_yt_speculate\turn_3.txt`: `"content":"","card_ids":[]`
- `I05_session_key_kernel\turn_3.txt`: `"content":"","card_ids":[]`
