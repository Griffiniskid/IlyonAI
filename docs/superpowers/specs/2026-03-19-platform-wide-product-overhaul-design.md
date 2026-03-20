# Platform-Wide Product Overhaul Design

Date: 2026-03-19
Status: Approved in brainstorming, pending plan
Primary focus: one mega-spec that upgrades product design, smart money intelligence, speed, and platform reliability

## Summary

AI Sentinel already completed a major DeFi core analysis rework, but the full product experience is still uneven. Key capabilities are present in code yet underutilized in UX, partially wired, or missing platform-level glue. This spec defines a platform-first, phased mega-overhaul that upgrades every major domain in one coherent architecture:

1. product shell and navigation
2. smart money and whale intelligence
3. real-time transport and alerting
4. multi-chain portfolio intelligence
5. speed, caching, and API consistency
6. evidence quality, model governance, and operational reliability

This is a comprehensive design spec. Implementation sequencing should be phased, but all phases are part of one connected roadmap.

## Decisions Captured During Brainstorming

- Scope direction: all major areas in one mega-spec
- Execution style: platform-first phased implementation
- Whale direction: full smart money platform (not just a feed)
- Navigation direction: full app shell with discoverability-first IA
- Include in scope: real-time feeds, alerts system, and rekt database
- Portfolio direction: full multi-chain portfolio support
- Design direction: preserve and polish existing emerald visual identity
- Performance target profile: balanced targets
- Access policy: all product capabilities remain free during testing; no monetization tiers in this scope

## Why This Spec Exists

After repository review, the largest product gaps are no longer in core DeFi scoring logic. They are now cross-product cohesion, user discoverability, platform integration, and real-time intelligence delivery.

Primary observed gaps:

- Feature discoverability is low: only a subset of routes are reachable through primary navigation.
- Whale tooling is useful but still feed-like; it is not yet a full smart money intelligence surface.
- Some wallet forensics methods are scaffolded but still placeholder-heavy.
- Sentinel monitoring exists, but user-facing alert delivery and management are missing.
- Real-time transport is limited; most UX still relies on pull/poll patterns.
- Visual quality is inconsistent across old polished pages and newer feature surfaces.
- Portfolio support is not yet fully multi-chain at product parity.
- API contracts vary by route family, increasing frontend complexity and drift risk.

## Goals

- Build one cohesive product shell where all major features are discoverable and navigable.
- Evolve whale tracking into a full smart money intelligence platform.
- Ship real-time intelligence delivery for analysis status, whale flows, and alerts.
- Provide portfolio intelligence across all supported chains.
- Meet product performance targets:
  - first meaningful response under 5 seconds
  - deep analysis completion under 30 seconds
  - whale/event feed latency under 5 seconds
  - page transitions under 1.5 seconds
- Standardize API contracts, evidence metadata, and confidence semantics.
- Keep all core capabilities available for free during this testing phase.

## Non-Goals For This Cycle

- Paid feature tiers, billing, or paywall gating
- Automatic trade execution or fund movement
- Full institutional compliance framework buildout
- Unlimited chain additions beyond currently supported target chains

## Design Principles

- Product-first coherence: users should feel one platform, not isolated tools.
- Evidence-first intelligence: every claim includes source, freshness, and confidence.
- Progressive delivery: fast partial results first, deep enrichment second.
- Safe degradation: slow or failed providers reduce confidence, not availability.
- Explainability over opacity: "what changed / why it matters / what to do" at every major surface.
- Reuse primitives: shared component system and shared data contracts across domains.

## Architecture Overview

### Domain Map

The system should be organized into six cooperating domains:

1. Intelligence Core
   - token, pool, contract, and DeFi analysis pipelines
   - normalized scoring, evidence, and scenario generation

2. Smart Money Graph
   - wallet/entity graph model
   - whale flows, behavioral signals, and cluster intelligence

3. Safety Loop
   - sentinel detection pipeline
   - exploit/rekt intelligence
   - approval and risk alerts

4. Portfolio Intelligence
   - multi-chain holdings and exposures
   - risk decomposition and alert impact

5. Product Shell and UX Runtime
   - app shell, discoverability, and route IA
   - command palette and contextual panels

