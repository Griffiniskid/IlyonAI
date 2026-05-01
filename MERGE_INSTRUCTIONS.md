# CRITICAL: Merge These Changes Before Combining Systems

## Context
You are working on combining the IlyonAI Sentinel and Assistant systems. **The code has been significantly updated since your last session.** The current `main` branch contains critical bug fixes and features that MUST be preserved during your merge. Do NOT overwrite these files with older versions.

## Files That Changed (DO NOT LOSE THESE CHANGES)

### 1. `server/app/agents/crypto_agent.py` — 7 critical changes

#### A. Tolerant JSON Parser (`_parse_tool_json`) — Lines ~100-130
**Added**: New helper function that parses LLM tool input JSON while tolerating:
- Markdown code fences (```json ... ```)
- Trailing LLM commentary after JSON (e.g. "(Note: I converted...)")
- Extra prose appended after valid JSON

**Why**: The LLM frequently appends explanatory text after JSON tool arguments, causing `json.loads()` to fail with "Extra data" error. This broke all compound actions like "swap X then bridge it".

**Usage**: Replaces `json.loads(raw)` in all tool entry points:
- `_build_swap_tx`
- `_build_transfer_transaction`  
- `_build_stake_tx`
- `_build_deposit_lp_tx`
- `_build_bridge_tx`
- `build_solana_swap`
- `find_liquidity_pool`

#### B. Solana Added to `_CHAIN_META` — Line ~86
**Added**: `101: {"name": "Solana", "native": "SOL", "native_name": "SOL"}`

**Why**: Without this, the system prompt said "Active network: Chain 101" instead of "Solana", causing the LLM to think Solana was unsupported and refusing Phantom wallet operations.

#### C. Solana SPL Tokens Added — Lines ~233-260
**Added**: `_TOKENS_SOLANA` registry with 13 common SPL tokens:
- SOL, USDC, USDT, BONK, JUP, RAY, ORCA, mSOL, JitoSOL, WBTC, WETH, PYTH
**Added**: `101: _TOKENS_SOLANA` to `TOKENS_BY_CHAIN`

**Why**: Token resolution for Solana was falling through to EVM registries, returning wrong addresses and decimals (e.g., USDT resolved to 18 decimals instead of 6, causing Jupiter amount overflow errors).

#### D. System Prompt Updates — Lines ~2081-2095
**Changed**: Compound action instructions now tell LLM to:
1. Call `get_wallet_balance` FIRST when source chain is ambiguous
2. Discover which chain holds the token
3. Use that discovered chain for swap/bridge

**Changed**: `get_wallet_balance` tool description now allows balance checks for compound/multi-step actions (previously said "NEVER call this before a swap").

**Why**: Without this, the AI assumed the active session chain_id for swaps, even when user's tokens were on a different chain (e.g., bridging from Ethereum when USDT was on Solana).

### 2. `server/app/api/endpoints.py` — Major additions (~290 lines)

#### A. `_is_swap_bridge_compound()` — Line ~390
Detects queries like "swap X to Y and bridge to Z" or "swap X then bridge Y".

#### B. `_try_direct_compound_swap_bridge()` — Lines ~400-640
**Deterministic handler for compound swap+bridge queries.** This is the most important new feature.

**What it does**:
1. Parses swap intent (amount, token_in, token_out) and bridge destination
2. **Checks wallet balances** via `_get_balance_via_portfolio()` to discover source chain
3. Falls back to known token registries (`TOKENS_BY_CHAIN`) if balances unavailable
4. Builds swap tx on discovered source chain:
   - Solana → uses `build_solana_swap()` (Jupiter)
   - EVM → uses `_build_swap_tx()` (Enso)
5. Builds bridge tx from source to destination via `_build_bridge_tx()` (deBridge)
6. Returns combined plain-text response with both transactions

