# Closed-bug regression sweep — passA-wave8

**5 closed bugs reappeared.** Details below.

## Reappearing patterns

| Probe ID | Bug ref | Files affected | Sample file:pattern |
|----------|---------|----------------|---------------------|
| D05-balancer-exit-drain | D-P0-10b | 1 | `D05_balancer_exit_pool\turn_1.txt`: `Balancer V3 Deposit LP` |
| C14-raydium-clmm-fake-address | P0-C-02 MUTATED | 2 | `C14_meteora_dlmm\turn_2.txt`: `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM` |
| E02-slippage-band-fabrication | BUG-E-004 wave-6 | 2 | `E07_eth_to_base_curve\turn_4.txt`: `slippage band` |
| E10-bridge-supply-submitted | BUG-E-013 | 2 | `enso-02\turn_2.txt`: `Once confirmed` |
| H14-backticked-solidity | P0-H-03 | 1 | `enso-07\turn_3.txt`: ``mint`` |

## Per-probe inventory

### D05-balancer-exit-drain — D-P0-10b
Prompt: `Exit Balancer wsteth-weth with 0.5 BPT`
Hits: 3 across 1 files
- `D05_balancer_exit_pool\turn_1.txt` → `Balancer V3 Deposit LP`
- `D05_balancer_exit_pool\turn_1.txt` → `0xb95cac28`
- `D05_balancer_exit_pool\turn_1.txt` → `Single-asset join`

### C14-raydium-clmm-fake-address — P0-C-02 MUTATED
Prompt: `Add 1 SOL + 100 USDC to Raydium CLMM SOL-USDC`
Hits: 2 across 2 files
- `C14_meteora_dlmm\turn_2.txt` → `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`
- `C14_meteora_dlmm\turn_4.txt` → `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`

### E02-slippage-band-fabrication — BUG-E-004 wave-6
Prompt: `Bridge 200 USDC from Ethereum to Arbitrum via deBridge then Compound V3 supply`
Hits: 2 across 2 files
- `E07_eth_to_base_curve\turn_4.txt` → `slippage band`
- `H06_S6_xchain_native\turn_3.txt` → `slippage band`

### E10-bridge-supply-submitted — BUG-E-013
Prompt: `Bridge 100 USDC from Ethereum to Base then supply to Aave V3`
Hits: 2 across 2 files
- `enso-02\turn_2.txt` → `Once confirmed`
- `enso-02\turn_4.txt` → `Once confirmed`

### H14-backticked-solidity — P0-H-03
Prompt: `Migrate my Uniswap V2 LP to V3`
Hits: 1 across 1 files
- `enso-07\turn_3.txt` → ``mint``
