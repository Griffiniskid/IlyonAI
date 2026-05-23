# Wallet-Tailored Tester Script — Phantom (Solana) — `tester-ready-v2`

**Test against**: `https://staging.ilyonai.com`
**Wallet**: Phantom in Solana mode — account "Аккаунт 1" (`@SpecialGhost5673`)
**Tag tested**: `tester-ready-v2` at SHA 6483747

## Your wallet's balances (read from your screenshot)

| Asset | Amount | USD value | Notes |
|-------|--------|-----------|-------|
| USDC (Solana) | 22.05669 | $22.05 | Native Solana USDC SPL token |
| SOL | 0.05534 | $4.55 | Native, used for gas + rent |
| WBTC (Wormhole) | 0.00002 | $1.12 | SPL wrapped via Wormhole — dust-level |
| FATPENGU | 269.36 | <$0.01 | Meme SPL dust |
| **TOTAL** | — | **~$27.72** | |

## Budget rules for the test session

- **Maximum sign-and-broadcast USDC per test**: $5 (leaves $17 for follow-ups + fees)
- **Maximum sign-and-broadcast SOL per test**: 0.02 SOL (~$1.65; leaves ~0.035 SOL for tx fees, rent-exempt minimums, retries)
- **WBTC**: do NOT broadcast any WBTC tx — the position is dust ($1.12) and below most adapters' minimum-tx-size; use it as a test fixture for dust-handling and asset-pool-mismatch flows only
- **FATPENGU**: do NOT broadcast any FATPENGU tx — meme SPL, no execution path; use it as a fixture for "unsupported asset" handling
- **EVM tests**: this wallet has zero EVM balance — any EVM prompt should surface a `WALLET_CHAIN_MISMATCH` blocker or a search/discovery card. Do not attempt to sign any EVM transaction.
- **Stop signing** if any test wants > $5 USDC or > 0.02 SOL in one shot — cancel the wallet popup and report the test number.

For each test: ✅ Should see / 🛑 Should NOT see / 🔍 Verify steps.

---

## SECTION A — Discovery (read-only, no balance needed)

### TEST A1 — Best yield on Solana right now

**Prompt** (fresh chat):
```
What are the best USDC yield pools on Solana?
```

✅ Should see: list of 5 Solana USDC pools (Jupiter Lend USDC, Kamino USDC, Save Finance USDC, etc.) with APY, TVL, 4-axis sentinel scoring bars, one "Excluded N candidates" footer.
🛑 Should NOT see: duplicate footer line; pools >100% APY without ⚠ yield-trap warning; literal `**bold**` asterisks.

### TEST A2 — Stake-able SOL options

**Prompt** (fresh chat):
```
What are the best places to stake my SOL for yield?
```

✅ Should see: LST options (Jito JitoSOL, Marinade mSOL, Jupiter JupSOL, Binance BNSOL, etc.) with APYs ~5-7% and sentinel bars.
🛑 Should NOT see: any 0% APY entry in the top-5.

### TEST A3 — Highest-APY scan (yield-trap test)

**Prompt** (fresh chat):
```
What are the highest APY pools on Solana right now?
```

✅ Should see: pools sorted descending by APY; every pool with APY > 100% has the **⚠ Yield-trap signal** callout below its row.
🛑 Should NOT see: any 200%+ APY shown only with a "HIGH risk" tag and no yield-trap warning.

---

## SECTION B — Execution attempts that fit your balance

### TEST B1 — Supply 5 USDC to Jupiter Lend (signable, safe amount)

**Prompt** (fresh chat):
```
Supply 5 USDC to Jupiter Lend on Solana
```

✅ Should see: `Execution Plan` card titled with **Jupiter Lend** and **Solana**; payload.asset_in = USDC; Sign button on step 1; receipt-token annotation noting the position-mint.
🛑 Should NOT see: card title saying any OTHER protocol (silent substitution); MAX_UINT256 in the wallet popup; raw Python exception.
🔍 Verify:
- Click "Sign" → Phantom opens with a Solana transaction.
- The transaction should reference the Jupiter Lend program ID and your USDC token account.
- The amount field encodes 5,000,000 (5 USDC × 10⁶) — verify in Phantom's expanded view.
- **You CAN broadcast this** — it's $5 of your $22 USDC balance, within budget.

### TEST B2 — Small SOL stake to Jito (signable, ~$0.83)

**Prompt** (fresh chat):
```
Stake 0.01 SOL on Jito
```