6. Platform Delivery
   - REST + streaming APIs
   - caching tiers, event bus, tracing, and reliability controls

### Canonical Entities

All feature domains should use shared identifiers and schemas for:

- `wallet`
- `entity`
- `token`
- `pool`
- `protocol`
- `chain`
- `event`
- `analysis`
- `alert`

This removes data-model drift between pages and allows true cross-feature reasoning.

### Core Event and Data Flows

The platform should define three canonical producer-consumer flows with explicit ownership.

#### Flow A: Analysis to UI

1. User/API starts analysis request.
2. Intelligence Core creates `analysis` record and emits `analysis.started`.
3. Pipeline stages emit `analysis.progress` with incremental payloads.
4. On completion, service stores final snapshot and emits `analysis.completed`.
5. Stream gateway pushes events to subscribed clients.
6. UI reconciles stream updates with REST snapshot reads.

Ownership:

- Producer: Intelligence Core
- Persistence: analysis store
- Stream delivery: Platform Delivery
- Consumer: web app

Contract minimum:

- `event_id`
- `event_type`
- `analysis_id`
- `stage`
- `trace_id`
- `occurred_at`
- `payload_version`

Idempotency key:

- `analysis_id + event_type + stage + sequence`

#### Flow B: Sentinel to Alert Delivery

1. Sentinel emits raw risk event.
2. Alert orchestrator enriches and correlates related signals.
3. Dedupe policy resolves duplicate/near-duplicate alerts.
4. Alert record is persisted with lifecycle state.
5. Delivery fanout sends to in-app stream and configured channels.
6. UI updates alert inbox and global indicator.

Ownership:

- Producer: Sentinel/Safety Loop
- Correlation/dedupe: Alert Orchestrator
- Persistence: alert store
- Delivery: Stream gateway + channel workers
- Consumer: web app and integrations

Contract minimum:

- `alert_id`
- `severity`
- `rule_id`
- `subject_type`
- `subject_id`
- `correlation_id`
- `trace_id`
- `state`

Dedupe key:

- `user_id + rule_id + subject_id + severity + 5m_bucket`

#### Flow C: Ingestion to Smart Money Insights

1. Chain ingestion pulls transactions/events.
2. Normalizer converts chain-specific data to canonical event schema.
3. Graph service updates wallet/entity graph edges.
4. Signal engine computes derived smart money features.
5. Insight snapshots and stream events are published.
6. Smart money pages and scoring factors consume results.

Ownership:

- Producer: data adapters
- Canonical normalization: ingestion normalization service
- Graph persistence: Smart Money Graph store
- Signal generation: analytics/signal engine
- Consumers: smart money UI + scoring modules

Failure handling:

- retries with bounded exponential backoff
- dead-letter queue for repeatedly failing events
- per-source circuit breaker
- stale markers if source lag exceeds threshold

## Product Information Architecture

## App Shell

Introduce a full app shell:

- desktop: collapsible left sidebar + top command bar + contextual right insights panel
- mobile: bottom navigation for primary domains + sheet navigation for deep routes

## Navigation Taxonomy

Navigation should group by user intent:

- Discover
  - dashboard
  - trending
  - market overviews
- Analyze
  - token
  - pool
  - contract
  - DeFi
- Smart Money
  - smart money hub
  - whales feed
  - wallet/entity profile
  - flows explorer
- Protect
  - shield
  - audits
  - rekt database
  - alerts inbox
- Portfolio
  - multi-chain holdings
  - exposures and scenarios
- Settings
  - auth, preferences, integrations

## Command Palette

Provide a global action/search palette:

- navigate pages
- search token/wallet/protocol
- run analyses
- create watchlists
- create alert rules

## Smart Money Platform Design

## Product Surfaces

Build a dedicated smart money domain with:

- `/smart-money` hub
- `/whales` advanced feed
- `/wallet/[address]` profile
- `/flows` capital movement explorer
- smart money overlays embedded in token and DeFi pages

## Intelligence Capabilities

Core smart money capabilities:

- multi-chain flow ingestion and normalization
- wallet-to-entity clustering with confidence scoring
- wallet behavior profiling (style, conviction, rotation, hold behavior)
- signal families: accumulation, distribution, liquidity extraction, insider proximity, coordinated activity
- evidence traces and confidence bands on all surfaced insights

