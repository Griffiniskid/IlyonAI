# Closed-bug regression sweep — passA-waveD1

**2 closed bugs reappeared.** Details below.

## Reappearing patterns

| Probe ID | Bug ref | Files affected | Sample file:pattern |
|----------|---------|----------------|---------------------|
| E02-slippage-band-fabrication | BUG-E-004 wave-6 | 1 | `E01_eth_to_base_aave\turn_3.txt`: `slippage band` |
| E10-bridge-supply-submitted | BUG-E-013 | 1 | `H05_S5_xchain_diff_token\turn_4.txt`: `Once confirmed` |

## Per-probe inventory

### E02-slippage-band-fabrication — BUG-E-004 wave-6
Prompt: `Bridge 200 USDC from Ethereum to Arbitrum via deBridge then Compound V3 supply`
Hits: 1 across 1 files
- `E01_eth_to_base_aave\turn_3.txt` → `slippage band`

### E10-bridge-supply-submitted — BUG-E-013
Prompt: `Bridge 100 USDC from Ethereum to Base then supply to Aave V3`
Hits: 1 across 1 files
- `H05_S5_xchain_diff_token\turn_4.txt` → `Once confirmed`
