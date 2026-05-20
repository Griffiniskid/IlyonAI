# Closed-bug regression sweep — passA-wave10

**4 closed bugs reappeared.** Details below.

## Reappearing patterns

| Probe ID | Bug ref | Files affected | Sample file:pattern |
|----------|---------|----------------|---------------------|
| D05-balancer-exit-drain | D-P0-10b | 2 | `D05_balancer_exit_pool\turn_2.txt`: `0xb95cac28` |
| C14-raydium-clmm-fake-address | P0-C-02 MUTATED | 2 | `C14_meteora_dlmm\turn_2.txt`: `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM` |
| E02-slippage-band-fabrication | BUG-E-004 wave-6 | 1 | `E01_eth_to_base_aave\turn_3.txt`: `slippage band` |
| E10-bridge-supply-submitted | BUG-E-013 | 1 | `enso-07\turn_3.txt`: `Once confirmed` |

## Per-probe inventory

### D05-balancer-exit-drain — D-P0-10b
Prompt: `Exit Balancer wsteth-weth with 0.5 BPT`
Hits: 4 across 2 files
- `D05_balancer_exit_pool\turn_2.txt` → `0xb95cac28`
- `D05_balancer_exit_pool\turn_2.txt` → `Single-asset join`
- `D05_balancer_exit_pool\turn_4.txt` → `0xb95cac28`
- `D05_balancer_exit_pool\turn_4.txt` → `Single-asset join`

### C14-raydium-clmm-fake-address — P0-C-02 MUTATED
Prompt: `Add 1 SOL + 100 USDC to Raydium CLMM SOL-USDC`
Hits: 2 across 2 files
- `C14_meteora_dlmm\turn_2.txt` → `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`
- `C14_meteora_dlmm\turn_4.txt` → `9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM`

### E02-slippage-band-fabrication — BUG-E-004 wave-6
Prompt: `Bridge 200 USDC from Ethereum to Arbitrum via deBridge then Compound V3 supply`
Hits: 1 across 1 files
- `E01_eth_to_base_aave\turn_3.txt` → `slippage band`

### E10-bridge-supply-submitted — BUG-E-013
Prompt: `Bridge 100 USDC from Ethereum to Base then supply to Aave V3`
Hits: 1 across 1 files
- `enso-07\turn_3.txt` → `Once confirmed`
