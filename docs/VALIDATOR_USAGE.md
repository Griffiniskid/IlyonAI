# Validator Index — Canonical Locations for All Agents

Every agent and human dev working on this repo should run these BEFORE
claiming any pool / swap / stake / LP feature works on staging or prod.

## Files

| Path | What it catches |
|---|---|
| `tests/validators/strict_validator_v2.py` | **Primary**. 30+ assertion classes: card composition, calldata sanity, redirect-phrase detection, URL liveness, float-drift, dev-string leaks, zap completeness, post-sign-fire safety, range block payload, wallet/chain match, deadline freshness, zero-addresses, chain_id presence, Solana tx size, amount consistency, protocol-text match. |
| `scripts/strict_pool_validator.py` | v1 — 121 scenarios. Legacy. v2 replaces it. |
| `scripts/anvil_fork_sim.py` | L3 funded fork. Spawns anvil, sets balance/storage, broadcasts plan, captures receipts + event logs. Catches calldata that's structurally valid but reverts on real state. |
| `scripts/playwright_browser_smoke.py` | L4 browser smoke. Headless Chromium, mocks Phantom+MetaMask EIP-1193, navigates chat, asserts DOM hydrates + wallet detection. |
| `tests/calldata_decoder.py` | EVM selector decoder + sanity asserts (mint amount > 0 in-range, deadline future, approve amount > 0, recipient == user). |

## Run order

```bash
# L2 strict API validation (~22 min, 30+ scenarios)
ILYON_BASE=https://staging.ilyonai.com python3 -B tests/validators/strict_validator_v2.py

# L3 Anvil funded fork sim (broadcasts a real V3 mint plan)
python3 -B scripts/anvil_fork_sim.py

# L4 Playwright headless smoke (~30s)
python3 -B scripts/playwright_browser_smoke.py
```

## Bug classes the validator now catches

1. Card composition (required + forbidden card_types per scenario)
2. Calldata semantic sanity (mint, approve, curve add_liquidity, Aave supply)
3. Range card payload invariants (current_price, fee_tier, cdf_30d, presets)
4. **Redirect-phrase detection** ("finalise the LP add inside ...", "currently unavailable")
5. **URL liveness** (HEAD with redirect follow; must not land on /swap when expecting /liquidity)
6. **Float-drift** (`0.111111`, `0.099999`, `0.000000123`, scientific notation, 15+ digit raw atomic units)
7. **Dev-string leaks** (`undefined`, `[object Object]`, `NaN`, `TODO`, `FIXME`)
8. **Amount consistency** (summary text amount must match scenario's expected_amount within 1%)
9. **Protocol text match** (card title/description must mention expected protocol)
10. **Signable card has real tx** (execution_plan_v3 ready status implies every ready step has `tx.data` or `tx.serialized`)
11. **Zap completeness** (Raydium AMM must have ≥3 steps swap+swap+deposit, not 1 prep-swap)
12. **Wallet/chain mismatch blocker** (Solana request on EVM wallet emits wallet_chain_mismatch)
13. **Mint deadline freshness** (deadline > now AND < now + 24h)
14. **No zero-address tx.to**
15. **EVM tx has chain_id**
16. **Solana tx serialized size < 1232 bytes** (or has ALT hint)
17. **Post-sign no search-trigger fire** (runtime must not inject `confirm the receipt` user message)
18. **Float-precision regression** (per-token forbid_text)
19. **Pool URL not DefiLlama fallback** (pool_link card must have protocol-native URL)
20. **PancakeSwap V3 URL ≠ Uniswap branch**
21. **Curve slug map ≠ wrong pool**
22. **Yearn vault address fallback when symbol-only**
23. **Aave reserve fallback per chain**
24. **Receipt-token strip** (sDAI/yvUSDC/aUSDC → underlying)
25. **Stale extra.pool_address override** (parser pair wins over meta.symbol)
26. **Chain inference** (parser chain wins over meta.chain)
27. **Protocol inference** (parser proto wins over meta.project)
28. **Velodrome-V3 hallucination → V2_AMM** (explicit registry trust over substring scan)
29. **Sanctum INF / Frax / Beefy / Ichi / Steer slug coverage**
30. **Range refinement chain depth** (5+ delta turns)

## CI / CD wiring (recommended)

Add to `.github/workflows/validate.yml`:

```yaml
- name: Strict validator v2
  run: |
    ILYON_BASE=https://staging.ilyonai.com python3 tests/validators/strict_validator_v2.py
- name: Anvil fork sim
  run: |
    curl -L https://foundry.paradigm.xyz | bash
    ~/.foundry/bin/foundryup
    python3 scripts/anvil_fork_sim.py
- name: Playwright smoke
  run: |
    pip install playwright && playwright install chromium
    python3 scripts/playwright_browser_smoke.py
```

## Adding new assertions

When a browser bug surfaces that the validator missed:

1. Add a new `check_*` function at the top of `tests/validators/strict_validator_v2.py`.
2. Wire it into `run_scenario` per-card or per-text loop.
3. Add a new `Scenario` that intentionally triggers the bug pattern.
4. Run validator → must FAIL on the new scenario before you ship the fix.
5. Fix the bug → re-run → must PASS.
6. Commit both the scenario and the fix in the same PR.

This is the "tester reality bridge" (L5) — every browser-found bug
becomes a permanent harness assertion.
