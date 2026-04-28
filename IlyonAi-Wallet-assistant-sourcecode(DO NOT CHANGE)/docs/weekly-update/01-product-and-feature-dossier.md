# Product And Feature Dossier

## 1. Repository Role Inside The Larger Project

This repository should be understood as a specialized extension to the main project, not the entire product.

Its role is to add a new AI-native crypto interaction layer with these major themes:

- natural-language DeFi interaction
- wallet-connected transaction preparation
- multi-chain balance visibility
- browser-extension access points
- cross-ecosystem support for EVM and Solana users
- new monetization and protocol-integration groundwork through affiliate routing and fee-aware execution

In weekly-update language, the safest framing is:

- the core project continues elsewhere
- this module adds a new conversational DeFi operating layer
- this module is both a user-facing feature set and a technical integration layer

## 2. Product Vision In Plain Language

The core idea is simple:

- a user should be able to ask for crypto information or actions in plain language
- the system should translate that request into either a useful answer, a protocol recommendation, or a ready-to-sign transaction preview
- the product should work across both EVM and Solana-adjacent wallet contexts without forcing the user into separate tools

This makes the product neither a normal chatbot nor a normal wallet dashboard.

It is closer to an AI DeFi control room.

## 3. Primary User Problems This Module Solves

This repository tries to solve these specific pain points:

- users do not want to manually navigate multiple DeFi interfaces for simple actions
- users do not want to translate intent into protocol-specific transaction steps by hand
- users want balance, price, and execution context in one place
- users want wallet execution to remain non-custodial while still getting AI help
- users want cross-chain and cross-wallet flows to feel coherent instead of fragmented

## 4. Main Product Surfaces

This repository contains six meaningful product surfaces.

### 4.1 Main Web App

This is the flagship experience.

It is a full React application with:

- an intro / landing experience
- an authentication modal
- a persistent sidebar
- a market ticker
- four main tabs: Home, AI Chat, Portfolio, Swap
- wallet-aware transaction previews
- chat persistence for authenticated users

This is where the project feels most complete.

### 4.2 Browser Extension Popup

This exists, but it is still mostly a lightweight shell.

It currently behaves more like a designed placeholder than a fully wired feature surface.

It shows:

- branding
- backend status
- mock token cards
- quick action buttons
- a connect-wallet presentation state

It does not yet behave like the full app.

### 4.3 Browser Extension Sidepanel

This is more real than the popup, but still much smaller than the main app.

It supports:

- a minimal chat interface
- quick prompt chips
- a backend online/offline indicator
- a local wallet-address readout
- message sending to the backend agent

It does not currently render the advanced structured cards and execution previews that the main app supports.

### 4.4 Background Worker

The extension also has a Manifest V3 background service worker.

Today it mainly covers:

- install-time setup
- sidepanel opening behavior
- alarm hooks
- minimal internal message routing

This is infrastructure groundwork more than a finished feature layer.

### 4.5 Backend API And AI Orchestration Layer

This is the engine behind the UI.

It provides:

- authentication
- chat storage
- AI request routing
- portfolio scanning
- bridge-status polling
- low-level RPC proxying

The backend is where the system becomes more than a front-end prototype.

### 4.6 Smart Contract Track

There is also a separate smart-contract feature track in this repository.

That track introduces:

- an affiliate-aware PancakeSwap Infinity / V4-style hook
- dynamic LP fee changes for affiliate trades
- distributor-fee accounting and distribution
- a deployment script for creating a dynamic-fee pool with hook permissions attached

This contract work is important because it shows the product is not only consuming DeFi protocols, but also trying to shape protocol-level monetization behavior.

## 5. Main Application Experience

## 5.1 Entry Flow

The first major surface is an intro / landing experience.

It is not a bare splash screen. It behaves like a product pitch layered on top of the app.

It includes:

- hero copy
- stat blocks
- feature cards
- how-it-works messaging
- partner / integration references
- launch or sign-in calls to action

