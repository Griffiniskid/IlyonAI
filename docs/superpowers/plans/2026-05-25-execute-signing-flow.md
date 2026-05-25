# Make Executable Pools Actually Sign-able — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:executing-plans or subagent-driven-development.

**Goal:** When a pool is shown executable, the user can complete the deposit end-to-end — connect the right wallet, clear real blockers, sign, broadcast, and the funds land in the correct pool.

**Architecture:** Three real defects sit between "plan built" and "user signs": (1) the Sign button ignores plan-level blockers, (2) the build runs balance/gas preflight against whatever wallet is connected even if it's the wrong chain (Phantom/Solana for a BSC pool → false 0-balance), (3) the simulation goes stale (>30s) with no auto re-quote. Fix all three, then verify the signed tx broadcasts and deposits to the correct pool.

---

## Root cause (diagnosed from the screenshots + code)

The PancakeSwap BUSD plan **built correctly** — step status `ready`, real `approve→swap→deposit` calldata via Enso. It can't be signed because:

1. **Sign button not gated on blockers (UI bug).** `ExecutionPlanV3Card.tsx:57` — `canSign = isFirstReady && step.status === "ready"`. It does NOT check `payload.status === "blocked"` or `payload.blockers`. So the yellow "Sign step 1" button shows even while the card says *"No signing button is shown until every blocker is resolved."* Contradiction.
2. **Wrong-wallet / no-funds (real, expected).** The connected wallet is **Phantom (Solana)**; the pool is **BSC**. The balance/gas preflight scans that wallet → 0 BUSD, 0 BNB → real `INSUFFICIENT_BALANCE` + gas blockers. A BSC deposit needs a funded **EVM (MetaMask)** wallet. This is correct gating, but the UX should say "connect/fund an EVM wallet," not silently show 0.
3. **`SIM_STALE`** — the simulation is >30s old; the card warns "re-quote before signing" but there's no auto re-quote, so even a funded user hits a stale-sim gate.

**Net:** the build works; the signing path is blocked by a UI bug + wallet/chain context + stale sim. None require new protocol integrations.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `web/components/agent/cards/ExecutionPlanV3Card.tsx` | Gate Sign button on plan-level blockers; show a "connect the right wallet" CTA on wallet-chain mismatch | Modify |
| `web/components/agent-app/MainApp.tsx` | Pass the connected wallet's chain context; on chain mismatch prompt connect/switch before signing | Modify |
| `src/agent/tools/build_yield_execution_plan.py` | Run balance/gas preflight against the wallet that matches the pool's CHAIN; emit a `WALLET_NOT_CONNECTED`/`WALLET_CHAIN_MISMATCH` blocker (not a false 0-balance) when the matching wallet is absent | Modify |
| `src/agent/tools/build_yield_execution_plan.py` (re-quote) | When `simulated_at` is older than the freshness window, rebuild+re-simulate the step before returning `ready` | Modify |
| `web/hooks/useWalletSigning.ts` | Confirm EVM send + chain-switch (wallet_switchEthereumChain) to the pool's chain before signing | Verify/Modify |
| `web/tests/e2e/execution-plan-signing.test.tsx` | Sign button hidden when blockers present; shown only when blockers cleared | Create |
| `scripts/validation/signing_flow_check.py` | Assert ready plans carry signable calldata + fresh sim + correct chain id; report per chain | Create |

---

## Tasks

### Task 1: Gate the Sign button on plan-level blockers (the UI contradiction)
- [ ] **Test (vitest):** render an ExecutionPlanV3 payload with `status:"blocked"` + an `INSUFFICIENT_BALANCE` blocker AND a `ready` step → assert NO `sign-step-*` button. Then with `status:"ready"` + no blockers → assert the button IS present.
- [ ] **Run → fail.**
- [ ] **Implement:** in `ExecutionPlanV3Card.tsx`, compute `planBlocked = payload.status === "blocked" || (payload.blockers||[]).some(b => HARD_OR_FUNDING_CODES.has(b.code))`. Change the render guard at line 170 and `canSign` (line 57) to also require `!planBlocked`. Keep the existing blocker list rendering.
- [ ] **Run → pass. Commit.**

### Task 2: Wallet-chain-aware preflight + CTA
- [ ] **Test:** `build_yield_execution_plan` for a BSC pool with only a Solana wallet present → emits a `WALLET_NOT_CONNECTED` (EVM) blocker, NOT a 0-balance `INSUFFICIENT_BALANCE`.
- [ ] **Run → fail.**
- [ ] **Implement (backend):** pick the preflight wallet by the pool's chain kind — EVM pool → `evm_wallet`; Solana pool → `solana_wallet`. If the matching wallet is missing, emit `WALLET_NOT_CONNECTED` with CTA "Connect a MetaMask/Phantom wallet on {chain}" instead of scanning the wrong wallet (which yields a misleading 0-balance). Only run the balance/gas scan when the right wallet is present.
- [ ] **Implement (frontend):** on Sign, if the plan's chain ≠ the connected wallet's active chain, prompt connect/switch (MetaMask `wallet_switchEthereumChain`; for Solana require Phantom) before opening the signer.
- [ ] **Run → pass. Commit.**

### Task 3: Auto re-quote on stale simulation
- [ ] **Test:** a step whose `simulated_at` is older than the freshness window is rebuilt/re-simulated (fresh `simulated_at`, fresh `simulated_calldata_hash`) before the plan returns `ready`.
- [ ] **Run → fail.**
- [ ] **Implement:** in `build_yield_execution_plan`, before emitting `ready`, if `now - simulated_at > FRESHNESS_S`, re-run the adapter build + simulate so the returned tx is fresh. Frontend: if the user clicks Sign with a stale sim, trigger a re-quote (re-issue the execute) instead of failing.
- [ ] **Run → pass. Commit.**

### Task 4: End-to-end signing verification
- [ ] **Implement** `scripts/validation/signing_flow_check.py`: for a sample of executable pools per chain, assert the `ready` step has (a) non-null calldata (EVM `to`+`data` / Solana `serialized`), (b) a `simulated_at` within the freshness window, (c) `chain_kind`/chain id matching the pool. Report per chain; exit non-zero on any gap.
- [ ] **Run it → 0 gaps.**
- [ ] **Manual (user, real funds):** connect a funded MetaMask on BSC (BNB for gas + BUSD) → EXECUTE the PancakeSwap pool → blockers clear → Sign → broadcast → confirm the position token lands in the wallet (Enso receipt `0x58F8…`). Same for a Solana pool with funded Phantom (Marinade/Jito). **Do not claim done until a real deposit confirms on-chain.**

---

## How to TEST execution right now (before the fixes)

The build already works; you just need the matching funded wallet:
- **Solana** (your Phantom): "liquid staking on solana" → EXECUTE **Marinade** or **Jito** → sign with funded Phantom (needs SOL). Same wallet you already have.
- **BSC/EVM**: connect a **MetaMask** wallet funded with **BNB (gas) + the pool token** → EXECUTE an Aave/PancakeSwap pool. With Phantom (Solana) you'll always see the BUSD/BNB blockers because that wallet holds no BSC funds.

---

## Out of scope
- The ~5% curve per-pool Enso route gaps (separate, deep-link fallback).
- Solana AMM zap + CLMM range-UI (separate features).
