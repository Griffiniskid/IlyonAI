# IlyonAi Tester Walkthrough — `tester-ready-v2` (SHA 6483747)

**Test against**: `https://staging.ilyonai.com`
**Wallet**: connect MetaMask AND Phantom (some tests need EVM, some need Solana)
**How to use this doc**: copy each `Prompt` line verbatim into the chat input. Each test stands alone — open a fresh chat (top-right "+ New chat") between tests so prior context doesn't bleed in. The few multi-turn tests are labelled explicitly.

For every test, three boxes:
- **✅ Should see** — the agent's correct behavior
- **🛑 Should NOT see** — bug signatures that mean a regression (file a ticket if any of these appear)
- **🔍 What to click / verify** — explicit verification steps

The expected results are tied to the 23 BUG-RC items from `AI Bug Convo.md` that were closed in Wave RC-α/β/γ. If any "Should NOT see" item appears, copy the chat transcript + screenshot and report.

---

## TEST 1 — Best pools on Solana (search discovery)

**Prompt**:
```
What are the best pools on solana?
```

**✅ Should see**:
- A `Constraint-Matched DeFi Opportunities` chat bubble with 5 numbered items (top-5 of N available).
- Each item has: protocol name, asset/pair, chain badge, risk tier, APY %, TVL $, DefiLlama links.
- A `Constraint-matched DeFi` card below the chat bubble with the same 5 items rendered as a card list.
- **Each card item shows a 4-axis sentinel scoring bar**: Safety / Durability / Exit / Confidence with numeric scores 0-100.
- An "Excluded N candidates that violated the requested risk, APY, chain, or TVL constraints." line — appearing **exactly ONCE** (not twice).
- An "Execute" button (rocket icon) on each card with an `via <adapter>` label.

**🛑 Should NOT see**:
- The "Excluded N candidates" line appearing twice with different wording ("violated requested" vs "violated the requested").
- Sentinel scoring bar missing or showing "Sentinel scoring unavailable".
- Any pool with APY = 0.0% in the top-5 ranked list.
- Any pool with APY > 100% without a yellow `⚠ Yield-trap signal` callout underneath its row.
- Raw text like `**Constraint-Matched DeFi Opportunities**` (literal asterisks) — should render as bold.

**🔍 What to click / verify**:
- Hover the sentinel scoring bar — colors should be red (low) / amber (mid) / emerald (high).
- Click a DefiLlama pool link — should open in new tab.

---

## TEST 2 — Multi-pool allocation (verbatim BUG-RC-005 repro)

**Prompt** (run Test 1 first to seed the prior pool list, then in the SAME chat):
```
Can you pick 4 best pools out of those in your opinion and distribute and allocate 40 usdt on sol across them?
```

**✅ Should see**:
- An `Allocation` card emitted (NOT a single-pool execute_plan_v3 card).
- The allocation shows 4 positions, each with a USD weight summing to $40.
- An "Analysis trace" or "Market brief" section explaining the picks.
- A **"Cross-chain advisory"** line that says something like: *"USDT on Solana — verify your wallet holds USDT on Solana (not the EVM variant). If only EVM balance is available, the deposit will need a deBridge / Allbridge / Wormhole bridge step BEFORE the allocation steps execute."*

**🛑 Should NOT see**:
- A single-pool `execution_plan_v3` card (would mean BUG-RC-005 regression: agent collapsed multi-pool intent to single execute).
- The chat saying "Asset/pool mismatch — refused" with `BEST` as the asset name (means dispatcher mis-parsed "4 best" as asset=BEST).
- Empty content / blank chat bubble.
- Any pool re-listed from Test 1 that previously errored (prior-failure memory).

**🔍 What to click / verify**:
- The 4 allocations should be diverse (different protocols / chains) — not all Gmtrade or all same protocol.
- The weights should sum to ≈$40 (small rounding OK).

---

## TEST 3 — Aave V3 supply on Base (verbatim BUG-RC-001 repro)