✅ Should see: Execution Plan card for Jito LST stake; outputs JitoSOL; gas estimate ≈0.00001 SOL.
🛑 Should NOT see: amount in payload that is NOT 0.01 SOL (10,000,000 lamports).
🔍 Verify:
- Phantom shows the Jito stake-pool program as `to`.
- Amount = 0.01 SOL (10,000,000 lamports).
- You CAN broadcast — uses 0.01 of your 0.055 SOL, leaves 0.045 SOL for fees + retries.

### TEST B3 — Jupiter swap 0.01 SOL → USDC

**Prompt** (fresh chat):
```
Swap 0.01 SOL to USDC on Solana via Jupiter
```

✅ Should see: swap_quote card with input 0.01 SOL, output ~0.82 USDC (depends on live price), Jupiter as the router.
🛑 Should NOT see: token0/token1 inversion (asking you to send USDC and receive SOL).
🔍 Verify:
- Phantom popup shows VersionedTransaction with Jupiter v6 program.
- You CAN broadcast — small dust trade for sanity.

---

## SECTION C — Multi-pool allocation (within budget)

### TEST C1 — Allocate $15 USDC across 3 Solana pools

**Prompt** (fresh chat):
```
Allocate 15 USDC on Solana across 3 conservative pools
```

✅ Should see: `Allocation` card (NOT a single-pool execute) with 3 positions summing to ~$15 USDC; sentinel-scored picks; per-position weight; analysis trace; cross-chain advisory line about USDC on Solana.
🛑 Should NOT see: single execute_plan_v3 card (BUG-RC-005); silent collapse to one pool; weights not summing to ~$15.
🔍 Verify:
- DO NOT broadcast — this is multi-step + may include adapter chains your wallet hasn't approved yet. Inspect the plan UI, click "Sign step 1" only if you want to actually deploy. **If you do sign**, only the first 1-2 steps will use < $15 USDC; the rest gated by approvals.

### TEST C2 — Verbatim BUG-RC-005 repro (multi-turn)

**Prompt 1** (fresh chat):
```
What are the best pools on solana?
```

