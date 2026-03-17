# DeFi Intelligence Overhaul Design

Date: 2026-03-17
Status: Approved for planning
Primary focus: Phase 1 core intelligence redesign for DeFi opportunity analysis

## Summary

AI Sentinel should evolve from a token-analysis-led product with a partially enriched DeFi screener into a capital allocation intelligence system. The Phase 1 objective is to help a user decide where to deploy capital across Solana and EVM DeFi opportunities with materially better usefulness, consistency, and speed.

This design combines three required directions into one layered system:

1. incremental performance and architecture upgrades
2. a stronger opportunity intelligence platform
3. an embedded AI analyst copilot

The implementation plan that follows this spec should focus on the first executable program: the core opportunity-analysis pipeline, the upgraded scoring model, the behavioral-intelligence interfaces, and the decision-ready API surface required to support them. Broader product expansion remains part of the roadmap but is not all in scope for the first implementation plan.

## Decisions Captured During Brainstorming

- Phase 1 focus: core intelligence
- Chain strategy: full multi-chain parity
- Latency target: under 30 seconds is acceptable; current multi-minute latency is not
- Existing token analysis quality is acceptable; the weak point is DeFi usefulness
- Primary user job: pick where to deploy
- Core ranking principle: evaluate the ratio of risk to APR, where both sides are composites
- Scoring philosophy: hybrid equal-weight between deterministic logic and AI judgment

## Why This Spec Exists

The repository already points in the right direction, but several important pieces are still either sequential, placeholder-heavy, or not yet productized enough for allocator-grade DeFi recommendations.

Key examples from the current codebase:

- `src/defi/opportunity_engine.py` fetches market inputs concurrently but still builds opportunities one by one, which makes deeper enrichment stack latencies instead of staying within a budget.
- `src/analytics/wallet_forensics.py` contains explicit production placeholders for deployment history, funding-chain analysis, and related-wallet discovery.
- `src/analytics/time_series.py` relies on in-memory snapshots, which prevents durable behavioral learning and makes anomaly quality unstable across restarts.
- `src/data/solana.py` includes a fallback that estimates whale activity from trending-volume heuristics, which is acceptable as a stopgap but too weak for a core decision engine.
- `src/api/middleware/rate_limit.py` and `src/api/routes/auth.py` have ordering and state-model issues that reduce reliability for authenticated traffic.

The result is a product that can look promising but is not yet structured to answer the most important DeFi question with enough rigor: should a user deploy capital here, and why?

## Goals

- Cut DeFi opportunity analysis latency from multi-minute behavior to a reliable sub-30-second workflow.
- Turn DeFi outputs into decision-ready recommendations rather than generic rankings.
- Preserve and extend deterministic scoring while elevating AI to a first-class analytical partner.
- Support Solana and major EVM chains through a common model with chain-specific adapters.
- Make whale, smart-money, and anomaly signals directly relevant to opportunity ranking.
- Expose a clean `OpportunityAnalysis` contract that both the API and web product can consume.
- Build evidence, freshness, and confidence into every score so the system can degrade honestly.

## Non-Goals For The First Implementation Plan

- Full portfolio-construction and rebalancing automation
- Personalized allocator profiles beyond minimal ranking-profile support already present
- Full watchlist, alerting, and monitoring product completion
- Every future DeFi archetype at once; the initial pass should prioritize LP, farm, lending, and vault-like surfaces
- Complete replacement of all token-analysis systems unrelated to DeFi ranking

## Design Principles

- Model opportunities as deployment theses, not just pools or markets.
- Separate fact collection, normalization, deterministic scoring, AI judgment, and user-facing assembly.
- Spend expensive work only on the top candidates.
- Treat confidence and freshness as ranking inputs, not decorative metadata.
- Use hard caps for unacceptable conditions; do not let AI override them.
- Keep chain-specific collection adapters behind a shared intelligence contract.
- Prefer durable evidence stores over process-local memory.

## Product Shape

The core object is an `OpportunityAnalysis`. It represents a deployable thesis and includes:

- what the opportunity is
- why it ranks where it does
- what evidence supports the recommendation
- what can break the thesis
- what conditions would upgrade or downgrade the recommendation

Each opportunity is built from three layers:

1. market truth: deterministic facts and normalized evidence
2. intelligence judgment: AI synthesis over the same evidence bundle
3. execution usability: deploy, watch, avoid, or deploy-small style outputs with reasons

## Scope Decomposition

The larger product effort naturally splits into multiple tracks:

- core intelligence
- product UX
- API and platform reliability
- growth and monitoring

This spec is for the first track: the core intelligence overhaul, with only the API and UX changes that are necessary to expose the new opportunity-analysis model. Full downstream UX expansion and monitoring remain follow-on phases.

## Architecture Overview

The DeFi engine should become a three-pass pipeline.

### Pass 1: Market Scan

Purpose:

- gather a broad cross-chain market universe quickly
- normalize pools, farms, lending markets, and related opportunity shapes
- compute a cheap first-pass deterministic score for all candidates

Inputs:

- DefiLlama and other normalized market sources
- existing protocol catalog and protocol metadata
- existing chain, token, and protocol reference data

Outputs:

- a ranked candidate set with cheap summary scores
- enough metadata to decide which candidates deserve deeper work

Constraints:

- must stay fast
- must not trigger expensive docs, AI, history, or deep wallet analysis for the full universe

### Pass 2: Selective Enrichment

Purpose:

- enrich only the top candidate band
- collect deeper evidence on protocols, positions, dependencies, and capital behavior

Evidence collected here should include:

- protocol docs and governance posture
- audits and incident history
- dependency graphs and inherited risk
- asset-quality data and reward-token quality
- historical APR and TVL behavior
- exit-path and liquidity-depth signals
- smart-money and whale-behavior summaries
- anomaly and fragility signals

Execution model:

- bounded concurrency per provider, per chain, and per evidence family
- request coalescing so overlapping user requests share work
- stage-level time budgets so slow sources reduce confidence instead of blocking the analysis

### Pass 3: Decision Synthesis

Purpose:

- assemble the final `OpportunityAnalysis`
- compute deterministic and AI scores
- apply hard caps, confidence gating, and recommendation rules
- return a decision-ready explanation

Outputs per opportunity:

- deterministic score bundle
- AI judgment bundle
- final deployability score
- risk-to-APR ratio outputs
- scenario set
- confidence report
- evidence trace
- final recommendation and explanation

## OpportunityAnalysis Contract

Each opportunity should expose a stable contract with these top-level sections:

- `identity`: id, chain, protocol, kind, category, assets, strategy family
- `market`: TVL, APR split, liquidity, utilization, volumes, relevant raw facts
- `scores`: deterministic, AI, final deployability, safety, APR quality, exit quality, resilience, confidence
- `factors`: normalized factor tree with evidence and freshness
- `behavior`: whale, smart-money, insider, concentration, stickiness, anomaly, and flow-quality signals
- `scenarios`: what improves, what breaks, and what to monitor
- `recommendation`: deploy, deploy-small, watch, avoid, plus rationale
- `evidence`: sources, freshness, gaps, and fallback markers

## Advanced Factor System

The scoring engine should move from a mostly generic DeFi scorecard to archetype-aware factor models.

Initial archetypes:

- LP and AMM
- single-sided farm
- lending supply
- lending borrow or loop
- vault and auto-compounder
- stable strategy

Cross-cutting top-level pillars:

### 1. Protocol Integrity

- audit depth and freshness
- upgradeability and proxy risk
- admin-key power, timelocks, and multisig quality
- bug-bounty presence
- incident history with time decay and recurrence weighting
- codebase and deployment maturity
- governance attack surface
- dependency count and dependency criticality

### 2. Market Structure

- TVL size and stability
- liquidity concentration
- utilization stability
- borrow-cap and supply-cap saturation
- oracle robustness
- depth at realistic position sizes
- cross-chain fragmentation

