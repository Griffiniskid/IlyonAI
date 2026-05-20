# Static sweep — passA-wave10

Scanned: 532 turn files
Files with ≥1 hit: 97
Total pattern hits: 200

## Top patterns (by file count)

| ID | Sev | Files | Hits | Description |
|----|-----|-------|------|-------------|
| AP-140 | P1 | 92 | 192 | 40-hex address (verify if backed by card or freeform) |
| AP-050 | P0 | 5 | 5 | 'slippage band 0.5%' / 'protocol fee ~0.10%' fabrication (E02, E05) |
| AP-130 | P0 | 2 | 2 | Empty final content with empty card_ids (G03 T4, I03 T3, I05) |
| AP-190 | P0 | 1 | 1 | Backticked Solidity call signatures (H14 t3/t4) |

## Per-category breakdown

| Cat | Total files w/ hits | Top pattern (files) |
|-----|---------------------|---------------------|
| A | 13 | AP-140 (13 files) |
| B | 6 | AP-050 (5 files) |
| C | 11 | AP-140 (11 files) |
| D | 15 | AP-140 (14 files) |
| E | 16 | AP-140 (16 files) |
| F | 5 | AP-140 (5 files) |
| G | 16 | AP-140 (16 files) |
| H | 10 | AP-140 (10 files) |
| I | 2 | AP-140 (1 files) |
| e | 3 | AP-140 (2 files) |

## Top-30 most-affected files

- `B01_stable_strategy\turn_1.txt` — 4 hits — AP-050, AP-140
- `A11_aave_opt_weth\turn_2.txt` — 3 hits — AP-140
- `B06_eth_solana_split\turn_1.txt` — 3 hits — AP-050, AP-140
- `B15_pendle_yt_speculate\turn_1.txt` — 3 hits — AP-050, AP-140
- `C03_uniswap_v3_native\turn_4.txt` — 3 hits — AP-140
- `C04_slipstream_base\turn_4.txt` — 3 hits — AP-140
- `C07_balancer_wsteth_weth\turn_2.txt` — 3 hits — AP-140
- `C12_pancake_v3\turn_4.txt` — 3 hits — AP-140
- `C14_meteora_dlmm\turn_3.txt` — 3 hits — AP-140
- `D09_aave_native_full_cycle\turn_3.txt` — 3 hits — AP-140
- `D09_aave_native_full_cycle\turn_4.txt` — 3 hits — AP-140
- `F02_wallet_chain_mismatch\turn_3.txt` — 3 hits — AP-140
- `H01_S1_same_chain_dual\turn_4.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_3.txt` — 3 hits — AP-140
- `H03_S3_native_eth_V3\turn_4.txt` — 3 hits — AP-140
- `H15_S15_wrong_wallet\turn_2.txt` — 3 hits — AP-140
- `I02_session_key_compound\turn_2.txt` — 3 hits — AP-140
- `A01_aave_base_usdc\turn_5.txt` — 2 hits — AP-140
- `A04_compound_base\turn_2.txt` — 2 hits — AP-140
- `A04_compound_base\turn_4.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_3.txt` — 2 hits — AP-140
- `A07_spark_dai\turn_4.txt` — 2 hits — AP-140
- `A09_aave_arb_usdt\turn_4.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_3.txt` — 2 hits — AP-140
- `A10_aave_polygon_dai\turn_4.txt` — 2 hits — AP-140
- `B09_morpho_blueprint\turn_4.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_2.txt` — 2 hits — AP-140
- `C01_aave_base_refine_chain\turn_5.txt` — 2 hits — AP-140
- `C08_morpho_blue_market\turn_2.txt` — 2 hits — AP-140
- `D02_aave_supply_withdraw_all\turn_1.txt` — 2 hits — AP-140

## Sample evidence (top-5 patterns)

### AP-140 [P1] — 40-hex address (verify if backed by card or freeform)

- `A01_aave_base_usdc\turn_5.txt`: `0x0b2c639c533813f4aa9d7837caf62653d097ff85`
- `A03_low_risk_only\turn_4.txt`: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- `A04_compound_base\turn_2.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A04_compound_base\turn_4.txt`: `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`
- `A07_spark_dai\turn_3.txt`: `0x6b175474e89094c44da98b954eedeac495271d0f`

### AP-050 [P0] — 'slippage band 0.5%' / 'protocol fee ~0.10%' fabrication (E02, E05)

- `B01_stable_strategy\turn_1.txt`: `gas estimates, and 0.5%`
- `B02_bear_strategy\turn_1.txt`: `gas estimates, and 0.5%`
- `B06_eth_solana_split\turn_1.txt`: `gas estimates, and 0.5%`
- `B10_pendle_pt\turn_1.txt`: `gas estimates, and 0.5%`
- `B15_pendle_yt_speculate\turn_1.txt`: `gas estimates, and 0.5%`

### AP-130 [P0] — Empty final content with empty card_ids (G03 T4, I03 T3, I05)

- `D13_raydium_clmm_close\turn_4.txt`: `"content":"","card_ids":[]`
- `I05_session_key_kernel\turn_3.txt`: `"content":"","card_ids":[]`

### AP-190 [P0] — Backticked Solidity call signatures (H14 t3/t4)

- `enso-05\turn_3.txt`: ``deposit(uint256 amount)``