**Prompt** (fresh chat):
```
Supply 100 USDC to Aave V3 on Base
```

**✅ Should see**:
- An `Execution Plan` card titled with **Aave V3** and **Base** explicitly in the title.
- `payload.protocol` (inspect via browser devtools Network → /api/v1/agent SSE) must be `aave-v3`.
- A single Sign button at step 1 (approve or supply).
- Status: `ready` · 1 signature(s) required.
- Receipt-token line including a contract address with explanatory note: *"Receipt token: 0x… — open this address on the chain's explorer and verify the contract name reads 'aave-v3' or its canonical position-token symbol."*

**🛑 Should NOT see**:
- The card title mentioning **Fluid Lending** or any non-Aave protocol (= BUG-RC-001 silent substitution regression).
- A blocker `INTENT_MISMATCH: protocol substitution refused: aave → fluid` (means user-intent matched but routing failed differently).
- `**Aave V3 Supply** — Supply 100.0 USDC...` printed THREE times in the chat bubble (duplicate-title regression).
- Generic Enso boilerplate `Enso shortcuts bundle approvals + swaps; review the destination contract before signing.` — should be pool-specific instead.

**🔍 What to click / verify**:
- Click "Sign" — wallet popup should open with payload `to` matching the Aave V3 Pool on Base (`0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`).
- Cancel the wallet popup — composer should re-enable within seconds.

---

## TEST 4 — Re-quote / refresh sim (BUG-RC-004)

**Prompt** (in the SAME chat as Test 3, after the plan is shown):
```
Re quote please
```

**✅ Should see**:
- Agent re-emits the same Aave V3 Supply plan with a fresh simulation timestamp.
- The card shows status `ready` again.
- Optionally a short note like "Refreshing simulation..." in the chat.

**🛑 Should NOT see**:
- A generic refusal text like *"I couldn't complete that request. Try: `Supply 100 USDC to Aave V3 on Base`"* — i.e. example with a chain DIFFERENT from your prior plan (= BUG-RC-020 cascade).
- A literal `SIM_STALE: Simulation is Infinitys old (>30s).` (= BUG-RC-006 regression). If a SIM_STALE warning appears at all, the time must be a finite number like `30s` or `1m 12s` or `stale`.

---

## TEST 5 — Suspiciously-high APY warning (BUG-RC-010)

**Prompt** (fresh chat):
```
What are the highest APY pools right now?
```

**✅ Should see**:
- A list of pools sorted by APY descending.
- **Every pool with APY > 100% has a yellow `⚠ Yield-trap signal` callout** under its row: *"X% APY is well above sustainable. Most pools quoting >100% are thin-liquidity short-term emissions; the realised 30d APY is often a fraction of this. Verify the historical APY chart before sizing."*

**🛑 Should NOT see**:
- A pool with 200%+ APY shown only with a "HIGH risk" tag, no yield-trap callout.
- 0% APY pools listed in the top-5 (= BUG-RC-009 regression).

---

## TEST 6 — Asset-pool mismatch refusal (BUG-RC-002)

**Prompt** (fresh chat):
```
Supply 100 USDC to fluid-lending WSTETH on Ethereum
```

**✅ Should see** (one of these two outcomes):
- Either: A blocker card with `ASSET_POOL_MISMATCH` code, saying USDC is not accepted by the WSTETH pool. Recovery CTA suggests re-issuing.
- Or: Agent finds a USDC variant of Fluid Lending (e.g. fluid-lending USDC market) and emits that plan instead — but `payload.asset_in` MUST still be `USDC` (no silent coercion to WSTETH).

**🛑 Should NOT see**:
- A plan whose title says "Fluid Lending **WSTETH**" with `payload.asset_in: "USDC"` (silent coercion = BUG-RC-002 regression).
- The agent emitting a wallet popup that actually deposits USDC into a WSTETH pool.

---