Conceptually, this screen does three jobs:

- it explains the product before the user connects a wallet
- it frames the app as a premium AI DeFi interface rather than a raw tool
- it softens the transition into a dense dashboard/chat workspace

## 5.2 Authentication Experience

Authentication is wallet-first.

The user chooses between:

- MetaMask
- Phantom

There is intentionally no traditional identity-heavy onboarding on the main path.

The message is clear:

- your wallet is your identity
- signing is used for access control
- the app stays non-custodial

### MetaMask path

The MetaMask flow is designed for EVM-first users.

What it does:

- finds the real MetaMask provider even if another wallet has injected an EVM provider
- requests account access
- attempts to switch the user to BNB Smart Chain by default
- generates a sign-in message with a timestamp
- sends the signed payload to the backend for JWT issuance
- stores the returned token and wallet context locally

Practical product meaning:

- MetaMask users get authenticated chat persistence
- MetaMask users become BNB-first by default
- EVM execution is the standard path for them

### Phantom path

The Phantom flow is more nuanced because the product treats Phantom as both:

- a Solana wallet
- a potential EVM provider through Phantom Ethereum

What it does:

- connects the Solana wallet first
- optionally fetches Phantom's EVM address and EVM chain
- optionally requests a Solana sign-in signature for backend auth
- stores a structured wallet context locally
- falls back to guest mode if the sign-in flow fails

Practical product meaning:

- Phantom users can still use the app even if backend auth is unavailable
- Phantom users are represented primarily by the Solana address in the UI
- Phantom users can trigger both Solana-native and Phantom-EVM-aware flows depending on the request

## 5.3 Sidebar As Persistent Control Rail

The main app has a persistent sidebar that acts like a live environment panel.

It contains:

- brand identity block
- wallet connection state
- a small market watchlist
- a Greenfield memory status strip
- authenticated user details
- new-chat and chat-history controls
- backend online/offline status
- sign-out or about button

This matters conceptually because the app does not treat chat as an isolated page.

Instead, it keeps environment, identity, and market context visible all the time.

## 5.4 Market Ticker And Ambient Live Context

Across the top of the main content area the app shows a continuously moving market ticker.

It displays tokens such as:

- BNB
- ETH
- BTC
- CAKE
- USDT
- SOL
- ARB
- OP

Its job is not deep analysis.

Its job is to make the application feel connected to live market conditions even when the user is elsewhere in the interface.

## 6. The Four Primary Tabs

## 6.1 Home Tab

The Home tab is a guided dashboard rather than a pure analytics screen.

It includes:

- welcome copy
- platform stat cards
- market overview cards with click-to-ask behavior
- quick-action cards
- platform feature cards
- wallet-connection CTA

This tab is important because it gives first-time users a way into the product without forcing them to invent their first prompt.

## 6.2 AI Chat Tab

This is the core of the whole module.

The chat tab is where the system becomes an AI operating layer instead of just a dashboard.

It supports:

- free-form natural-language prompts
- quick prompt chips
- first-use capability cards
- saved chat threads for authenticated users
- inline structured response rendering
- live reasoning-step animation while a response is being prepared
- confirmation-oriented transaction previews

This page can return several different kinds of output.

### Plain informational responses

Examples:

- token price information
- macro DeFi overviews
- normal chat answers

### Balance reports

The backend can return a structured balance payload and the frontend renders it as a dedicated balance card.

This lets the AI respond with a wallet report instead of a plain paragraph.

### Liquidity-pool result cards

When the user asks for a pool, a pair address, or a yield opportunity, the system can render a dedicated liquidity-pool card with:

- DEX identity
- chain
- liquidity
- volume
- APR / APY information when available
- protocol and explorer links

### Universal cards

The backend can also return a more generic card format for things like:

- staking options
- token or pair search results
- lists of actionable protocol links

### Transaction previews

This is one of the defining features of the repository.

