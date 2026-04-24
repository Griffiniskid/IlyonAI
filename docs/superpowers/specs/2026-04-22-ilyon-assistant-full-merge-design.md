# Ilyon Assistant Full Merge Design

Date: 2026-04-22
Status: Approved in brainstorming, plan written
Primary focus: absorb every assistant feature, UI element, workflow, extension surface, and contract track into Ilyon AI while making Ilyon Sentinel the decision brain for the merged product

## Summary

Ilyon already contains the beginnings of the assistant merge: preview routes at `/agent/chat` and `/agent/swap`, a live-but-thin agent runtime in `src/api/routes/agent.py`, shared card rendering in `web/components/agent/`, chat persistence tables in `migrations/versions/001_agent_platform.py`, and an extension/contracts scaffold in `extension/` and `contracts/`.

The separate assistant repository contains the richer, already-built product behavior that still needs to be absorbed:

1. full conversational execution UX
2. saved chats and chat controls
3. structured execution previews for swap, bridge, transfer, staking, and LP deposit
4. full home/dashboard chrome including ticker, market modules, wallet rail, and control surfaces
5. multi-chain portfolio aggregation
6. extension popup and sidepanel behavior
7. Greenfield-backed memory foundations
8. affiliate-aware contract and monetization groundwork

This spec defines the full-product merge target. The objective is not to keep two systems side by side. The objective is one Ilyon product where all assistant capabilities live inside Ilyon-owned runtime, storage, UI, extension, and contract boundaries, and where Ilyon Sentinel, Shield, wallet intelligence, and DeFi scoring engines shape the assistant's outputs before the user sees them.

## Decisions Captured During Brainstorming

- Backend target: one unified Ilyon backend, no FastAPI sidecar.
- Assistant repository role after merge: source/reference only, not a separately maintained runtime.
- Scope: include every assistant feature and element, not only chat and swap route parity.
- UI scope includes shell-level and dashboard-level absorption: ticker, market overview, quick actions, wallet rail, status surfaces, and saved-chat controls.
- Partial/foundation assistant tracks must be productized in Ilyon rather than remaining partial: popup, sidepanel, Greenfield memory, affiliate integration.
- Brand/system rule: Ilyon remains the product shell and visual authority; assistant UX strengths are absorbed into that shell.
- Intelligence rule: assistant execution and interaction patterns are preserved, but Ilyon Sentinel/Shield/DeFi intelligence override weaker assistant heuristics wherever Ilyon already has stronger evidence engines.
- Navigation rule: bridge, stake, transfer, and LP deposit stay as structured in-chat execution cards rather than becoming new top-level routes.

## Why This Spec Exists

The repository review showed that the merge problem is no longer "can Ilyon host an assistant route?" It is now a full system-absorption problem:

- the assistant already has mature working behavior in its own codebase
- Ilyon already has stronger analytics, scoring, and intelligence engines in several domains
- the current merge state only exposes fragments of both systems
- some of the most visible assistant features exist today only as preview plugs or partial extension shells

If this work is executed as a shallow copy, the result will be two merged but still conceptually separate products in one repo. That is explicitly not the target. The merged product must feel like one system:

- one backend
- one web product
- one extension product family
- one contract track
- one decision layer

## Goals

- Absorb every assistant feature and user-visible element into Ilyon-owned runtime paths.
- Replace preview/demo surfaces with real merged product behavior.
- Make Ilyon Sentinel the evidence and judgment plane for assistant recommendations and execution previews.
- Preserve the assistant's strongest UX patterns: natural-language execution, structured cards, saved chat continuity, multi-wallet workflows, and clear wallet-signing handoff.
- Productize assistant partial tracks: popup, sidepanel, Greenfield memory, and affiliate integration.
- Keep the assistant repository as reference code only once parity is achieved.
- Verify the merged system by real product flows rather than by route existence alone.

## Non-Goals

- Running a long-term FastAPI sidecar beside Ilyon's aiohttp backend.
- Keeping the assistant app as a second maintained end-user product.
- Rewriting assistant functionality from scratch when the working implementation can be ported and adapted.
- Allowing assistant-native heuristics to override stronger Ilyon evidence engines.
- Adding new top-level routes for every execution type when in-chat cards are the intended interaction model.

