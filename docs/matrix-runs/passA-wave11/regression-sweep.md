# Closed-bug regression sweep — passA-wave11

**1 closed bugs reappeared.** Details below.

## Reappearing patterns

| Probe ID | Bug ref | Files affected | Sample file:pattern |
|----------|---------|----------------|---------------------|
| D05-balancer-exit-drain | D-P0-10b | 2 | `D05_balancer_exit_pool\turn_2.txt`: `0xb95cac28` |

## Per-probe inventory

### D05-balancer-exit-drain — D-P0-10b
Prompt: `Exit Balancer wsteth-weth with 0.5 BPT`
Hits: 4 across 2 files
- `D05_balancer_exit_pool\turn_2.txt` → `0xb95cac28`
- `D05_balancer_exit_pool\turn_2.txt` → `Single-asset join`
- `D05_balancer_exit_pool\turn_4.txt` → `0xb95cac28`
- `D05_balancer_exit_pool\turn_4.txt` → `Single-asset join`
