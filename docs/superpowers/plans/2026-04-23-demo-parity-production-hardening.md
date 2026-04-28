# Demo-Parity & Production Hardening Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task has a validation gate that must pass via an actual HTTP request against a running dev server — not just passing tests.

**Goal:** Make the live, SSE-driven Agent Chat produce the exact visual and behavioral experience of the `allocate $10k` demo on `main` (web/app/agent/chat/page.tsx in `main`), with real data, on staging.

**Architecture:**
- Live stream `POST /api/v1/agent` emits SSE frames (thought / tool / card / final / done).
- Chat page on staging replaces its bland shell with a pixel-faithful re-render of the demo layout (preview banner, framed panel, quick chips, composer), but each element is backed by live data from the SSE stream.
- A new `allocate_plan` tool composes multi-tool data (DefiLlama pools + Sentinel scoring + Shield) into one allocation + sentinel_matrix + execution_plan card triplet — matching the demo.

**Tech Stack:** Next.js 14 + React + Tailwind, aiohttp + LangChain ReAct runtime, DefiLlama/CoinGecko/DexScreener data clients, Sentinel scorer, Shield verdict engine, PostgreSQL via SQLAlchemy async.

**Execution Status (2026-04-24):**
- Root cause identified for wrong allocations: guest chat was using `simple_runtime` + heuristic `allocate_plan`, which dropped chain constraints and bypassed the main DeFi opportunity engine.
- Remediated: allocation prompts now parse chain and asset hints, use the production DeFi opportunity engine first, deep-analyze finalists with bounded fallbacks, and emit multi-step reasoning frames.
- Remediated: Sentinel explanation prompts are now routed away from allocation and answered with grounded methodology text based on the live scoring model.
- Remediated: chat/swap routes now keep the main app sidebar, chat sessions are accessible again for guest flows via local session storage, and the swap screen has been restyled toward the reference composer.
- Validation currently passing: `pytest tests/agent/test_simple_runtime.py tests/agent/tools/test_allocate_plan.py tests/integration/test_demo_parity.py -q`, `bash scripts/validate_demo_parity.sh`, and `npm --prefix web run build`.

---

## Demo Contract (the thing we must reproduce)

**User message:** "I have $10,000 USDC. Allocate it across the best staking and yield opportunities, risk-weighted using Sentinel scores."

**Demo-mandated UI sequence** (from `main:web/app/agent/chat/page.tsx`):
1. **PreviewBanner** (emerald strip, "Preview of the AI Agent Chat layout · Sentinel scoring layered in").
2. **Framed chat panel** (rounded-2xl border, title strip "allocate $10k yield", New + 15 chats pills on the right).
3. **UserBubble**: the prompt (emerald right-aligned bubble, 8x8 U avatar).
4. **ReasoningAccordion** expanded (8 steps, timestamp): Parsed intent / DefiLlama 2,041 candidates / TVL filter / Sentinel scoring / Shield cross-check / drop 3 / select 5 / execution plan.
5. **AssistantBubble**: "Here's a risk-weighted allocation…" with <strong>89 / 100</strong> and <strong>5.6%</strong>.
6. **AllocationCard** (purple border, "Allocation Proposal" + "Sentinel × DefiLlama" badge, 4 StatTiles: Deploy / Blended APY / Chains / Sentinel weighted, 5 position rows with rank chip, protocol · asset · chain pill · "via router" · TVL, APY + Sentinel pill + USD/weight). Combined Position footer strip.
7. **AssistantBubble**: "Below is the Sentinel scoring breakdown…"
8. **SentinelScoreCard** (purple "Sentinel Pool Scores" + "Ilyon safety lens" badge, Dimensions strip, 5 matrix rows: rank chip, protocol · asset, chain pill, fit pill, risk pill, score/100, 4 ScoreBars Safety/Yield dur./Exit liq./Confidence, Flags line). Counts footer: 4 Low, 1 Medium, 89/100 weighted.
9. **ReasoningAccordion collapsed** (3 steps).
10. **AssistantBubble**: "Ready to execute?…"
11. **ExecutionPlanCard** (purple border, "Execution Plan" + amber "Awaiting signatures · 5", 4 StatTiles: Txs/Wallets/Total gas/Slippage, 5 rows verb+amount+asset→target, chain pill, router, wallet, gas, shield disclaimer, Start signing + Rebalance buttons).
12. **Quick chips**: Rebalance now / Low-risk only / Maximize APY / Explain Sentinel / Skip Pendle.
13. **Composer**: rounded input with ArrowUp icon, "Enter — send · Shift+Enter — new line" hint.