## Delivery Target

After the merge, the product should be understood as follows:

- `src/` is the only backend runtime and owns auth, chat, execution builders, portfolio services, memory metadata, and intelligence enrichment.
- `web/` is the only full web product and contains the full absorbed assistant experience, including product chrome and dashboard elements.
- `extension/` is the browser-extension companion to the same backend and shared UI/contract model.
- `contracts/` is the canonical home for affiliate-fee contract logic, deployment wiring, and tests.
- `IlyonAi-Wallet-assistant-main/` stays in-repo only for reference and migration provenance.

## Architecture Overview

### Runtime Ownership Map

1. Unified backend in `src/`
   - aiohttp routes remain the single HTTP surface
   - assistant auth, chat, portfolio, and execution capabilities are ported into Ilyon route and service modules
   - Ilyon scoring, Shield, wallet intelligence, and DeFi engines become first-class dependencies of assistant outputs

2. Unified web product in `web/`
   - Ilyon shell/navigation remains the frame
   - assistant's full chrome and route-local behavior are absorbed into that frame
   - `/agent/chat`, `/agent/swap`, `/portfolio`, `/`, and dashboard surfaces become real merged experiences

3. Unified extension product in `extension/`
   - popup, sidepanel, and background worker connect to the same backend and the same auth/session model
   - extension becomes a real companion product, not a placeholder shell

4. Unified contract track in `contracts/`
   - affiliate hook remains the monetization contract track
   - backend and UI only surface affiliate behavior where the flow is genuinely supported

### Program Decomposition

This is one coordinated merge program split into ordered subprojects:

1. backend foundation and auth/session unification
2. assistant runtime and execution-flow absorption
3. web shell and dashboard chrome absorption
4. chat, swap, portfolio, and market surface replacement
5. Sentinel/Shield/wallet-intel decision integration
6. extension productization
7. Greenfield memory productization
8. affiliate hook operational integration
9. final parity verification and reference freeze

### Canonical Product Rules

- The main web app is the mature, full-featured experience.
- The extension is a real product companion with thinner spatial constraints, not a mock.
- All transaction execution remains non-custodial: backend prepares, wallet signs.
- No assistant feature is allowed to remain reference-only once the merge is complete.
- If an assistant element is not copied literally, it must be superseded by an Ilyon-native implementation with the same or better user value.

## Unified Backend Merge

### Backend Shape

The backend stays inside Ilyon's aiohttp application. Assistant FastAPI endpoints are mapped into Ilyon-owned modules instead of being preserved as a separate app.

Primary backend responsibilities after merge:

- unified wallet auth for MetaMask and Phantom
- saved chat sessions and message persistence
- SSE agent turn streaming
- deterministic intent routing for high-risk actions
- multi-chain portfolio aggregation
- bridge-status lookup and transaction preview preparation
- Sentinel/Shield/wallet-intel/DeFi enrichment on outputs
- memory metadata and sync coordination
- affiliate-aware preview metadata where supported

### Auth and Identity

`web_users` becomes the single web principal table for web and extension flows. The auth system must support multiple wallet contexts per user:

- primary EVM wallet
- primary Solana wallet
- preferred signer type
- active chain context
- remembered wallet/display metadata

Ilyon's existing auth flow in `src/api/routes/auth.py` is extended rather than replaced. MetaMask and Phantom verification become first-class verifiers inside the same auth system, not independent product branches.

### Assistant Runtime and Tooling

The live runtime in `src/agent/runtime.py` and `src/api/routes/agent.py` becomes the canonical conversational execution loop.

Merged runtime behavior:

- deterministic fast-path routing for swap, bridge, transfer, stake, LP, portfolio, and pool lookup
- agentic reasoning for open-ended prompts and orchestration
- structured tool envelopes for UI cards
- persisted session state and recent-memory window
- Sentinel and Shield enrichment on relevant tool outputs
- clear separation between read-only discovery and unsigned transaction assembly

### Persistence

`chats` and `chat_messages` remain the core conversation store. Stored messages keep:

- role/content
- structured card references
- tool trace metadata
- delivery status
- future memory linkage identifiers

Additional persistence is required for:

- multi-wallet identity binding
- optional Greenfield object metadata/indexing
- affiliate-preview analytics where those flows are active

