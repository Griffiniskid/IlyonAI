# Agent Platform — Full Project Description

## 1. Project Concept

Agent Platform is an AI-powered crypto wallet assistant built around one main idea:

- the user should be able to ask for crypto actions and information in natural language
- the system should understand the request, gather data, and either answer it directly or prepare a transaction the wallet can sign
- the same product should work across two wallet ecosystems:
  - EVM wallets, primarily MetaMask
  - Phantom, with both Solana and Phantom EVM contexts

The product is not just a chatbot and not just a wallet dashboard. It is a hybrid system with three layers working together:

- a conversational AI interface for intent capture
- a structured backend tool layer for balances, prices, swaps, bridges, liquidity, and staking
- a frontend transaction-preview and wallet-execution layer

In practical terms, the product tries to turn prompts like these into useful output:

- `my balance`
- `swap 0.2 sol to usdc`
- `bridge 0.2 sol to bnb chain`
- `give me liquidity pools with highest apr for sol/usdc`
- `find a pool for usdc/usdt`
- `stake bnb`
- `give me a link to protocol where i can stake bnb`

The system combines informational and transactional flows in a single interface. Some requests return data cards. Some return transaction previews. Some return links to external protocols.

## 2. High-Level Product Surfaces

The project currently has four visible product surfaces:

- the main web app
- a browser-extension popup UI
- a browser-extension side panel UI
- the backend API and agent system that powers all of them

The main product experience today lives in the web app.

## 3. Main App Structure

The web app is organized around four top-level tabs:

- `Home`
- `AI Chat`
- `Portfolio`
- `Swap`

There is also:

- a landing/intro experience shown before entering the full app
- an auth modal for wallet connection
- a persistent sidebar
- a saved-chats panel for authenticated users

The application is visually positioned as a premium crypto control center: dark theme, gold accent, motion-heavy, card-driven, and intentionally shaped around DeFi and wallet actions.

## 4. Page-by-Page Description

### 4.1 Landing / Intro Experience

The intro screen acts like a product-marketing shell layered on top of the application.

It includes:

- a top navigation strip
- a hero section with positioning copy
- a stat row that frames the product as a live crypto control center
- feature cards that explain what the assistant can do
- a “how it works” section
- an integrations or ecosystem section
- a CTA to launch/connect

Purpose:

- introduce the product value before requiring wallet connection
- visually frame the product as a sophisticated DeFi assistant, not a raw admin tool
- reduce the abruptness of entering a dense application shell immediately

### 4.2 Sidebar

The sidebar is a permanent navigation and state-summary rail.

It contains:

- brand block with product name and chain/assistant subtitle
- connected wallet card
- market watchlist cards
- Greenfield memory status section
- current user identity block
- new chat and chat history controls
- backend online indicator
- sign out control

Purpose:

- keep wallet and environment state visible at all times
- give users persistent access to the current session identity and market context
- make chat creation and chat switching fast

### 4.3 Home Tab

The Home tab acts like a dashboard and product overview.

It includes:

- headline/title copy
- platform stat cards
- market overview cards
- quick action shortcuts
- feature summary cards
- wallet connection CTA or connected-wallet success state

Purpose:

- provide a non-conversational entry point into the product
- make the system discoverable for new users
- allow fast jumping into common actions

This is not a raw analytics dashboard. It is a guided launch surface into the rest of the product.

### 4.4 AI Chat Tab

This is the core surface of the entire platform.

It includes:

- chat header with context and chat controls
- first-use capability cards when conversation is empty
- a conversation feed
- message rendering in multiple modes
- reasoning accordion under assistant messages
- quick prompt chips above the composer
- textarea composer with Enter-to-send behavior

This page is responsible for almost all of the product’s power.

The user can ask for:

- price information
- wallet balance information
- portfolio questions
- pool discovery
- APR/APY analysis
- swaps
- staking
- transfers
- bridging
- liquidity actions

The AI Chat page is also where prepared transactions are reviewed and signed.

### 4.5 Portfolio Tab

The Portfolio tab is a multi-chain wallet overview page.

It includes:

- summary cards for total balance, native token price, token count
- unit toggle between USD and native denomination
- refresh button
- error banner area
- empty state when no wallet is connected
- token table showing symbol, price, balance, value, and chain

Purpose:

- give users a consolidated portfolio view without needing to ask in chat
- support both EVM and Phantom dual-context scanning
- show a usable overview of known assets across supported chains

Important caveat:

- the page shows known/scannable assets, not a universal perfect inventory of every token in existence

### 4.6 Swap Tab

The Swap tab is a guided pre-composer, not the full swap engine.

It includes:

- amount input
- from token and to token selection via simple input state
- reverse-direction button
- quick pair buttons
- wallet connection CTA if disconnected
- inline estimated result text