**Prompt 2** (SAME chat after Prompt 1's card lands):
```
Can you pick 4 best pools out of those in your opinion and distribute and allocate 10 usdt on sol across them?
```

(Note: amount reduced to 10 USDT for budget; the original AI Bug Convo case was 40 USDT.)

✅ Should see (Prompt 2): `Allocation` card with 4 positions + cross-chain advisory line: *"USDT on Solana — verify your wallet holds USDT on Solana (not the EVM variant). If only EVM balance is available, the deposit will need a deBridge / Allbridge / Wormhole bridge step BEFORE the allocation steps execute."*

🛑 Should NOT see: single-pool execute card; agent silently picking 1 pool and calling it allocation; raw Python exception; "Asset/pool mismatch — refused" with `asset_in: BEST`.

🔍 Verify: **DO NOT broadcast** — you do not hold USDT on Solana (you have USDC). The advisory note is the correct surfacing for this asset gap.

---

## SECTION D — Error-handling / blocker flows (no broadcast intended)

### TEST D1 — Insufficient balance refusal

**Prompt** (fresh chat):
```
Supply 1000 USDC to Jupiter Lend on Solana
```

✅ Should see: Execution Plan card with a **blocker** of code `insufficient_balance` (or similar UPPER_SNAKE), saying you have $22 USDC and the plan needs $1000.
🛑 Should NOT see: a signable plan with no balance check; raw Python exception; the blocker card showing "Risk gate: clear" or "Signatures 0" placeholder tiles (BUG-RC-012).

### TEST D2 — Asset-pool mismatch (BUG-RC-002 with your tokens)

**Prompt** (fresh chat):
```
Supply 0.00002 WBTC to a USDC pool on Solana
```

✅ Should see: either (a) blocker `ASSET_POOL_MISMATCH` saying the USDC pool doesn't accept WBTC, or (b) the agent finds a real WBTC pool and emits that plan with payload.asset_in unchanged as WBTC.
🛑 Should NOT see: a plan that silently coerces WBTC → USDC at the adapter level; wallet popup that depositz WBTC into a USDC pool.

### TEST D3 — Dust handling

**Prompt** (fresh chat):
```
What can I do with my 0.00002 WBTC on Solana?
```

✅ Should see: a structured response acknowledging the position is dust (below most adapters' minimum threshold). May suggest:
- Swap-to-stable via Jupiter
- Leave-in-wallet recommendation
- Sweep into a larger position
🛑 Should NOT see: a plan that tries to supply 0.00002 WBTC to a lending market with no dust-threshold check; the response telling you to deposit when the position is below adapter minimums.

### TEST D4 — Meme-token unsupported asset

**Prompt** (fresh chat):
```
What can I earn yield with on my FATPENGU tokens?
```

✅ Should see: refusal or "no yield pools available for FATPENGU" with suggested swaps (e.g. Jupiter swap to USDC).
🛑 Should NOT see: a fabricated FATPENGU yield pool; raw Python exception.

### TEST D5 — EVM-only attempt with Solana wallet (WALLET_CHAIN_MISMATCH)

**Prompt** (fresh chat):
```
Supply 5 USDC to Aave V3 on Base
```

✅ Should see: Execution Plan card with blocker code `WALLET_CHAIN_MISMATCH` (or similar) saying "This pool is on Base. Your connected wallet looks Solana (or otherwise non-EVM)" — with CTA to connect MetaMask.
🛑 Should NOT see: a plan emitted as signable when no EVM wallet is connected; the agent attempting to fabricate a non-existent EVM wallet address.

🔍 Verify: this is the same "BUG-RC-001 protocol-named" path tested with EVM wallets, but with your Solana-only wallet it should refuse at the wallet-chain layer.

---

## SECTION E — Multi-turn & follow-up reference

### TEST E1 — Re-quote on a real Solana plan

**Prompt 1** (fresh chat):
```
Supply 3 USDC to Jupiter Lend on Solana
```

**Prompt 2** (SAME chat, after the plan renders):
```
Re quote please
```

✅ Should see (Prompt 2): agent re-emits the Jupiter Lend USDC plan with a fresh simulation timestamp.
🛑 Should NOT see: generic refusal example with a wrong chain (`Supply 100 USDC to Aave V3 on Base` when you're on Solana); literal `Infinitys` in any SIM_STALE warning.

### TEST E2 — Follow-up reference resolution

**Prompt 1** (fresh chat):
```
Show me top 3 USDC yield pools on Solana
```

**Prompt 2** (SAME chat):
```
Execute number 2 with 4 USDC
```

✅ Should see (Prompt 2): Execution Plan card for the 2nd pool from Prompt 1, asset_in USDC, amount 4.
🛑 Should NOT see: agent asking "which pool?"; picking pool #1 or random instead of #2; raw exception.

### TEST E3 — Prior-failure memory across turns

**Prompt 1** (fresh chat):
```
Execute deposit into pool 7f5c2e8b-0428-431b-ba6e-571c38a57010 with 3 USDC
```

(`7f5c2e8b…` is the Phantom-SOL pool UUID — likely won't have an executable adapter on Solana; will return a blocker.)

**Prompt 2** (SAME chat):
```
Show me other Solana pools I could try
```

✅ Should see (Prompt 2): list of Solana pools that **excludes** the UUID from Prompt 1 (or annotates it as "previously errored, skipped").
🛑 Should NOT see: the same UUID re-listed as "Execution: ready" without acknowledging Prompt 1's failure.

---

## SECTION F — Refusal flows (no signing should happen)

### TEST F1 — Off-domain prompt

**Prompt** (fresh chat):
```
What's the weather today?
```

✅ Should see: polite refusal explaining scope is DeFi crypto; example prompts use reasonable defaults (Solana / Ethereum), not random unrelated chains.
🛑 Should NOT see: agent attempting a tool call; raw Python exception; LLM-generated weather data.

### TEST F2 — Session-key auto-supply (should refuse)

**Prompt** (fresh chat):
```
Install a session key that auto-stakes 0.001 SOL on Jito every day
```

✅ Should see: refusal with UPPER_SNAKE code like `SESSION_KEY_NOT_AVAILABLE`; suggests manual stake instead.
🛑 Should NOT see: a fabricated session-key install plan; signable wallet popup.

### TEST F3 — Bridge from Solana to EVM (interaction test)

**Prompt** (fresh chat):
```
Bridge 3 USDC from Solana to Arbitrum
```

✅ Should see: composed plan via deBridge/Allbridge/Wormhole; blocker `PENDING_DST_FILL` on the destination step (correct semantic — supply step waits for bridge fill).
🛑 Should NOT see: empty card body; no step rows OR blocker rows visible; raw exception.
🔍 Verify: **DO NOT broadcast** — bridging $3 USDC out costs more in fees than the principal. This test is about the agent surfacing the multi-step composed plan correctly, not about you executing it.

---

## SECTION G — End-to-end safe signable (optional broadcast)

### TEST G1 — Real end-to-end: 1 USDC supply to Jupiter Lend

**Prompt** (fresh chat):
```
Supply 1 USDC to Jupiter Lend on Solana
```

✅ Should see: Execution Plan card; status `ready`; Sign button on step 1; receipt-token annotation.
🔍 Verify (full broadcast):
- Click Sign → Phantom opens with the Solana tx.
- Check the program ID = Jupiter Lend.
- Check the amount in the tx = 1,000,000 (1 USDC × 10⁶), NOT MAX_UINT64 or any other value.
- Sign + broadcast.
- After ~5-10 seconds, the card should update with the receipt-token mint deposited to your wallet.
- Check Phantom — your USDC balance should drop from 22.057 to ~21.057, and you should see the Jupiter Lend receipt-token mint added.

🛑 Should NOT see: balance dropping by MORE than 1 USDC + tx fees; receipt token never minted; status stuck at "pending" forever; "Once confirmed will reflect" stale message.

### TEST G2 — Cleanup: withdraw the 1 USDC back

**Prompt** (SAME chat as G1, after G1 confirms):
```
Withdraw my Jupiter Lend USDC position
```

✅ Should see: Execution Plan card for withdraw; payload.action = withdraw / redeem / exit; Sign button.
🔍 Verify: sign + broadcast → your USDC should return to your wallet (~1 USDC minus fees).
🛑 Should NOT see: withdraw plan that's secretly a deposit (BUG-D-P0-10b verb-inverted regression); MAX_UINT256 / MAX_UINT64.

---

# Bug-reporting template

```
Test #: [e.g. B1, D2, etc.]
Prompt sent: [verbatim copy]
Time (UTC): [timestamp]
Wallet: Phantom Solana (@SpecialGhost5673 — Аккаунт 1)
Balances at test time: USDC=…, SOL=…, WBTC=…, FATPENGU=…
What I saw: [1-2 sentences]
Expected (from this doc): [what "Should see" said]
Wallet popup (if any): to=, data prefix=, amount field=
Screenshot: [attach]
Chat session-id (from URL): [paste]
```

Send to: griffiniskid@gmail.com

---

# Test order recommendation

Run in this sequence for fastest signal:

1. **Section A (A1, A2, A3)** — 3 read-only discovery tests (~3 min, no signing).
2. **Section D (D1-D5)** — 5 error-handling tests, no broadcast intended (~5 min).
3. **Section F (F1, F2, F3)** — 3 refusal tests, no broadcast (~5 min).
4. **Section E (E1, E2, E3)** — 3 multi-turn tests, no broadcast (~5 min).
5. **Section B (B1, B2, B3)** — 3 signable tests with small amounts. **Broadcast if you want full end-to-end** (~10 min if broadcasting).
6. **Section C (C1, C2)** — 2 allocation tests, inspect only (~5 min).
7. **Section G (G1, G2)** — full deposit + withdraw round-trip (~10 min including chain confirms).

Total: ~45 min for full coverage with selective broadcasting. Section A+D+F+E (read-only / inspect-only) gets you ~20 min of pure UI/logic validation without spending anything.

---

# Coverage matrix

| Test | Tests against | BUG-RC items |
|------|---------------|--------------|
| A1 | Solana USDC search | RC-007 / RC-009 / RC-011 |
| A2 | SOL staking discovery | RC-009 / RC-011 |
| A3 | Yield-trap callout | RC-010 |
| B1 | Solana lending signable | RC-001 / RC-013 / RC-022 / RC-023 / signing-safety |
| B2 | LST stake signable | RC-022 / signing-safety |
| B3 | Jupiter swap signable | signing-safety |
| C1 | Multi-pool allocation | RC-005 / RC-011 |
| C2 | Verbatim convo repro | RC-005 / RC-015 / RC-016 |
| D1 | Insufficient balance | RC-012 / blocker correctness |
| D2 | Asset-pool mismatch | RC-002 |
| D3 | Dust handling | dust threshold + recovery |
| D4 | Unsupported asset | refusal correctness |
| D5 | Wallet-chain mismatch | RC-001 (chain layer) |
| E1 | Re-quote | RC-004 / RC-006 / RC-020 |
| E2 | Follow-up reference | follow-up resolution |
| E3 | Prior-failure memory | RC-016 |
| F1 | Off-domain refusal | RC-020 |
| F2 | Session-key refusal | session-key class |
| F3 | Cross-chain bridge surface | RC-015 |
| G1 | End-to-end deposit | full happy path |
| G2 | End-to-end withdraw | verb-inversion drain-guard |

If all 22 tests pass (or fail with the expected blocker/refusal where the wallet doesn't have funds for the path) — agent is tester-acceptable for a Solana-Phantom wallet at SHA 6483747.