**Demo-mandated data shape:** 5 positions — Lido stETH (ETH, 3.1%, Sentinel 94, 35%), Rocket Pool rETH (ETH, 2.9%, 91, 20%), Jito JitoSOL (Sol, 7.2%, 88, 20%), Aave v3 aArbUSDC (Arb, 4.8%, 90, 15%), Pendle PT-sUSDe (Mainnet, 18.2%, 71, 10%). Weighted Sentinel 89/100, blended APY ≈5.6%, 3 chains, $31.2B combined TVL. Execution: 5 txs, MetaMask+Phantom, ~$17.16 total gas, 0.5% slippage cap. **Live system can select different pools if Sentinel scores justify it, but must honor the same schema and density.**

---

## File Structure

**Create:**
- `src/agent/tools/allocate_plan.py` — single-shot tool that composes DefiLlama → Sentinel → Shield → 3 cards (allocation, sentinel_matrix, execution_plan).
- `src/allocator/composer.py` — pure function: pools + risk budget → ranked positions with weights.
- `web/components/agent/DemoChatFrame.tsx` — pixel-faithful container (PreviewBanner + framed panel + title strip + quick-chips strip).
- `web/components/agent/cards/AllocationCard.tsx` — purple-themed rewrite matching demo.
- `web/components/agent/cards/SentinelMatrixCard.tsx` — new card variant (card_type `sentinel_matrix`).
- `web/components/agent/cards/ExecutionPlanCard.tsx` — purple-themed rewrite matching demo.
- `web/components/agent/QuickChips.tsx` — 5-chip horizontal strip.
- `tests/agent/tools/test_allocate_plan.py` — TDD harness with live DefiLlama golden samples.
- `tests/integration/test_demo_parity.py` — POST /api/v1/agent with the demo prompt, assert SSE frames match demo schema (3 cards, 2 reasoning phases, 3 assistant bubbles).
- `scripts/validate_demo_parity.sh` — e2e validation: starts server, curl-POSTs the demo prompt, parses SSE, prints PASS/FAIL.

**Modify:**
- `web/app/agent/chat/page.tsx` — wrap ChatShell in DemoChatFrame; inject QuickChips.
- `web/components/agent/ChatShell.tsx` — accept frame props, emit sessionId upward.
- `web/components/agent/MessageList.tsx` — alternate rendering order: reasoning block, cards, assistant text — to match demo sequence.
- `web/components/agent/ReasoningAccordion.tsx` — match demo styling (purple, brain icon, 01/02 prefixes, timestamp below).
- `web/components/agent/AssistantBubble.tsx` — 8x8 A avatar, purple bg, tl-sm corner.
- `web/components/agent/UserBubble.tsx` — 8x8 U avatar, emerald bg, tr-sm corner, timestamp.
- `web/components/agent/cards/CardRenderer.tsx` — route `allocation`, `sentinel_matrix`, `execution_plan` to the new components; re-export old cards for backward compat.
- `web/components/agent/Composer.tsx` — rounded-2xl frame + ArrowUp button + help text.
- `web/types/agent.ts` — add `sentinel_matrix` card type + payload; tighten `AllocationPayload` and `PlanPayload` to match demo fields (per-position: rank, protocol, asset, chain, apy, sentinel, risk, fit, weight, usd, tvl, router, safety, durability, exit, confidence, flags; per-step: index, verb, amount, asset, target, chain, router, wallet, gas).
- `src/api/schemas/agent.py` — extend `CardType` enum with `sentinel_matrix`; add pydantic models `AllocationPayload`, `SentinelMatrixPayload`, `ExecutionPlanPayload` mirroring the demo.
- `src/agent/runtime.py` — give the ReAct prompt an explicit "For allocation intents, call `allocate_plan` exactly once" rule.
- `src/agent/simple_runtime.py` — treat "allocate" / "yield" / "risk-weighted" / "diversify" as an allocate_plan intent.
- `src/agent/tools/__init__.py` — register the new allocate_plan tool.

**Test:**
- `web/tests/app/agent-chat-demo-parity.test.tsx` — render the chat page with a mocked stream that emits the demo sequence; assert key DOM elements (PreviewBanner, purple AllocationCard, SentinelMatrixCard with 5 rows, ExecutionPlanCard with 5 steps, 5 QuickChips).

---

## Task List

### Task 0: Establish baseline — run the current system against the demo prompt

**Files:** none (observation only).