## TEST 7 — Execute by pool UUID (BUG-RC-003 verbatim repro)

**Prompt** (run Test 1 first to get pool UUIDs visible, then SAME chat):
```
Execute deposit into pool 9e709e57-84eb-496b-82ce-2e8f6a17db1b with $100
```

(That UUID is BNSOL — Binance Staked SOL, a real DefiLlama pool. If you ran Test 1 and got different UUIDs, substitute the first one from your list.)

**✅ Should see**:
- Either: A signable execution_plan_v3 card for the BNSOL deposit (or whatever pool matches the UUID).
- Or: A structured blocker card with code like `WALLET_CHAIN_MISMATCH` / `pool_not_found` / `ASSET_POOL_MISMATCH` — typed UPPER_SNAKE code with a clear CTA.

**🛑 Should NOT see**:
- Raw text like *"I wasn't able to fetch that data right now. cannot access local variable 'ExecutionBlocker' where it is not associated with a value"* (= BUG-RC-003 regression — raw Python exception leak).
- Any `Traceback`, `UnboundLocalError`, `AttributeError: 'NoneType'` in the chat.
- Empty chat bubble with no card.

---

## TEST 8 — Prior-failure memory across turns (BUG-RC-016)

**Prompt 1** (fresh chat):
```
Execute deposit into pool 7f5c2e8b-0428-431b-ba6e-571c38a57010 with $100
```

(May succeed or fail depending on adapter coverage — either way, run Prompt 2.)

**Prompt 2** (SAME chat):
```
Execute deposit into pool 7083d6a5-e3cb-4eeb-8204-f1b735e4ecbb with $100
```

**Prompt 3** (SAME chat):
```
Is there a pool that you can execute right now?
```

**✅ Should see** (Prompt 3):
- A list of execution-ready pools.
- **The two pool UUIDs from Prompt 1 + Prompt 2 are NOT in the new list** OR are clearly annotated as "previously errored, skipped".

**🛑 Should NOT see**:
- The SAME pool UUID from Prompts 1/2 re-listed as "Execution: ready" without acknowledging the prior failure (= BUG-RC-016 regression — the "ready" label is lying).

---

## TEST 9 — Blocker card placeholder fields (BUG-RC-012)

**Prompt** (fresh chat):
```
Execute deposit into pool gmtrade XAU-USDC with 100 USDT
```

(Gmtrade is a Solana protocol with no one-click execution path; this should produce a blocked plan.)

**✅ Should see**:
- A blocker card with status `blocked`, code something like `pool_kind_unsupported` or `UNSUPPORTED_ADAPTER`.
- Status tile showing "blocked" — and **NO** other placeholder tiles (no "Risk gate: clear", no "Total Gas: -", no "Chains: -", no "0s ETA").
- A clear blocker title + detail + a recovery CTA (e.g. "Open Gmtrade to deposit there: …").
- If the blocker text promises "alternatives" — at least one alternative card must follow. If no alternatives are available, the blocker says "no equivalent alternatives in registry" + suggests fresh search (NOT a hollow "alternatives surfacing" promise = BUG-RC-019).

**🛑 Should NOT see**:
- "Signatures 0" chip on a blocked card (= BUG-RC-012).
- "Risk gate: clear" tile on a blocked card.
- The pool symbol "Gmtrade XAU-USDC" printed THREE times in the chat bubble.

---

## TEST 10 — Markdown rendering in chat (BUG-RC-014)

**Prompt** (fresh chat):
```
Best low-risk USDC pools on Ethereum
```

**✅ Should see**:
- Headings like "Constraint-Matched DeFi Opportunities" rendered as **bold** (HTML `<strong>`).
- Protocol names like "Sky Lending" or "Aave V3" rendered as bold inline in the numbered list.

