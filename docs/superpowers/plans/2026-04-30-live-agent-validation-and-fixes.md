# Live Agent Validation And Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the `prod-agent-fixes` worktree to the VPS and prove the live `ilyonai.com` AI agent works across swaps, balances, staking, bridges, yield search, prices, and error handling with 50+ targeted production API requests.

**Architecture:** Use the local `.worktrees/prod-agent-fixes` branch as the only source of truth for fixes. Deploy to the VPS `~/ai-sentinel` copy by copying validated files and rebuilding impacted Docker services, then test the public domain through the Next.js proxy and assistant API. Every confirmed bug gets a failing regression test before production code changes.

**Tech Stack:** FastAPI assistant service, Next.js proxy/web service, Docker Compose on VPS, Enso EVM swap API, Jupiter Solana swap API, Python `unittest`/`pytest`, GitNexus for impact/change analysis.

---

## Working Rules

- Work only in `/home/griffiniskid/Documents/ai-sentinel/.worktrees/prod-agent-fixes` locally.
- Do not edit `/home/griffiniskid/Documents/ai-sentinel` local main workspace.
- Do not edit `IlyonAi-Wallet-assistant-sourcecode(DO NOT CHANGE)/`.
- Deploy to the VPS path `/home/aisentinel/ai-sentinel` from the `prod-agent-fixes` worktree files, not by relying on local main.
- Test public live behavior through `https://ilyonai.com/api/v1/agent` with a browser-like `User-Agent` because Cloudflare blocks Python default clients.
- Do not claim a feature works unless a fresh live request or local test proves it.

## Files

- Modify: `IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py` for confirmed swap/bridge/staking/yield root-cause fixes.
- Modify: `IlyonAi-Wallet-assistant-main/server/app/api/endpoints.py` for confirmed direct route parser/proxy root-cause fixes.
- Modify: `IlyonAi-Wallet-assistant-main/server/tests/test_staking_and_bridge_routing.py` for regression tests covering direct swap, all-token swap, and Solana routing bugs.
- Create: `scripts/live_agent_validation.py` to run the 60 live requests and classify responses.
- Create: `docs/ops/live-agent-validation-results.md` to record live run results, failures, fixes, and residual external limitations.

## Phase 1: Deploy Baseline

- [ ] Run `git status --short` in `.worktrees/prod-agent-fixes` and confirm the worktree contains only intended changes.
- [ ] Copy current `prod-agent-fixes` files to VPS `~/ai-sentinel`.
- [ ] Run `docker compose up -d --build --force-recreate assistant-api web` on the VPS.
- [ ] Confirm `docker compose ps` shows `assistant-api` and `web` healthy.
- [ ] Confirm `GET https://ilyonai.com/api/v1/agent-health` returns `{"status":"ok"}`.

## Phase 2: Reproduce Reported Bugs

- [ ] Send `swap all wbtc from my wallet to sol` with a Solana wallet and capture HTTP status, body, and assistant logs.
- [ ] Send `swap all sbtc from my wallet to sol` with a Solana wallet and capture HTTP status, body, and assistant logs.
- [ ] Send `swap 1 ray to usdc` with a Solana wallet and inspect returned sell amount, buy amount, decimals, and transaction payload.
- [ ] Send `swap 1 usdc to sol` with a Solana wallet to preserve the known working path.
- [ ] If a request fails, trace the exact failing function with GitNexus before editing code.

## Phase 3: TDD Fix Loop

- [ ] For each confirmed root cause, write a minimal failing regression test first.
- [ ] Run the targeted test and verify it fails for the expected reason.
- [ ] Run GitNexus impact analysis before modifying any function/class/method.
- [ ] Implement the smallest production change that makes the test pass.
- [ ] Run the targeted test and then the full assistant test suite.
- [ ] Deploy the fixed files to the VPS and rebuild only impacted services.
- [ ] Re-run the exact production request that failed and verify live behavior.

## Phase 4: 60-Request Live Validation Catalog

Use stable session IDs prefixed `live-validation-20260430-`. Expected result for every request: HTTP 200, JSON response envelope, no HTML error page, no proxy 500, no stack trace. Feature-specific invariants are listed next to each request.

### Health And General Chat

1. `Hello` on chain 56: conversational response.
2. `What can you do?` on chain 56: capabilities response.
3. `Explain my connected wallet` on chain 56: no transaction proposal.
4. `Show my balance` with EVM wallet only: balance report or clear provider/config error.
5. `Show my Solana balance` with Solana wallet: Solana balance report.
6. `What is the SOL price?`: price response, no transaction proposal.
7. `What is the BNB price?`: price response, no transaction proposal.
8. `What is the ETH price?`: price response, no transaction proposal.

### Solana Swaps

9. `swap 1 usdc to sol`: Solana action proposal, sell token USDC, buy token SOL, sell amount approximately 1 USDC.
10. `swap 0.2 sol to usdc`: Solana action proposal, sell token SOL, buy token USDC, sell amount approximately 0.2 SOL.
11. `swap 1 ray to usdc`: Solana action proposal or insufficient-balance message; never a 700+ USDC quote for 1 RAY.
12. `swap 0.000001 ray to usdc`: insufficient-balance or tiny quote; never oversized output.
13. `swap all ray to usdc`: all-token path uses actual RAY balance or clear zero-balance message.
14. `swap all wbtc from my wallet to sol`: all-token path returns JSON or clear unsupported/insufficient-balance message, never proxy 500.
15. `swap all sbtc from my wallet to sol`: unsupported token or balance message, never proxy 500.
16. `swap all usdc to sol`: all-token path uses actual USDC balance or clear zero-balance message.
17. `swap 0.01 bonk to sol`: token resolution is Solana, not EVM.
18. `swap 1 jup to usdc`: token resolution is Solana, not EVM.
19. `swap 0.1 sol for ray`: token resolution is Solana and output token RAY.
20. `swap sol to usdc`: asks for amount or defaults safely; no malformed transaction.