**Critical implementation details**:
- Passes **human-readable amounts** to `build_solana_swap()` (it handles decimal conversion internally)
- Uses Jupiter's `out_amount` directly for bridge (already in raw units, do NOT convert again)
- Handles "all" / "max" amounts by querying wallet balance
- Maps chain IDs to friendly names ("Solana", "BNB Smart Chain", etc.)

**Integration point**: Added to main flow BEFORE direct swap/bridge handlers (line ~1128), so compound actions bypass the LLM entirely.

#### C. `_try_direct_bridge()` — Lines ~290-330
**Modified**: Now converts human-readable amounts to raw units before calling `_build_bridge_tx()`:
```python
amount = str(int(Decimal(amount) * (Decimal(10) ** int(src_decimals or 18))))
```

**Why**: Previously passed "5" as raw units → became 0.000005 USDT (5 wei instead of 5,000,000).

#### D. `_try_direct_stake()` — Modified
Same decimal conversion fix for EVM staking amounts.

### 3. `server/tests/test_staking_and_bridge_routing.py` — 50+ new tests

**Added test classes**:
- `TolerantToolJsonParserTests` (8 tests) — validates `_parse_tool_json()` handles fences, trailing commentary, empty input
- `BridgeToolToleratesLlmCommentaryTests` — end-to-end test with exact production failure payload
- `ChainMetaTests` (2 tests) — validates Solana in `_CHAIN_META`
- `SystemPromptTests` (2 tests) — validates prompt mentions balance discovery
- `DirectBridgeRoutingTests` — bridge amount conversion tests
- `DirectStakingRoutingTests` — staking amount conversion tests

**Total**: 50 tests (was 17, now 50), all passing.

## What NOT to Change

1. **Do NOT modify `_parse_tool_json()` logic** — it's carefully designed to handle LLM output quirks
2. **Do NOT remove Solana from `_CHAIN_META` or `TOKENS_BY_CHAIN`** — critical for Phantom wallet support
3. **Do NOT revert system prompt compound action instructions** — required for correct multi-step behavior
4. **Do NOT remove `_try_direct_compound_swap_bridge()`** — this is the primary handler for swap+bridge flows
5. **Do NOT change amount handling in `build_solana_swap()`** — it expects human-readable strings and converts internally

## Merge Strategy

When combining systems:
1. **Start from current `main`** (commit `fa87cbe` or later)
2. Apply your changes on top, resolving conflicts in favor of the current code for the files listed above
3. Run `pytest` to verify all 50 tests pass
4. Test compound queries on production after deployment

## Production Verification Commands

After deployment, validate with:
```bash
# Health check
curl https://ilyonai.com/api/v1/agent-health

# Compound swap+bridge (Phantom wallet)
curl -X POST https://ilyonai.com/api/v1/agent \
  -H "Content-Type: application/json" \
  -d '{"query":"swap 10 usdt to usdc and bridge it to bnb chain",...}'

# Simple bridge
curl -X POST https://ilyonai.com/api/v1/agent \
  -H "Content-Type: application/json" \
  -d '{"query":"bridge 5 usdt from solana chain to bnb chain",...}'
```

## Git History

Current HEAD: `fa87cbe fix(compound): show human-readable amounts and chain names in response`

Recent commits (most recent first):
- `fa87cbe` — Human-readable amounts in compound response
- `13386f9` — Pass human-readable amounts to build_solana_swap
- `a41d9aa` — Don't double-convert Jupiter out_amount for bridge
- `b3d7a4e` — Add Solana SPL tokens to TOKENS_BY_CHAIN
- `f082a49` — Deterministic compound swap+bridge handler
- `c360eaf` — Add Solana to chain meta + balance discovery instructions
- `4fbef49` — Tolerate LLM trailing commentary in tool JSON inputs
- `74100c9` — Convert human-readable amounts to raw units before bridging

## Contact

If any merge conflicts arise with the files above, preserve the current `main` version and apply your changes around it. These fixes resolve critical production bugs and must not be lost.