### 3. APR Quality

- base-yield versus incentive-yield split
- reward-token quality
- emissions durability
- treasury runway supporting incentives
- expected APR decay
- extractability after fees, slippage, and rebalance drag

### 4. Position Risk

- impermanent-loss path risk
- collateral volatility and correlation
- liquidation cascade risk
- looping or rehypothecation complexity
- stablecoin depeg risk
- weak-leg concentration

### 5. Exit Quality

- unwind depth at realistic notional sizes
- withdrawal queue, lock, or cooldown risk
- slippage-to-exit
- emergency-exit options
- bridge dependency during exit
- liquidity disappearance risk under stress

### 6. Behavioral Intelligence

- smart-money entering versus leaving
- whale concentration and flow direction
- mercenary-farming likelihood
- insider or deployer-linked participation
- sudden APR moves without structural support
- capital stickiness versus tourist liquidity

### 7. Chain And Infrastructure Risk

- chain liveness and congestion
- bridge exposure
- sequencer or validator concentration
- RPC, indexer, and oracle dependency fragility
- ecosystem contagion risk by chain

Each factor must carry:

- raw measurement
- normalized score
- confidence
- evidence source
- freshness or time decay
- scenario sensitivity
- optional hard-cap effect

## Hybrid Scoring Model

The system should produce two independent judgments for every opportunity.

### Deterministic Score

Derived from explicit factor models, hard caps, and confidence rules. This remains the system of record for unacceptable conditions.

### AI Judgment Score

Derived from a constrained AI review of the same evidence bundle. The AI should answer:

- would a skilled allocator deploy here?
- what risks are underpriced by the visible APR?
- which metrics provide fake comfort?
- what breaks the thesis first?

### Final Ranking Rule

- final deployability score = 50 percent deterministic + 50 percent AI judgment
- AI influence is gated by evidence quality
- deterministic hard caps cannot be bypassed by AI optimism

The user-facing score should be accompanied by these outputs:

- gross APR
- haircut APR
- net expected APR
- weighted risk burden
- risk-to-APR ratio
- fragility flags
- kill switches that invalidate the thesis
- best-fit risk profile
- confidence reasoning

## Behavioral Intelligence Layer

Whale analysis should evolve from raw large-transaction tracking into an entity-aware behavior system.

Core graph objects:

- wallet
- wallet cluster
- deployer or operator
- LP provider
- farmer
- treasury
- market maker
- bridge source or sink
- suspicious or exploiter-linked cluster

Behavior classes:

- smart accumulator
- smart distributor
- mercenary emissions farmer
- sticky liquidity
- tourist capital
- protocol-aligned treasury flow
- insider-linked flow
- exit-liquidity seeker

Opportunity-facing behavioral outputs:

- capital quality score
- stickiness score
- dump-risk score
- insider-exposure score
- mercenary-farming score
- whale-alignment score
- what changed in the last 24 hours that matters

The Solana and EVM stacks should share a common behavior interface while using separate collection adapters.

## Speed Strategy

The main speed improvement should come from removing expensive work from the user-critical path.

Three timing classes:

### Offline Continuously Maintained

- docs analysis
- audits and incidents
- dependency graph materialization
- historical APR and TVL snapshots
- entity labels and wallet clustering outputs
- chain-health and protocol-health baselines

### Warm Query Support

- normalized market snapshots
- precomputed cheap factors
- recent opportunity summaries
- shared caches and shared evidence bundles

### Live Query Only

- top-candidate refresh
- missing-evidence fill
- final scoring and final explanation assembly

Target user experience:

- sub-5-second provisional shortlist
- sub-20-second enriched shortlist
- sub-30-second final analyst-grade result

## API Surface Required For Phase 1

The API should converge on decision-ready opportunity resources.

Required surfaces:

- `GET /opportunities`
- `GET /opportunities/{id}`
- `POST /opportunities/compare`
- `GET /protocols/{slug}`
- `GET /entities/{wallet_or_cluster}`
- `POST /positions/analyze`
- `GET /signals`