## Forensics Implementation Upgrade

Wallet forensics should replace placeholder pathways with concrete data-backed implementations for:

- deployment history extraction
- funding chain tracing
- related-wallet discovery

Each result should include explicit confidence and fallback metadata.

## Real-Time and Alerts Design

## Transport

Add live delivery channels for high-value updates:

- WebSocket as primary
- SSE fallback
- polling fallback for compatibility

Event families:

- `analysis.progress`
- `analysis.completed`
- `whale.detected`
- `smart_money.shift`
- `alert.created`
- `portfolio.risk_changed`

## Alerts Product

Create `/alerts` plus global bell tray:

- unread state
- severity filters
- watchlist/channel rules
- dedupe and suppression controls
- acknowledgement workflow
- deep-link actions to relevant detail pages

Alert state model:

- `new` -> `seen` -> `acknowledged`
- optional `snoozed_until`
- optional `resolved_at`

Delivery channels in scope for this cycle:

- required: in-app stream/inbox
- required: browser notification support (opt-in)
- optional: webhook delivery (testing, no paywall)
- deferred: email/telegram/discord connectors

Alert delivery SLOs:

- high/critical p95 delivery latency under 5 seconds
- medium/low p95 delivery latency under 15 seconds
- duplicate-alert rate under 2% per 24h window
- dropped alert events under 0.1% per 24h window

Delivery failure policy:

- retry: exponential backoff with bounded attempts
- failover: in-app persistence always retained even if external channel fails
- dead-letter queue for repeated delivery failure
- operator-visible delivery health dashboard

## Sentinel Delivery Loop

Sentinel detections must route through alert orchestration:

1. detection event
2. enrichment/correlation
3. dedupe and throttling
4. severity assignment
5. user delivery and UI state updates

## Rekt Intelligence Design

Build `/rekt` as a full intelligence page set:

- incident timeline
- protocol incident profiles
- exploit vectors and impact summaries
- chain and sector filtering
- links to related assets/protocols/watchlists

Rekt context should appear inside token/DeFi/portfolio risk sections when relevant.

## Multi-Chain Portfolio Intelligence Design

## Portfolio Scope

Provide first-class multi-chain portfolio support across current target chains.

### Chain Support Matrix (Required for Parity)

Target chains for this cycle:

- Solana
- Ethereum
- Base
- Arbitrum
- BSC
- Polygon
- Optimism
- Avalanche

Required capabilities per chain:

| Capability | Requirement |
|---|---|
| Spot holdings | required |
| LP position tracking | required |
| Lending position tracking | required |
| Vault position tracking | required |
| Risk decomposition | required |
| Alert coverage | required |

Parity definition:

- A chain is "at parity" only when all required capabilities above are implemented and tested.
- If any capability is unavailable for a chain, UI must show explicit degraded status and missing-capability reason.
- Missing data must never silently disappear; users must see confidence/freshness and capability gaps.

Support:

- wallet import and tracking across chains
- normalized holdings (spot, LP, lending, vault)
- risk decomposition by chain, protocol, token
- exposure concentration and correlation flags
- smart-money overlap and divergence views
- portfolio-impact alerts

## Portfolio Narratives

Surface decision-friendly portfolio insights:

- what changed
- what is most exposed
- where risk is rising
- what actions reduce risk concentration

## Speed and Reliability Design

## Two-Speed Response Pattern

Every heavy analysis endpoint should follow:

- Fast lane under 5 seconds using warm snapshots, heuristics, and cached factors
- Deep lane under 30 seconds with full enrichment and synthesis

UI should render fast lane results immediately and progressively hydrate deep insights.

## Cache and Compute Strategy

- precompute jobs for high-demand markets
- layered caching (memory -> redis -> durable snapshot)
- stale-while-revalidate and confidence-aware freshness indicators
- request coalescing on identical workloads
- provider budget enforcement and circuit-breaking

## API Contract Evolution

Standardize response envelope across route families:

- `status`
- `data`
- `meta`
- `errors`
- `trace_id`
- `freshness`

Add cursor pagination and selective fields for heavy feeds.

## Design System and UX Quality Baseline

Preserve the existing emerald identity and polish consistency.