- [ ] **Step 1:** Start aiohttp server on :8080 in background (`python -m src.main`).
- [ ] **Step 2:** Curl the endpoint with the exact demo prompt:
  ```bash
  curl -N -X POST http://localhost:8080/api/v1/agent \
    -H 'Content-Type: application/json' \
    -d '{"session_id":"demo-1","message":"I have $10,000 USDC. Allocate it across the best staking and yield opportunities, risk-weighted using Sentinel scores."}'
  ```
- [ ] **Step 3:** Save the full SSE transcript to `.demo-baseline.log`.
- [ ] **Step 4:** Catalog gaps between what came back and the demo contract above. Record them as TaskCreate follow-ups.

### Task 1: Backend — `allocate_plan` tool + composer

**Files:**
- Create: `src/allocator/composer.py`, `src/agent/tools/allocate_plan.py`, `tests/agent/tools/test_allocate_plan.py`.
- Modify: `src/agent/tools/__init__.py`, `src/api/schemas/agent.py`.

Behavior: accept `{ usd_amount: float, risk_budget?: "conservative"|"balanced"|"aggressive", chains?: string[] }`. Query DefiLlama yield endpoint, filter by TVL ≥ $200M + audit-present + ≥ 180 days live, score via Sentinel, drop by Shield verdict, pick top-5 with position cap 35%, emit three cards in the same envelope (or queued via StreamCollector). Return `ToolEnvelope` with `card_type="allocation"` for the primary, and use `collector.emit_card()` to push `sentinel_matrix` and `execution_plan` as follow-up frames.

- [ ] Write failing unit test `test_composer_picks_top_five_with_cap` (stub DefiLlama client, assert ranking + weights sum to 100).
- [ ] Implement `composer.py::compose_allocation(pools, usd, risk_budget) -> list[Position]`.
- [ ] Run test → PASS. Commit.
- [ ] Write failing integration test `test_allocate_plan_emits_three_cards` (mock ReAct loop, assert Collector drained `allocation`, `sentinel_matrix`, `execution_plan`).
- [ ] Implement `allocate_plan.py`.
- [ ] Run test → PASS. Commit.

### Task 2: Backend — schemas for strict payload shape

**Files:**
- Modify: `src/api/schemas/agent.py`, `web/types/agent.ts`.
- Create: `tests/api/schemas/test_demo_payloads.py`.

- [ ] Add pydantic models mirroring demo-mandated fields exactly. Strict mode (forbid extra).
- [ ] Extend `CardType` with `sentinel_matrix` and `execution_plan` (rename `plan` to `execution_plan` via alias).
- [ ] Regenerate TS types (`scripts/gen_agent_types.py`) and commit both.
- [ ] Test that a fully-populated sample validates and a missing-field sample fails.

### Task 3: Backend — prompt guard rails for allocation intents

**Files:**
- Modify: `src/agent/runtime.py` (ReAct prompt), `src/agent/simple_runtime.py` (keyword intent).

- [ ] Add explicit system-prompt rule: "When the user asks to allocate / distribute / diversify an amount into yield, call `allocate_plan` exactly once; do not call other tools first."
- [ ] Add `allocate_plan` to simple_runtime INTENT_PATTERNS, params `{ usd_amount, risk_budget }`.
- [ ] Integration test: POST demo prompt → transcript contains exactly one `tool` frame with `name="allocate_plan"`.

### Task 4: Frontend — DemoChatFrame + rewritten bubbles/accordion

**Files:**
- Create: `web/components/agent/DemoChatFrame.tsx`, `web/components/agent/QuickChips.tsx`.
- Modify: `AssistantBubble.tsx`, `UserBubble.tsx`, `ReasoningAccordion.tsx`, `Composer.tsx`, `ChatShell.tsx`, `web/app/agent/chat/page.tsx`.

- [ ] Lift visuals directly from `main:web/app/agent/chat/page.tsx` (PreviewBanner, title strip, QuickChip, Composer hint).
- [ ] Ensure ReasoningAccordion supports `expanded` default + numbered `01/02` prefixes + timestamp below.
- [ ] Ensure UserBubble and AssistantBubble have the avatar circles and tl-sm / tr-sm corner style.
- [ ] Snapshot test: `agent-chat-demo-parity.test.tsx` renders the demo sequence from fixture SSE frames and matches structural expectations.

### Task 5: Frontend — rewritten AllocationCard / SentinelMatrixCard / ExecutionPlanCard