**🛑 Should NOT see**:
- Literal asterisks like `**Sky Lending**` or `**Steps**` or `**Blockers**` in the chat (means markdown didn't render = BUG-RC-014).

---

## TEST 11 — Reasoning trace collapsed by default (BUG-RC-018)

**Prompt** (fresh chat):
```
What's the best way to earn yield on 1 ETH?
```

**✅ Should see**:
- A collapsible "Reasoning · N steps" header at the top of the assistant response.
- The reasoning steps (🧠 Parsed direct yield execution, ⚙️ Called build_yield_execution_plan, etc.) are **collapsed by default** — you must click to expand.

**🛑 Should NOT see**:
- The reasoning steps fully expanded in chat, flooding the response with internal step narration.

---

## TEST 12 — Refusal of off-domain prompts (sanity check)

**Prompt** (fresh chat):
```
What is the meaning of life?
```

**✅ Should see**:
- A polite refusal explaining the agent is scoped to DeFi crypto operations.
- Suggested example prompts (search, allocate, supply, etc.) — they should reference reasonable defaults like Ethereum or Base, not random unrelated chains.

**🛑 Should NOT see**:
- The agent attempting to call any DeFi tool.
- Raw Python exception text.

---

## TEST 13 — Cross-chain bridge surface (BUG-RC-015)

**Prompt** (fresh chat):
```
Bridge 250 USDC from Ethereum to Arbitrum then supply to Morpho Blue
```

**✅ Should see**:
- An `Execution Plan` card with a multi-step composed plan: bridge step + Morpho Blue supply step.
- Bridge step shows the deBridge / Allbridge / LiFi route selected.
- One of the steps will be `blocked` with code `PENDING_DST_FILL` — that's correct (the supply step waits for the bridge to fill).
- Per-step status icons + ETA.
- A blocker row visible on the card (NOT a missing card).

**🛑 Should NOT see**:
- The agent collapsing this to a single-chain plan (just Aave Arbitrum without the bridge).
- The execution_plan_v3 card emitted but no step rows / blocker rows visible in the DOM.

---

## TEST 14 — V3 LP mint with range preset

**Prompt** (fresh chat):
```
Add liquidity to Uniswap V3 ETH-USDC on Ethereum, balanced range, $500
```

**✅ Should see**:
- An execution_plan_v3 card for V3 NFT mint (Uniswap V3).
- Steps include: approve token0 + approve token1 + mint NFT position.
- Range bounds shown (balanced = ±10% per spec §3.3).
- The plan uses Uniswap V3 (NOT silently substituted to Aerodrome / Pancake / etc.).

**🛑 Should NOT see**:
- Token0/token1 inverted in the wallet popup payload.
- The range showing literal `Infinitys` or `NaN`.
- A wallet popup with `amount: 2^256-1` (MAX_UINT256 drain).

**🔍 What to click / verify**:
- Click step 1 "Sign" — wallet popup should request approval for ONLY the specified amount, NOT MAX_UINT256.
- The pair direction (token0 = WETH, token1 = USDC on Uniswap V3) should match the wallet popup payload.

---

## TEST 15 — Session-key / AA-policy refusal (sanity)

**Prompt** (fresh chat):
```
Install a session key that auto-supplies 100 USDC to Aave V3 every week
```

**✅ Should see**:
- A refusal text like "Session-key flows are not available on this build" or similar.
- Suggested alternatives (manual deposits, etc.).
- A typed blocker code (UPPER_SNAKE) — likely `SESSION_KEY_NOT_AVAILABLE`.

**🛑 Should NOT see**:
- The agent attempting to fabricate a `setPolicy(...)` Kernel v3 entrypoint call.
- A wallet popup with anything signable.

---

## TEST 16 — Multi-turn follow-up reference

**Prompt 1** (fresh chat):
```
Show me top 3 USDC supply pools on Base
```

**Prompt 2** (SAME chat, after the 3 pools render):
```
Execute number 2
```

**✅ Should see** (Prompt 2):
- Agent recognises "number 2" as the second pool from Prompt 1.
- An execution_plan_v3 card for that specific pool.

**🛑 Should NOT see**:
- Agent asking "which pool?" (it should resolve via prior-card context).
- Agent picking a different pool (e.g. number 1 or random).
- Raw Python exception.

---

## TEST 17 — Sentinel scoring presence on every opportunity card (BUG-RC-011)

**Prompt** (fresh chat):
```
Show me 5 yield opportunities on multiple chains
```

**✅ Should see**:
- 5 opportunity cards.
- **Every** card has the 4-axis sentinel scoring bar visible (Safety / Durability / Exit / Confidence) with numeric scores.

**🛑 Should NOT see**:
- Any card with sentinel bar missing.
- Any card showing "Sentinel scoring unavailable" badge unless the backend genuinely couldn't score it.

---

## TEST 18 — End-to-end signable Aave V3 USDC supply (the happy path)

**Prompt** (fresh chat):
```
Supply 5 USDC to Aave V3 on Base
```

**✅ Should see**:
- Execution Plan card for Aave V3 Base USDC supply.
- One signable step (or two — approve + supply, depending on existing allowance).
- Status `ready`, 1-2 signatures.
- Sign button visible on step 1.

**🔍 What to click / verify**:
- Click "Sign" on step 1.
- MetaMask opens with a `supply` (or `approve` first) transaction.
- Verify in MetaMask: `to` = Aave V3 Pool on Base (`0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`), data starts with `0x617ba037` (Aave V3 `supply` selector) or `0x095ea7b3` (ERC20 approve).
- The amount in the data field should encode 5,000,000 (5 USDC, 6 decimals) — NOT 2^256-1.
- Cancel the popup — composer re-enables.
- If you actually have USDC on Base in this wallet, you can sign + broadcast for the full end-to-end check.

**🛑 Should NOT see**:
- Wallet popup with MAX_UINT256 amount.
- Wallet popup `to` address that's NOT the Aave V3 Pool.
- Card emitted but no Sign button visible.

---

# Bug-reporting template

If any "Should NOT see" item fires, please report with:

```
Test #: [number]
Prompt sent: [verbatim copy]
Time of test (UTC): [timestamp]
What I saw: [1-2 sentences]
Expected: [from "Should see" above]
Screenshot: [attach]
Chat link / session-id (if visible in URL): [paste]
```

Send to: griffiniskid@gmail.com (CC the team channel).

---

# Coverage matrix

| Test # | BUG-RC items verified |
|--------|----------------------|
| 1 | RC-007 (duplicate footer), RC-009 (0% APY filter), RC-011 (sentinel scoring) |
| 2 | RC-005 (allocation intent), RC-015 (cross-chain advisory), RC-016 (prior-failure) |
| 3 | RC-001 (protocol substitution), RC-013 (duplicate title), RC-022 (receipt-token), RC-023 (Enso warnings) |
| 4 | RC-004 (re-quote), RC-006 (Infinitys), RC-020 (refusal chain context cascade) |
| 5 | RC-010 (yield-trap), RC-009 (0% APY) |
| 6 | RC-002 (ASSET_POOL_MISMATCH) |
| 7 | RC-003 (exception leak) |
| 8 | RC-016 (prior-failure memory) |
| 9 | RC-012 (blocked-state placeholder fields), RC-019 (alternatives promise) |
| 10 | RC-014 (markdown render) |
| 11 | RC-018 (reasoning collapse) |
| 12 | RC-020 (refusal example chain context) |
| 13 | RC-015 (cross-chain bridge surface) |
| 14 | Token-pair / range / drain-guard (general safety) |
| 15 | Session-key refusal (RC2 from prior bug class) |
| 16 | Follow-up reference resolution |
| 17 | RC-011 (sentinel scoring on every card) |
| 18 | End-to-end happy path + signing safety |

If all 18 tests pass — every "Should see" matches and zero "Should NOT see" fires — **the agent is tester-acceptable at staging SHA 6483747**.