Expand reusable component set:

- DataTable
- Tabs
- Dialog/Drawer
- Tooltip
- Stat cards
- Timeline
- Filter bars
- Skeleton states

Every page must ship with:

- loading state
- empty state
- error state
- last-updated/source context
- mobile-responsive layout parity

## Data Quality and Governance

All model outputs should carry:

- source lineage
- timestamp and freshness class
- confidence
- fallback reason (if degraded)

Add signal quality feedback loops:

- historical replay for alert/signal quality
- analyst/admin feedback hooks for false-positive reduction
- auto-downweighting underperforming heuristics

YAGNI sequencing guard:

- Phase 2-3: collect instrumentation and feedback signals only
- Phase 4-5: evaluate baseline quality and establish thresholds
- Phase 6: enable adaptive auto-downweighting logic after baseline stability is proven

## Security and Access Model

All core features remain free and available during testing.

Security controls are still required:

- route auth scopes where needed
- rate limiting and anti-abuse controls
- signed webhook secrets for outbound integrations
- replay protection for sensitive mutation endpoints
- audit logs for high-risk configuration changes

## Error Handling and Degradation

Platform behavior under partial failure:

- provider failure -> mark affected evidence stale/unavailable, continue with reduced confidence
- stream outage -> auto-fallback to polling
- enrichment timeout -> return partial analysis with explicit missing sections
- alert pipeline pressure -> prioritize high-severity alerts and defer low-severity batches

No user-facing surface should fail hard because one provider is unavailable.

## Testing and Verification Strategy

Testing should include:

- unit tests for new domain services and scoring/signal logic
- contract tests for API envelope consistency
- integration tests for event pipeline and alert routing
- UI tests for app shell, navigation discoverability, and key page workflows
- performance tests for SLO targets (p50/p95)
- replay/backtest suites for smart money and anomaly signals
- chaos-style tests for provider degradation and stream interruptions

### Quantitative Pass Thresholds

- API contract compliance: 100% for standardized envelope on in-scope routes
- Stream reliability: dropped event rate under 0.1% per 24h
- Alert dedupe quality: duplicate rate under 2% per 24h
- Latency SLOs (p95):
  - first meaningful response under 5 seconds
  - deep analysis completion under 30 seconds
  - high/critical alert delivery under 5 seconds
  - route transition under 1.5 seconds on key app-shell navigations
- Regression suite: no increase in failing tests in existing critical test families

### Test Data and Replay Strategy

- Maintain golden fixtures for Solana + EVM event streams
- Maintain 30-day replay windows for smart money signal evaluation
- Preserve known anomaly and incident scenarios as deterministic replay cases
- Version fixtures alongside schema versions to catch compatibility drift

## Risk Register

| Risk | Leading indicator | Impact | Mitigation | Owner domain |
|---|---|---|---|---|
| Provider instability | rising timeout/error rates | stale or missing intelligence | provider budgets, retries, circuit breakers, stale markers | Platform Delivery |
| Event bus saturation | queue lag and consumer backlog | delayed alerts and feeds | backpressure policy, priority queues, autoscaling, dead-letter queue | Platform Delivery |
| Entity graph false positives | high analyst override rate | trust erosion in smart money | confidence gating and conservative merge thresholds | Smart Money Graph |
| Alert fatigue | high mute/snooze and low acknowledgement rates | users ignore important alerts | stronger correlation/dedupe and severity recalibration | Safety Loop |
| Frontend performance regressions | route p95 over target | weak UX and retention drop | route budgets, bundle checks, continuous profiling | Product Shell |
| Multi-chain parity slip | capabilities missing per chain | inconsistent user value | hard phase gates from chain parity matrix | Portfolio + Intelligence Core |

## Implementation Phases

### Phase 1: Product Foundation

Entry criteria:

- canonical route inventory complete
- app shell IA and nav map approved

Deliverables:

- app shell
- navigation IA
- command palette
- design system expansion
- baseline page quality standardization

Exit criteria:

- all major product routes are discoverable from shell navigation
- shared loading/empty/error patterns implemented on in-scope pages
- route transitions meet p95 under 1.5 seconds on key routes

### Phase 2: Smart Money Platform Core

Entry criteria:

- canonical event schema v1 defined
- smart money data source contracts finalized