## Web Surface Merge

### Route Mapping

- `/agent/chat`: replace preview with the real absorbed chat workspace.
- `/agent/swap`: replace preview with the real absorbed swap composer and chat handoff.
- `/portfolio`: keep route, expand into assistant-grade multi-wallet and multi-chain utility while retaining Ilyon risk framing.
- `/` and dashboard surfaces: absorb the assistant's onboarding, quick actions, feature framing, and market modules.

No new top-level routes are added for bridge, staking, transfer, or LP deposit. Those remain structured in-chat execution flows.

### Full Assistant Product Chrome Absorption

The merge target includes assistant shell-level and dashboard-level features, not only route parity.

Elements that must be absorbed into Ilyon:

- intro / landing experience
- top moving-token / market ticker bar
- market overview modules
- quick actions and capability framing
- wallet status card and user status row
- saved-chat controls
- backend/system status indicators
- market mini-list / ambient market widgets
- portfolio summary strips and utility widgets
- Greenfield memory status and, after productization, real memory UX

These elements are classified as:

- global shell elements
- home/dashboard elements
- route-local interaction elements
- extension-only elements

Nothing is dropped just because it is not part of chat or swap.

### Component Strategy

Ilyon's shell, route structure, and emerald-led brand system remain the base. The assistant's richer UX is absorbed through shared and expanded components:

- saved chat rail
- reasoning/progress UI
- structured cards for balance, pool, universal actions, and execution previews
- wallet execution affordances
- empty-state grids and quick prompts
- dashboard cards and ticker/market widgets

Current components in `web/components/agent/` are merge anchors, not final architecture. They are expanded to support the full assistant experience and the richer merged data contracts.

### Portfolio Merge

The merged portfolio page keeps Ilyon's strengths:

- health/risk framing
- capability/risk breakdown
- token intelligence links

It also absorbs the assistant's practical utility:

- multi-wallet aggregation
- Solana plus EVM inventory merging
- assistant-friendly token formatting and quick utility
- chat-to-portfolio continuity

## Extension, Memory, And Contracts

### Extension Productization

`extension/` is part of the required shipped product surface.

Popup must provide:

- quick-access market context
- wallet/auth status
- quick prompts and shortcuts
- compact portfolio and recent-action context
- handoff into sidepanel or full web app

Sidepanel must provide:

- real chat sessions
- structured card rendering
- quick prompts
- backend/status visibility
- practical lightweight parity with the main assistant experience

Background worker must provide:

- token/session storage
- auth propagation
- notification dispatch
- assistant event routing
- future page-context handoff hooks

### Greenfield Memory Productization

The assistant's Greenfield service layer is promoted from infrastructure-only code into a real product capability.

Required memory behavior:

- durable session summary storage
- preference and wallet-context persistence
- shared memory state across extension and web surfaces
- explicit UI memory state
- assistant recall behavior that uses structured memory artifacts instead of dumping raw transcripts

Greenfield remains a capability with clear failure boundaries. Memory degradation must reduce continuity, not break chat or execution.

### Affiliate Hook Productization

`contracts/src/AffiliateHook.sol` already exists in the main repo, so the problem is operational integration rather than contract import.

Productized behavior includes:

- deployable/testable Foundry track
- backend awareness of affiliate-capable routes
- preview-card fee disclosure where affiliate logic is active
- analytics/reporting for affiliate-aware execution outcomes
- strict capability scoping so the UI never implies affiliate routing where it is not actually enabled

## Sentinel Brain Integration And Decision Flow

This section defines what "combined logic" means.

The assistant is the control plane for natural language, wallet execution UX, and structured cards. Ilyon Sentinel is the evidence and judgment plane.

### Decision Rule

Every high-value assistant output is only complete when it contains both:

- assistant execution/discovery payloads
- Ilyon evidence and judgment metadata

### Domain-Specific Integration

1. Swap / bridge / transfer / stake / LP
   - assistant builds route and unsigned payloads
   - Ilyon layers token intelligence, Shield implications, DeFi scoring, and scenario warnings where relevant

2. Pool / yield / staking discovery
   - Ilyon's DeFi analyzer and opportunity engine become the ranking source of truth
   - assistant UX becomes the interaction and card-rendering layer over those ranked results