The assistant can return structured transaction previews for:

- EVM swaps
- Solana swaps
- bridges
- token transfers
- staking transactions
- liquidity-add / LP deposit actions

The UI does not auto-submit those transactions.

Instead, it renders them as review-first previews that the user confirms with the wallet.

## 6.3 Portfolio Tab

The Portfolio tab gives a direct, non-conversational portfolio view.

It includes:

- total balance card
- native asset price card
- token count card
- unit toggle between USD and native denomination
- refresh button
- wallet-empty state
- token table with per-chain labeling

This tab is significant because it turns the app from a pure conversational experience into a hybrid conversational-and-dashboard product.

The portfolio feature is particularly important for Phantom users because it can combine Solana and EVM context into one request path.

## 6.4 Swap Tab

The Swap tab is intentionally not the final execution engine.

It is a guided swap composer.

It includes:

- amount input
- from-token and to-token state
- direction swap button
- quick pair presets
- estimated output amount
- estimated rate
- routing engine labels
- execution notes

Its role is:

- help users formulate the trade
- show a lightweight quote feel
- then hand off execution into the chat flow

That handoff is important. The chat remains the final control room.

## 7. Core User Capabilities

The repository currently expresses these major user-facing capabilities.

## 7.1 Balance And Portfolio Awareness

The user can:

- ask for balances in chat
- open the Portfolio tab for a direct view
- scan across multiple EVM chains and Solana
- view balances in either USD or native denomination

The system is not aiming to be a perfect universal wallet indexer for every possible token.

It is a practical multi-chain scan of known and discoverable assets with a focus on useful holdings.

## 7.2 Price And Market Awareness

The user can:

- ask for live token prices
- see token pricing in the market cards and ticker
- get market-oriented prompts from the dashboard
- ask for broad DeFi market-state information

The product therefore mixes personal portfolio context with external market context.

## 7.3 Same-Chain Swap Preparation

The user can request swaps in natural language.

Examples of the intended behavior include:

- "swap 0.01 BNB to USDT"
- "swap all BNB to USDT"
- "swap SOL to USDC"

The system then:

- identifies the chain context
- identifies whether the request should go EVM or Solana
- builds a structured route result
- shows approval requirements if necessary
- renders a preview for signing

The main product value here is that the user does not need to manually navigate router UIs or compose parameters by hand.

## 7.4 Cross-Chain Bridge Preparation

The system can also handle bridge-style intent.

Examples:

- "bridge 0.2 SOL to BNB Chain"
- "bridge USDC from Ethereum to Arbitrum"

The bridge flow is notable because it handles:

- source chain parsing
- destination chain parsing
- source token and requested amount
- bridge-specific preview metadata
- order-status polling after execution
- Solana-source edge cases

This is one of the strongest differentiators in the codebase because it moves beyond same-chain swapping into cross-chain intent execution.

## 7.5 Staking Discovery And Staking Execution

The repository supports two different staking modes.

### Informational staking mode

The user can ask:

- where can I stake BNB
- give me a staking link for ETH
- what staking protocols are supported

The system returns structured protocol cards rather than a transaction.

### Transactional staking mode

The user can also ask to stake a supported native asset directly.

The backend can build staking transaction proposals for supported combinations such as:

- ETH staking
- BNB staking
- MATIC staking

This split between informational and transactional staking is important because it reduces confusion between "show me options" and "prepare a transaction".

## 7.6 Liquidity And Yield Discovery

The repository has a strong discovery-oriented DeFi layer.

The user can ask for:

- best APR pools
- best APY pools
- pool addresses
- pair lookups
- protocol opportunities for a token pair

The system tries to answer with trustworthy, actionable information rather than vague commentary.

That includes:

- verified pool preference
- explicit APY vs APR separation
- pool-address resolution
- protocol and explorer links

## 7.7 LP Deposit Preparation

Once a pool is found, the system can also build a deposit / add-liquidity style action.