Purpose:

- help users express a trade quickly without needing to type a perfect natural-language request
- hand the final execution off into chat, where the full backend routing and tx preview system operates

So this tab is a UX accelerator, not a complete standalone DEX app.

## 5. Main User-Facing Features

### 5.1 Wallet Connection and Authentication

Supported wallet types:

- MetaMask
- Phantom

#### MetaMask flow

- resolves the real MetaMask provider even if multiple EVM providers exist
- can switch the user to BNB Chain during setup
- signs a backend auth challenge
- stores a JWT for authenticated actions like chat persistence

#### Phantom flow

- connects the Solana wallet
- optionally reads Phantom EVM context as well
- attempts Solana-message authentication
- can fall back to guest mode if signing/auth fails

Current product meaning:

- Phantom users can operate with Solana actions and Phantom EVM actions
- MetaMask users operate through the EVM route only

### 5.2 AI Conversational Agent

The AI agent is the orchestration layer of the product.

It receives:

- query text
- session ID
- chat ID
- wallet addresses
- chain context
- wallet type

Then it does one of two things:

- handles the request with a deterministic shortcut when possible
- otherwise invokes the broader tool-using agent flow

This distinction matters because several reliability improvements in the project come from bypassing the LLM for fragile intent categories.

### 5.3 Deterministic Shortcuts

The backend currently contains direct fast-path handling for several user intents.

These exist so that the system does not rely entirely on model reasoning for high-risk or highly structured actions.

Current deterministic categories include:

- direct swap parsing for common swap prompts
- direct bridge parsing for common bridge prompts
- direct staking-info queries
- direct staking transaction prompts
- direct APR/APY pool search prompts
- direct LP deposit prompts
- direct pool lookup prompts

Purpose:

- reduce hallucinations
- reduce routing mistakes
- make common actions faster
- ensure wallet-specific behavior is handled correctly

### 5.4 Balance Lookup

Users can ask for wallet balances in chat, and the system can also show balances in the Portfolio tab.

Behavior:

- scans one or more wallet addresses
- aggregates balances by chain
- includes chain-native balances and supported tokens
- returns a structured `balance_report`

For Phantom users, the current system can combine:

- Solana address
- Phantom EVM address

so both sides of the wallet are represented.

### 5.5 Portfolio Aggregation

The portfolio endpoint powers the Portfolio tab and balance-related chat features.

Current behavior:

- scans supported chains via RPCs
- converts results into frontend-ready token rows
- computes total USD values where pricing is known
- merges multi-address wallet contexts when needed

This makes the portfolio page a presentation layer over the shared scan system rather than a totally separate data source.

### 5.6 Price and Market Data

The product exposes token pricing in multiple ways:

- visual market cards in the sidebar/dashboard
- scrolling ticker in the main area
- chat responses for token prices
- swap estimation support

Frontend market presentation is lightweight and visually focused.
Backend token pricing is utility-focused and used by agent features.

### 5.7 Swaps

The platform supports both EVM and Solana swaps.

#### EVM swaps

- built through Enso
- produce structured ready-to-sign EVM transaction payloads
- support explicit amount and `all`
- rendered through a shared transaction preview card

#### Solana swaps

- built through Jupiter
- produce base64 serialized VersionedTransaction payloads
- executed in Phantom Solana

Swap flows are surfaced in two ways:

- typed naturally in chat
- started from the Swap tab and handed into chat

### 5.8 Cross-Chain Bridging

Bridging is powered through deBridge DLN.

Current bridge system supports:

- transaction preparation
- bridge preview rendering
- source-chain intermediary explanation when relevant
- post-submission order status polling

Bridge UX includes:

- source token and destination token
- requested amount
- actual source-chain spend if deBridge prepends operating expenses
- source-side intermediary execution explanation
- warnings
- order ID
- estimated fill time
- destination chain info

The platform now includes deterministic bridge parsing so prompts like:

- `bridge 0.2 sol to eth chain`
- `bridge 0.2 sol to bnb chain`

are not dependent on the LLM guessing source/destination chain IDs correctly.

### 5.9 Staking

Two separate staking experiences exist.

#### Informational staking

- returns supported staking protocols
- returns direct links to the real protocol pages
- used for prompts like `where can i stake bnb`

#### Transactional staking

- builds stake transactions for supported native assets

Currently supported native staking assets are intentionally narrow:

- ETH
- BNB
- MATIC

This is not universal staking support for arbitrary tokens.

### 5.10 Liquidity and Pool Discovery

The platform supports several liquidity-related behaviors.

#### Yield / APR / APY analytics

- searches pools via DefiLlama-based analytics logic
- returns structured cards
- filters, confidence labels, APY display, deep links, pool addresses where available

#### Pool lookup