3. Portfolio and wallet prompts
   - assistant aggregation provides inventory and formatting
   - Ilyon wallet intel, Shield scan, and Sentinel monitoring provide risk interpretation and action guidance

4. General market prompts
   - assistant market discovery and quick UX remain useful
   - judgment-heavy outputs use Ilyon evidence systems rather than assistant-local heuristics

### Output Contract

High-value assistant cards and final answers should be able to carry:

- action/discovery summary
- execution or result payload
- Sentinel block
  - safety
  - durability
  - exit quality
  - confidence
  - risk level
  - strategy fit where relevant
- Shield block where relevant
- warnings and evidence bullets
- explicit signer boundary

### Override Rule

If Ilyon has a stronger evidence engine for a domain, that engine overrides assistant-native heuristics. Porting the assistant does not mean preserving weaker logic where Ilyon already has stronger intelligence.

## Canonical Data Flows

### Flow A: Chat Prompt To Structured Preview

1. User submits prompt from web or extension.
2. Auth/session layer resolves user and wallet context.
3. Runtime chooses deterministic fast-path or agentic lane.
4. Assistant builder/service returns discovery or unsigned transaction payload.
5. Sentinel/Shield/DeFi/wallet-intel decorators enrich the envelope.
6. SSE emits reasoning, tool, card, and final frames.
7. UI renders structured cards and wallet-signing affordances.

### Flow B: Portfolio To Risk Interpretation

1. Portfolio aggregator collects holdings across connected and tracked wallets.
2. Token and wallet-level intelligence enriches positions.
3. Sentinel/Shield summaries roll up into page and chat-visible risk surfaces.
4. User can pivot from portfolio holdings into token detail or assistant flows.

### Flow C: Extension To Memory Sync

1. Popup or sidepanel resolves auth/session state from extension storage.
2. Chat or action events update backend session state.
3. Structured memory summary is persisted to Greenfield and indexed in Ilyon metadata.
4. Subsequent sessions can recover memory context without depending on local-only extension state.

### Flow D: Execution Preview To Affiliate Disclosure

1. Execution builder identifies whether affiliate-aware routing applies.
2. Preview card carries explicit fee and route metadata.
3. UI discloses affiliate behavior only when active.
4. Backend records analytics/metadata for eligible flows.

## Verification Gates

The merge is only complete when these gates are green:

1. Parity gate
   - every assistant feature and visible element is mapped to a real merged Ilyon destination

2. Behavior gate
   - strongest demo-worthy workflows work end to end in merged Ilyon:
   - natural-language swap to preview
   - bridge flow with status tracking
   - portfolio scan
   - yield/pool discovery
   - saved chat reload
   - extension invocation

3. Judgment gate
   - outputs visibly use Sentinel/Shield/DeFi intelligence when relevant

4. Productization gate
   - popup, sidepanel, Greenfield memory, and affiliate integration are real product features, not placeholders

5. Reference freeze gate
   - assistant repo is no longer part of active runtime paths

## Risks And Mitigations

- Risk: two merged-but-separate architectures remain hidden inside one repo.
  - Mitigation: single backend runtime, single web product, reference-only assistant repo.

- Risk: assistant UI parity is achieved without real Ilyon intelligence integration.
  - Mitigation: output contract requires Sentinel/Shield/evidence blocks on relevant flows.

- Risk: extension and memory tracks remain soft-scoped and never fully shipped.
  - Mitigation: explicit productization gate and dedicated implementation tracks.

- Risk: contract integration is overstated in UX before execution paths are truly wired.
  - Mitigation: capability-scoped affiliate disclosure and test-backed route enablement.

- Risk: broad refactors destabilize the repo before parity exists.
  - Mitigation: sequence implementation around parity first, cleanup second.

## Implementation Sequencing

The implementation must proceed in this order:

1. backend contracts, auth/session, and wallet context foundations
2. runtime and deterministic execution-flow absorption
3. web shell/home chrome absorption
4. chat, swap, portfolio, and market surface replacement
5. extension productization
6. Greenfield memory productization
7. affiliate integration
8. final parity verification and reference freeze

The advanced implementation plan written alongside this spec is the execution document for those phases.