This means the project is not only a discovery tool. It is trying to connect:

- finding the opportunity
- understanding it
- acting on it

## 7.8 Token Transfer Preparation

The assistant can also return structured transfer transactions.

This is conceptually important because it broadens the app beyond DeFi-only actions into standard wallet utility:

- send tokens
- transfer native assets
- prepare ERC-20 transfers

## 8. Smart Query Handling And Reliability Strategy

One of the most important design decisions in this repository is that not every request is handled by a free-form LLM path.

For high-structure intents, the backend uses deterministic shortcuts.

That includes direct handling for:

- wallet balances
- common swap patterns
- common bridge patterns
- staking-link questions
- direct staking requests
- yield-search questions
- LP deposit prompts
- direct pool lookup prompts

This is conceptually valuable for the weekly update because it means the system has moved from "AI that talks about crypto" toward "AI system with deterministic reliability paths for high-risk actions".

## 9. Saved Chats And Session Continuity

Authenticated users have DB-backed chat persistence.

That means the product is not just a stateless prompt box.

The user can:

- create a new chat
- view prior chats
- reopen a prior thread
- delete a thread

The backend also keeps a short in-process conversation memory window for the AI itself.

In product terms, the app is trying to preserve both:

- user-visible conversation history
- model-visible recent context

## 10. Greenfield Memory Track

The UI presents a "Greenfield Memory" status indicator and the codebase contains a Greenfield service implementation.

That service can:

- generate off-chain auth for Greenfield storage providers
- create a private bucket per wallet
- compute Reed-Solomon checksums
- create an object on-chain
- upload a memory payload to a storage provider

This is strategically important because it points toward long-term AI memory or agent-state persistence.

However, it is not fully wired into the main app flow yet.

This should be described as a foundation or infrastructure track, not as a fully shipped user feature.

## 11. Extension Story

The repository also expands the product into browser-extension territory.

This matters conceptually because it shifts the project from:

- one web app

to:

- a multi-surface product that can live closer to the browser context

The current extension story breaks down like this:

- popup: design shell and quick-access concept, not fully wired
- sidepanel: lightweight working chat surface, still much simpler than main app
- background worker: extension lifecycle and infrastructure groundwork

So the extension work is real, but uneven in maturity.

## 12. Contract Story

The smart-contract part of the repository introduces a second strategic layer: protocol monetization.

The affiliate hook changes behavior for affiliate-labeled swaps by:

- lowering the LP fee for the affiliate path
- taking a small distributor cut from the swap input
- accumulating those fees per currency
- allowing anyone to trigger distribution to the configured distributor contract

This tells a bigger product story:

- the platform is not only a transaction UI
- it is also exploring protocol-side fee capture and affiliate economics

## 13. What Is Mature Vs What Is Still Early

### Strongest areas right now

- main React app experience
- backend AI routing and transaction-building logic
- wallet auth
- chat persistence
- portfolio scanning
- structured response rendering
- bridge, swap, staking, yield, and pool discovery flows

### Mid-maturity areas

- swap composer tab
- Phantom dual-context handling
- extension sidepanel
- affiliate-fee smart-contract track

### Early or partially implemented areas

- extension popup
- background-worker utility depth
- Greenfield memory end-to-end integration
- some public-facing marketing copy that is broader than the exact shipped implementation

## 14. Recommended Project Framing For A Weekly Update

If someone later needs to summarize this repository inside a larger weekly update, the safest conceptual framing is:

This week expanded the project with a new AI-native DeFi interaction module. The new layer combines wallet auth, saved chat sessions, multi-chain portfolio visibility, structured execution previews for swaps and bridges, staking and liquidity discovery, browser-extension surfaces, and early infrastructure for both Greenfield-backed memory and affiliate-fee protocol monetization. The web app and backend execution logic are the most mature parts today, while the extension shell, Greenfield memory activation, and some protocol-side tracks are still in active buildout.