- tries to find a specific pool / pair address
- often uses DexScreener-style data

#### LP deposit transaction building

- for supported flows, can build a deposit transaction
- for unsupported flows, may fall back to giving a protocol/pool link

### 5.11 Token / Pair Discovery

The agent can search token pairs, memecoins, or contract addresses using DexScreener-backed search.

Purpose:

- resolve assets before transactions
- find liquidity locations
- support “unknown token” discovery flows

### 5.12 Transfers

The system includes transfer transaction building for token/native sends.

This includes:

- transfer preview card
- recipient display
- chain-aware execution

### 5.13 Saved Chats

Authenticated users get:

- chat creation
- chat listing
- chat loading
- renaming
- deletion

This gives the AI chat product persistence and repeatability instead of making each session disposable.

## 6. Extension Surfaces

Beyond the main app, the repo also contains browser-extension surfaces.

### 6.1 Popup

The popup is a compact wallet/control panel UI.

It includes:

- header and network badge
- wallet card
- token list
- quick actions
- compact status-driven crypto assistant framing

This appears to be a lighter secondary surface rather than the primary feature-complete interface.

### 6.2 Side Panel

The side panel is a simplified conversational layout for browser-extension use.

It includes:

- header
- portfolio strip
- chat feed
- quick buttons
- input area

This is conceptually a browser-native mini-assistant shell.

### 6.3 Background Worker

The extension background worker currently handles:

- install lifecycle
- side panel behavior on action click
- basic message routing
- placeholder alarm handling

It is infrastructure for the extension shell rather than a major user-facing feature set yet.

## 7. Backend Architecture in Product Terms

The backend is a FastAPI application that exposes:

- `/api/v1/agent`
- auth endpoints
- chat endpoints
- portfolio endpoint
- bridge status endpoint
- RPC proxy

The agent endpoint is the central orchestration surface.

The backend system mixes:

- direct deterministic logic
- external protocol integrations
- AI-tool orchestration
- persistence for chats/auth

The product therefore behaves more like a task broker than a simple CRUD API.

## 8. Wallet-Specific Product Behavior

### 8.1 MetaMask

MetaMask is the most straightforward EVM path.

It is strongest for:

- EVM swaps
- EVM staking
- EVM transfers
- EVM LP actions
- EVM bridges
- authenticated saved-chat experience

### 8.2 Phantom

Phantom is a dual-context wallet in this product.

It can contribute:

- Solana signing
- Phantom EVM signing
- Solana portfolio state
- EVM portfolio state

The recent parity work improved:

- clean structured Phantom wallet state
- proper Solana query routing
- proper Phantom EVM execution for EVM actions
- proper Solana/EVM combined portfolio scanning
- fixed Solana APR pool search behavior
- fixed deterministic bridge parsing

## 9. Important Current Limitations

The system is feature-rich, but not universal.

Current important limits include:

- no dedicated standalone bridge/staking/liquidity tabs; those remain chat-driven
- staking support is intentionally narrow
- LP deposit support depends on the ability to resolve a usable protocol/pool route
- some unsupported actions are intentionally excluded, like arbitrary contract interaction, unstaking, reward-claiming, or remove-liquidity flows
- portfolio scanning is broad but not equal to a fully indexed wallet intelligence product
- the app is heavily local-dev oriented in several frontend/backend URL assumptions
- some extension surfaces are lighter-weight than the main app

## 10. Current Product Philosophy

The current conception of the project is:

- conversational first
- transaction-capable, not just informational
- multi-wallet, multi-chain, multi-paradigm
- card-based and preview-based rather than raw JSON-driven
- reliability improved through selective deterministic routing

In other words, the project is trying to behave like a crypto operating assistant:

- part wallet dashboard
- part AI analyst
- part DeFi transaction router
- part protocol discovery layer

## 11. Feature Summary Matrix

### Informational features

- landing and product explainer
- dashboard stats and market overviews
- prices
- balances
- portfolio view
- APR/APY analytics
- staking protocol links
- pool discovery
- token/pair discovery
- chat history

### Transactional features

- wallet auth signing
- EVM swaps
- Solana swaps
- bridges
- stake transaction building
- LP deposit transaction building
- transfers

### Hybrid features

- chat itself
- structured transaction previews
- bridge status polling
- pool cards with direct protocol links

## 12. Suggested Reading Inside This Repo

If someone wants to understand the actual implementation after reading this document, the most important files are:

- `client/src/MainApp.tsx`
- `client/src/wallets/metamask.ts`
- `client/src/wallets/phantom.ts`
- `server/app/api/endpoints.py`
- `server/app/agents/crypto_agent.py`
- `server/app/api/portfolio.py`
- `server/app/api/auth.py`
- `server/app/api/chats.py`