The payloads should be progressive-delivery friendly. A user should be able to receive a provisional result quickly, then poll or stream deeper enrichment updates using an analysis identifier.

## Product Surface Required For Phase 1

The frontend only needs the minimal surfaces necessary to expose the new intelligence model well:

- Discover: ranked opportunity radar
- Investigate: opportunity detail page
- Compare: side-by-side opportunity comparison

Monitoring, watchlists, score-change alerts, and broader AI-copilot product expansion remain follow-on work.

The AI analyst should be embedded into opportunity and compare views instead of being treated as a detached novelty surface.

## Reliability And Observability

Every analysis should capture:

- total latency
- per-stage latency
- per-provider latency and failure rate
- cache hit rates
- enrichment coverage
- AI runtime and cost
- score version and factor-model version
- reason for rank changes between runs

Every evidence point should record whether it came from:

- live source
- warm cache
- durable snapshot
- heuristic fallback
- unavailable data

The system should degrade by lowering confidence and narrowing claims instead of silently pretending nothing is missing.

## Testing And Calibration

The first implementation plan should establish:

- unit tests for factor calculators, hard caps, confidence math, and archetype rules
- fixture tests for representative Solana and EVM opportunities
- regression tests for known strong and weak opportunity patterns
- property tests for ranking invariants
- contract tests for provider normalization
- golden tests for AI explanation grounding

Backtesting and replay should become part of calibration so the system can evaluate how it would have ranked historical opportunities before drawdowns, emissions cliffs, or exploit-driven collapses.

## Roadmap

### Phase 1: Speed And Core Architecture

- refactor the opportunity engine into the three-pass pipeline
- create durable evidence and cache layers
- normalize opportunity schemas across supported chains
- add provisional ranking, enrichment budgets, and request coalescing
- fix API middleware ordering and authenticated rate-limit behavior

### Phase 2: Advanced Deployability Engine

- implement archetype-specific factor models
- add APR haircut math, expected decay, exit simulation, and scenario-aware outputs
- formalize deterministic plus AI equal-weight ranking

### Phase 3: Behavioral Intelligence Moat

- implement entity graph, clustering, behavior classes, and protocol memory
- make whales and anomalies ranking factors rather than side feeds
- persist time-series data durably

### Phase 4: Product Reshape

- rebuild the DeFi surface around Discover, Investigate, and Compare
- embed the analyst copilot into these flows
- add the first monitoring hooks needed for saved opportunities

### Phase 5: Calibration And Trust Layer

- version score models
- shadow-run new models
- add ranking-drift detection and replay-based evaluation

### Later Expansion

- personalized allocator modes
- position-monitoring and exit alerts
- portfolio-aware recommendations
- strategy bundles and allocator-memory features

## Planning Boundary

The implementation plan created from this spec should focus on:

- Phase 1 in full
- the architecture and interfaces needed to unlock Phase 2
- only the minimum product and API surface required to expose the new intelligence model cleanly

The first implementation plan should not attempt to complete the entire long-term roadmap in one pass.

## Acceptance Criteria For This Design

This design is successful if the resulting implementation plan can produce a system that:

- returns useful DeFi opportunity analyses in under 30 seconds
- ranks opportunities using a richer risk-to-APR decision model
- combines deterministic and AI reasoning without letting AI bypass hard caps
- treats whale, anomaly, and entity intelligence as ranking inputs
- exposes a stable `OpportunityAnalysis` contract to both API and frontend clients
- degrades honestly when evidence is missing or stale

## Notes For Planning

- Existing files such as `src/defi/opportunity_engine.py`, `src/defi/risk_engine.py`, `src/analytics/wallet_forensics.py`, `src/analytics/time_series.py`, `src/data/solana.py`, and the DeFi web surfaces should be treated as starting points, not final forms.
- The existing `docs/defi-intelligence-roadmap.md` remains useful background but this spec supersedes it as the planning reference for the next major DeFi intelligence iteration.