### EVM Swaps On BSC

21. `swap 0.003 bnb for eth`: EVM action proposal, chain 56, BNB input, Binance-Peg ETH output.
22. `swap 0.003 eth for bnb`: EVM action proposal or insufficient balance, chain 56, Binance-Peg ETH input, BNB output.
23. `swap all eth for bnb`: BSC balance check, chain 56, no Ethereum misroute.
24. `swap all bnb for eth`: BSC all-token path, chain 56.
25. `swap 1 usdt for bnb`: BSC token resolution, chain 56.
26. `swap 1 usdc for bnb`: BSC token resolution, chain 56.
27. `swap 0.01 cake for bnb`: BSC token resolution or clear unsupported token message.
28. `swap 0.001 btc for bnb`: no native BTC-on-Ethereum confusion; clear unsupported or pegged token behavior.
29. `swap 1 bnb for usdc on bsc`: explicit chain alias honored.
30. `swap 1 eth for usdc on bsc`: explicit chain alias honored, chain 56.

### EVM Swaps On Other Chains

31. `swap 0.001 eth for usdc on ethereum`: chain 1, native ETH input.
32. `swap 1 usdc for eth on ethereum`: chain 1.
33. `swap 1 matic for usdc on polygon`: chain 137.
34. `swap 1 usdc for matic on polygon`: chain 137.
35. `swap 0.01 avax for usdc on avalanche`: chain 43114.
36. `swap 1 usdc for avax on avalanche`: chain 43114.
37. `swap 0.001 eth for usdc on arbitrum`: chain 42161.
38. `swap 1 usdc for eth on arbitrum`: chain 42161.

### Staking And Yield

39. `stake bnb`: BSC staking proposal or staking options, chain 56.
40. `stake 0.01 bnb`: BSC staking proposal, chain 56.
41. `stake sol`: Solana staking route, not EVM.
42. `stake 0.1 sol`: Solana staking route, not EVM.
43. `best sol staking pool`: staking/yield info with links, no transaction proposal unless requested.
44. `best bnb staking pool`: staking/yield info with BSC protocols.
45. `best eth yield`: yield info, no swap transaction.
46. `best usdc pool on solana`: Solana pool/yield response.
47. `best usdc pool on bsc`: BSC pool/yield response.
48. `what is the APY for SOL pools`: APY response, no unsupported APR hallucination.

### Bridges

49. `bridge 0.1 sol to ethereum`: Solana bridge route or clear provider limitation.
50. `bridge all sol to ethereum`: all-token Solana bridge route or balance limitation.
51. `bridge 0.01 eth to solana`: EVM-to-Solana bridge route or clear provider limitation.
52. `bridge 1 usdc from solana to ethereum`: Solana source bridge route.
53. `bridge 1 usdc from bsc to solana`: BSC source bridge route or clear provider limitation.
54. `bridge all usdc from solana to bsc`: all-token bridge path uses actual Solana balance or clear limitation.

### Error Handling And Safety

55. `swap 999999999 ray to usdc`: insufficient balance or quote failure, no oversized phantom transaction.
56. `swap -1 sol to usdc`: validation error, no transaction.
57. `swap 0 sol to usdc`: validation error, no transaction.
58. `swap abc sol to usdc`: asks for valid amount, no 500.
59. `swap all unknowncoin to sol`: unsupported token or no-balance message, no 500.
60. `send all my tokens to this address`: refuses/clarifies, no transaction.

## Phase 5: Result Classification

- [ ] Record each request in `docs/ops/live-agent-validation-results.md` with status `PASS`, `FAIL-BUG`, `FAIL-EXTERNAL`, or `NEEDS-USER-WALLET`.
- [ ] `PASS` means live API returned the expected envelope and feature-specific invariant.
- [ ] `FAIL-BUG` means code routed incorrectly, produced unsafe transaction data, returned HTTP 500, returned HTML through JSON API, or produced obviously wrong amount/chain/token.
- [ ] `FAIL-EXTERNAL` means third-party provider rejected a valid quote or wallet provider blocked the generated URL, with evidence.
- [ ] `NEEDS-USER-WALLET` means the request depends on a real balance/private wallet state not available from the test wallet, but the API response is safe and JSON.

## Phase 6: Completion Criteria

- [ ] All local assistant tests pass.
- [ ] Docker Compose config validates locally.
- [ ] VPS services are healthy after rebuild.
- [ ] At least 50 live public-domain requests were executed.
- [ ] No live request returns proxy 500, HTML error, or malformed JSON.
- [ ] No live swap proposal has mismatched chain/token/amount units.
- [ ] GitNexus `detect_changes` reports expected changed symbols and low/understood risk.
- [ ] Final fixes are committed on local `prod-agent-fixes`.
