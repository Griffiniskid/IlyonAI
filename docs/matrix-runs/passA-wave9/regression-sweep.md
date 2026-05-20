# Closed-bug regression sweep — passA-wave9

**6 closed bugs reappeared.** Details below.

## Reappearing patterns

| Probe ID | Bug ref | Files affected | Sample file:pattern |
|----------|---------|----------------|---------------------|
| D05-balancer-exit-drain | D-P0-10b | 1 | `D05_balancer_exit_pool\turn_1.txt`: `Balancer V3 Deposit LP` |
| E02-slippage-band-fabrication | BUG-E-004 wave-6 | 3 | `E01_eth_to_base_aave\turn_3.txt`: `slippage band` |
| C14-raydium-clmm-fake-address | P0-C-02 MUTATED | 1 | `C14_meteora_dlmm\turn_4.txt`: `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM` |
| H14-backticked-solidity | P0-H-03 | 1 | `enso-07\turn_3.txt`: ``mint`` |
| E10-bridge-supply-submitted | BUG-E-013 | 1 | `H08_S8_partial_allowance\turn_2.txt`: `Once confirmed` |
| E08-ill-create-ready-to-sign-plan | BUG-E-004 E08 t3 | 1 | `I02_session_key_compound\turn_2.txt`: `I can generate a signable Execution Plan` |

## Per-probe inventory

### D05-balancer-exit-drain — D-P0-10b
Prompt: `Exit Balancer wsteth-weth with 0.5 BPT`
Hits: 3 across 1 files
- `D05_balancer_exit_pool\turn_1.txt` → `Balancer V3 Deposit LP`
- `D05_balancer_exit_pool\turn_1.txt` → `0xb95cac28`
- `D05_balancer_exit_pool\turn_1.txt` → `Single-asset join`

### E02-slippage-band-fabrication — BUG-E-004 wave-6
Prompt: `Bridge 200 USDC from Ethereum to Arbitrum via deBridge then Compound V3 supply`
Hits: 3 across 3 files
- `E01_eth_to_base_aave\turn_3.txt` → `slippage band`
- `E07_eth_to_base_curve\turn_4.txt` → `slippage band`
- `H06_S6_xchain_native\turn_3.txt` → `slippage band`

### C14-raydium-clmm-fake-address — P0-C-02 MUTATED
Prompt: `Add 1 SOL + 100 USDC to Raydium CLMM SOL-USDC`
Hits: 1 across 1 files
- `C14_meteora_dlmm\turn_4.txt` → `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`

### H14-backticked-solidity — P0-H-03
Prompt: `Migrate my Uniswap V2 LP to V3`
Hits: 1 across 1 files
- `enso-07\turn_3.txt` → ``mint``

### E10-bridge-supply-submitted — BUG-E-013
Prompt: `Bridge 100 USDC from Ethereum to Base then supply to Aave V3`
Hits: 1 across 1 files
- `H08_S8_partial_allowance\turn_2.txt` → `Once confirmed`

### E08-ill-create-ready-to-sign-plan — BUG-E-004 E08 t3
Prompt: `Bridge 0.05 WETH from Ethereum to Base then deposit to Balancer`
Hits: 1 across 1 files
- `I02_session_key_compound\turn_2.txt` → `I can generate a signable Execution Plan`