**Files:**
- Create: `web/components/agent/cards/AllocationCard.tsx`, `SentinelMatrixCard.tsx`, `ExecutionPlanCard.tsx`.
- Modify: `CardRenderer.tsx`.

- [ ] Port each component verbatim from `main` demo (purple theme, StatTile, ScoreBar, ChainPill, FitPill, SentinelPill, PositionRow, SentinelMatrixRow, ExecutionRow).
- [ ] Replace hardcoded demo arrays with `payload.*` props.
- [ ] Route `CardRenderer` switch for `allocation` / `sentinel_matrix` / `execution_plan` (or legacy `plan`).
- [ ] Storybook-free visual test: component renders with fixture payload and required DOM nodes exist (5 position rows, 4 ScoreBars per matrix row, etc.).

### Task 6: Integration — end-to-end demo parity harness

**Files:**
- Create: `tests/integration/test_demo_parity.py`, `scripts/validate_demo_parity.sh`.

- [ ] Script boots the server, POSTs the demo prompt, consumes SSE, asserts frame sequence: thought+ ≥ 1 tool (name=allocate_plan) ≥ 3 cards (types allocation/sentinel_matrix/execution_plan) ≥ final (text contains "89" or similar weighted score) ≥ done.
- [ ] Assert each card carries all required fields (rank, sentinel, risk, flags per position; verb/amount/gas/wallet per step; safety/durability/exit/confidence per matrix row).
- [ ] Must return exit 0 before merge.

### Task 7: Integration — Playwright-less headed sanity

**Files:**
- Create: `web/tests/e2e/demo-parity.sse.test.tsx` (jsdom; mock fetch with a recorded SSE transcript from Task 6).

- [ ] Render `<AgentChatPage>` with mocked stream, assert the following DOM counts: 1 PreviewBanner, 1 AllocationCard with 5 rows, 1 SentinelMatrixCard with 5 rows × 4 ScoreBars, 1 ExecutionPlanCard with 5 steps, 5 QuickChips, composer hint present.

### Task 8: Data wiring — real DefiLlama pools with enrichment

**Files:**
- Modify: `src/data/defillama.py` (if missing fields), `src/allocator/composer.py`.

- [ ] Pull the `/pools` endpoint; map each to `{ protocol, asset, chain, apy, tvl, auditsUrl, launchDate }`.
- [ ] Cross-check each with Sentinel (already in `src/agents/sentinel.py`) for safety/durability/exit/confidence scores.
- [ ] Cross-check each with Shield (`src/shield/...`) for flags (oracle-dep, upgradeable proxy, admin keys, rekt history).
- [ ] Ensure the 5 selected pools always have numeric fields (no `null` leak to UI).

### Task 9: Error handling + UX polish

**Files:**
- Modify: `CardRenderer.tsx`, `MessageList.tsx`, `ChatShell.tsx`.

- [ ] If any tool errors: show an inline error bubble (red border, AlertTriangle icon), keep other cards rendered.
- [ ] Empty composer disables send; Enter sends; Shift+Enter newlines.
- [ ] Auto-scroll to latest message; preserve scroll if user is looking up.

### Task 10: Final gate — live validation + commit

- [ ] `scripts/validate_demo_parity.sh` exits 0.
- [ ] `npm --prefix web run build` succeeds with no type errors.
- [ ] `pytest -q tests/agent tests/integration tests/api/schemas` all pass.
- [ ] Manually drive `/agent/chat` in the browser; eyeball matches the demo screenshots.
- [ ] Squash-commit onto `staging` with message `feat(agent): demo-parity + real allocate_plan pipeline`.

---

## Cross-Workstream Dependency Map

```
Task 0 (baseline) ──┐
                    ├──► Task 1 (composer+tool) ──► Task 3 (prompt) ──► Task 6 (e2e)
Task 2 (schemas) ───┤                                                    │
                    └──► Task 5 (cards)  ──► Task 4 (frame)  ──► Task 7 (jsdom)  ──► Task 10
                                                                         │
Task 8 (data) ──────────────────────────────────────────────────────────┘
                                                                         │
Task 9 (polish) ─────────────────────────────────────────────────────────┘
```

---

## Definition of Done

All ten tasks pass validation. A user on `staging` who types "I have $10,000 USDC. Allocate it across the best staking and yield opportunities, risk-weighted using Sentinel scores." sees the exact same visual sequence as the demo on `main`, populated with real DefiLlama / Sentinel data, with the agent's reasoning exposed in the Reasoning Accordion, and can click Start Signing (disabled in this phase) + Quick Chips (non-destructive) without errors.