Deliverables:

- smart money hub and advanced whales feed
- wallet/entity profile pages
- entity graph v1
- multi-chain flow normalization

Exit criteria:

- placeholder forensics pathways replaced for in-scope chains
- evidence/confidence appears on smart money insights
- smart money overlays available in token and DeFi views

### Phase 3: Real-Time and Alerts

Entry criteria:

- event schema and stream auth model implemented
- alert persistence model approved

Deliverables:

- WebSocket/SSE gateway
- alert center and global notification tray
- sentinel-to-alert orchestration
- event correlation and dedupe

Exit criteria:

- high/critical alert delivery p95 under 5 seconds
- alert state model (`new/seen/acknowledged`) fully functional
- dropped event and duplicate thresholds satisfy quantitative pass criteria

### Phase 4: Rekt + Portfolio Expansion

Entry criteria:

- alert deep-linking framework completed
- chain capability readiness reviewed against matrix

Deliverables:

- complete rekt intelligence product
- multi-chain portfolio aggregation and risk surfaces
- alert-to-portfolio integrations

Exit criteria:

- all target chains satisfy required portfolio capability matrix
- rekt context appears in token, DeFi, and portfolio risk surfaces
- portfolio alerts are correlated with holdings/exposure context

### Phase 5: Speed and Reliability Hardening

Entry criteria:

- core user journeys available end-to-end
- baseline latency and error metrics collected

Deliverables:

- precompute jobs
- cache-tier strategy completion
- provider budgets and circuit breakers
- API envelope parity
- performance tuning and SLO lock-in

Exit criteria:

- first meaningful response p95 under 5 seconds
- deep analysis completion p95 under 30 seconds
- API contract envelope compliance reaches 100% for in-scope routes

### Phase 6: Cross-Feature Intelligence Polish

Entry criteria:

- quality baselines collected for alert and signal outcomes
- observability dashboards available for key SLOs

Deliverables:

- unified insight narratives
- confidence and evidence UX refinements
- signal quality feedback loops
- end-to-end production readiness sweep

Exit criteria:

- narrative consistency across token/DeFi/smart money/portfolio pages
- adaptive heuristic downweighting enabled only after quality thresholds are met
- platform launch checklist signed off

## Observability and Measurement Definitions

To avoid ambiguous KPI reporting, each target must have a single measurement method:

- First meaningful response (<5s): measured client-side from navigation start to first non-skeleton primary content render on key routes (`/dashboard`, `/defi`, `/smart-money`, `/portfolio`) at p95 per 24h window.
- Deep analysis completion (<30s): measured server-side from analysis job accepted timestamp to completed snapshot persisted timestamp at p95 per 24h window.
- Event and alert latency (<5s high/critical): measured end-to-end from event ingest timestamp to client receive timestamp at p95 per 24h window.
- Route transitions (<1.5s): measured client-side for app-shell route changes at p95 across defined top journeys.

Required dashboards and ownership:

- Platform Delivery owns stream latency, event loss, and provider health dashboards.
- Intelligence Core owns analysis-duration and enrichment-budget dashboards.
- Product Shell owns route transition and core web vitals dashboards.
- Safety Loop owns alert precision, duplication, acknowledgement, and mute-rate dashboards.

## Success Criteria

Product-level success:

- users can discover every core feature from navigation without docs
- smart money intelligence is actionable beyond raw feed consumption
- alert pipeline delivers useful, low-noise, actionable notifications
- portfolio intelligence is truly multi-chain and risk-aware
- consistent visual quality across legacy and new pages

Performance-level success:

- first meaningful result under 5 seconds
- deep analysis under 30 seconds
- event feed under 5 seconds
- page transitions under 1.5 seconds

Reliability-level success:

- graceful degradation under partial provider failure
- consistent API contracts across route families
- end-to-end observability with trace IDs and freshness metadata

## Open Questions For Planning Stage

- Which event bus technology to standardize on for internal pub/sub?
- Which persistence model to use for alert history and user notification preferences?
- Which data source set should be canonical for wallet/entity graph bootstrapping per chain?
- Which pages should be delivered first inside each phase for earliest user-visible value?

These are planning-level decisions and should be resolved in the implementation plan.
