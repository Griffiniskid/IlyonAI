# Platform Enhancement: API Key Reduction & Feature Improvement

**Date:** 2026-04-12
**Status:** Approved

## Goal
Make every feature fully functional with only the 5 API keys already configured (OpenRouter, Gemini, Grok, Helius, Jupiter). Eliminate dependency on 7 Etherscan-family keys and optional Moralis/GoPlus keys. Improve all features except the scoring system.

## Sections

### 1. Shield - RPC Event Log Scanning
**Problem:** Shield requires 7 Etherscan-family API keys (none configured). 100% non-functional.
**Solution:** Replace Etherscan API calls with `eth_getLogs` RPC queries using existing public RPC endpoints.
- ERC-20 Approval event topic: `0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925`
- Filter by owner address in topic[1], extract spender from topic[2], amount from data
- Fetch token metadata (name, symbol, decimals) via `eth_call`
- Keep existing risk scoring and revoke TX builder
- Add approval age tracking
- Files: `src/shield/approval_scanner.py`, `src/api/routes/shield.py`

### 2. Entity Analysis - Smart Linking
**Problem:** Bare-bones in-memory graph with no automated linking.
**Solution:** Add linking heuristics and enrichment.
- Cross-chain same-address linking
- Funding source analysis
- New endpoint: `POST /api/v1/entities/resolve`
- Entity profile aggregation across linked wallets
- Files: `src/smart_money/graph_store.py`, `src/api/routes/entity.py`

### 3. Contract Scanning - Free GoPlus Integration
**Problem:** Contract scanning relies solely on AI auditor (needs OpenRouter).
**Solution:** Add GoPlus free public API as supplementary data source.
- Endpoint: `https://api.gopluslabs.io/api/v1/token_security/{chain_id}`
- No API key needed for basic tier
- Merge with existing AI auditor output
- Files: `src/data/goplus.py` (new), `src/contracts/`

### 4. Wallet Intelligence - On-Chain Enrichment
**Problem:** Wallet profiles lack on-chain data.
**Solution:** Use existing RPCs for transaction history, balances, activity timestamps.
- Files: `src/analytics/`, `src/api/routes/wallet_intel.py`

### 5. Portfolio - Free API Migration
**Problem:** EVM portfolio depends on optional Moralis key.
**Solution:** Use RPC `eth_call` for ERC-20 balances, DexScreener for prices.
- Files: `src/portfolio/`

### 6. Graceful Degradation
**Problem:** Missing keys cause silent failures.
**Solution:** Every endpoint returns useful data with clear status on what's available.
- Service health aggregation
- Partial result responses with degradation info

## Constraints
- DO NOT modify scoring system (token or DeFi)
- Keep all existing API contracts (additive changes only)
- All changes must pass existing test suite
