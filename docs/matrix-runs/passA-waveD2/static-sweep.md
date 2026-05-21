# Static sweep — passA-waveD2

Scanned: 532 turn files
Files with ≥1 hit: 53
Total pattern hits: 114

## Top patterns (by file count)

| ID | Sev | Files | Hits | Description |
|----|-----|-------|------|-------------|
| AP-140 | P1 | 50 | 111 | 40-hex address (verify if backed by card or freeform) |
| AP-130 | P0 | 3 | 3 | Empty final content with empty card_ids (G03 T4, I03 T3, I05) |

## Per-category breakdown

| Cat | Total files w/ hits | Top pattern (files) |
|-----|---------------------|---------------------|
| A | 7 | AP-140 (7 files) |
| B | 3 | AP-140 (3 files) |
| C | 9 | AP-140 (8 files) |
| D | 5 | AP-140 (5 files) |
| E | 9 | AP-140 (9 files) |
| F | 4 | AP-140 (3 files) |
| G | 5 | AP-140 (5 files) |
| H | 11 | AP-140 (10 files) |

## Top-30 most-affected files

- `A11_aave_opt_weth\turn_2.txt` — 3 hits — AP-140
- `B06_eth_solana_split\turn_1.txt` — 3 hits — AP-140
- `B09_morpho_blueprint\turn_4.txt` — 3 hits — AP-140
- `C02_aave_eth_native_refine\turn_1.txt` — 3 hits — AP-140
- `C04_slipstream_base\turn_4.txt` — 3 hits — AP-140
- `C08_morpho_blue_market\turn_4.txt` — 3 hits — AP-140
- `C09_yearn_v3_usdc\turn_4.txt` — 3 hits — AP-140
- `C12_pancake_v3\turn_4.txt` — 3 hits — AP-140
- `C14_meteora_dlmm\turn_3.txt` — 3 hits — AP-140
- `F02_wallet_chain_mismatch\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_4.txt` — 3 hits — AP-140
- `H15_S15_wrong_wallet\turn_2.txt` — 3 hits — AP-140
- `A01_aave_base_usdc\turn_5.txt` — 2 hits — AP-140
- `A04_compound_base\turn_4.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_4.txt` — 2 hits — AP-140
- `A08_sky_savings_rate\turn_4.txt` — 2 hits — AP-140
- `B03_bull_eth_strategy\turn_4.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_5.txt` — 2 hits — AP-140
- `D02_aave_supply_withdraw_all\turn_1.txt` — 2 hits — AP-140
- `D03_compound_claim_then_withdraw\turn_4.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_1.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_2.txt` — 2 hits — AP-140
- `D08_aave_borrow_repay\turn_3.txt` — 2 hits — AP-140
- `E04_eth_to_opt_aave_usdt\turn_4.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_1.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_3.txt` — 2 hits — AP-140
- `E05_arb_to_base_compound\turn_4.txt` — 2 hits — AP-140
- `E09_eth_to_arb_morpho\turn_3.txt` — 2 hits — AP-140

## Sample evidence (top-5 patterns)

### AP-140 [P1] — 40-hex address (verify if backed by card or freeform)

- `A01_aave_base_usdc\turn_5.txt`: `0x0b2c639c533813f4aa9d7837caf62653d097ff85`
- `A03_low_risk_only\turn_4.txt`: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- `A04_compound_base\turn_4.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A07_spark_dai\turn_3.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`
- `A07_spark_dai\turn_4.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`

### AP-130 [P0] — Empty final content with empty card_ids (G03 T4, I03 T3, I05)

- `C05_velodrome_cl\turn_4.txt`: `"content":"","card_ids":[]`
- `F07_token_2022_hook\turn_3.txt`: `"content":"","card_ids":[]`
- `H14_S14_v2_to_v3_migrate\turn_3.txt`: `"content":"","card_ids":[]`
