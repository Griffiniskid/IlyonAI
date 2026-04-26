# Technical Architecture Dossier

## 1. Repository Topology

The meaningful code in this repository is organized into three main tracks.

### 1.1 Client

Path: `client/`

Key technologies:

- React 18
- TypeScript
- Vite
- Framer Motion
- Chrome Extension Manifest V3

Main entry points:

- `client/src/main.tsx` for the full app
- `client/src/popup/main.tsx` for the popup
- `client/src/sidepanel/main.tsx` for the sidepanel
- `client/src/background/index.ts` for the background service worker

Build configuration uses multiple Vite entry points so the same frontend codebase can produce:

- a standalone web app
- a popup page
- a sidepanel page
- an extension background worker bundle

### 1.2 Server

Path: `server/`

Key technologies:

- FastAPI
- Pydantic
- SQLAlchemy
- SQLite
- LangChain
- OpenAI / OpenRouter / Groq provider support
- Web3.py
- httpx / requests

Key runtime files:

- `server/app/main.py`
- `server/app/api/*.py`
- `server/app/agents/crypto_agent.py`
- `server/app/db/*.py`
- `server/app/core/*.py`

### 1.3 Contracts

Path: `contracts/`

Key technologies:

- Solidity 0.8.26
- Foundry script flow
- PancakeSwap Infinity / V4 style hook interfaces
- OpenZeppelin Ownable and token helpers

Main files:

- `contracts/AffiliateHook.sol`
- `contracts/script/DeployAffiliateHook.s.sol`

## 2. Runtime Architecture

At a system level, the flow is:

1. the user interacts with the React app or extension surface
2. the frontend sends a request to the FastAPI backend
3. the backend tries deterministic routing for common high-structure intents
4. if deterministic routing does not apply, the backend invokes the LangChain agent
5. the backend returns either plain text or structured JSON-like content embedded in the response
6. the frontend parses that content into cards, reports, or transaction previews
7. if the response is executable, the frontend asks the user to sign in MetaMask or Phantom

This is important because the architecture is not a pure chat stack.

It is a hybrid of:

- UI state management
- wallet-aware execution
- deterministic backend routing
- AI-agent fallback
- structured result rendering

## 3. Client-Side Architecture

## 3.1 MainApp As The Core Frontend Orchestrator

`client/src/MainApp.tsx` is the dominant frontend file and acts as the orchestration layer for:

- app shell layout
- auth modal state
- wallet state
- chat state
- chat history loading and deletion
- market ticker updates
- portfolio loading
- swap-composer behavior
- structured-response parsing
- transaction execution
- toasts and user feedback

This file is very large because it currently centralizes most of the product behavior.

## 3.2 Structured Response Model

The frontend expects several structured payload families.

### SwapPreview

Used for:

- EVM swaps
- Solana swaps
- bridges
- transfers
- staking actions
- liquidity-add actions

Fields include:

- token symbols
- input and output amounts
- route labels
- fees
- approval transactions
- raw EVM transaction data
- serialized Solana transaction data
- bridge metadata such as source chain, destination chain, order ID, estimated time, and warnings

### BalanceData

Used for wallet balance reports.

It carries:

- wallet addresses
- per-chain balances
- total USD information
- chain-native balance information

### LiquidityPoolData

Used for pool discovery results.

It carries:

- DEX ID
- pair address
- base and quote token
- chain ID
- liquidity
- 24h volume
- APR
- protocol and explorer URLs

### UniversalCardsData

Used as a flexible card format for generalized structured answers.

Typical uses include:

- staking option cards
- pair search cards
- token search cards
- protocol suggestion cards

## 3.3 Wallet Support Matrix

### MetaMask

Frontend behavior:

- explicitly resolves the true MetaMask provider in multi-wallet environments
- guards against Phantom hijacking `window.ethereum`
- attempts chain switching to BNB Smart Chain
- signs an auth payload for the backend
- persists JWT and wallet state in localStorage

### Phantom

Frontend behavior:

- connects Solana first
- optionally reads Phantom EVM provider and EVM chain
- stores a structured wallet context
- attempts backend auth but tolerates guest fallback
- provides Solana signing for serialized transactions

This dual-wallet handling is one of the most distinctive engineering details in the repository.

## 3.4 Frontend Persistence

The frontend uses local browser storage for:

- `ap_token`
- `ap_wallet`
- `ap_sol_wallet`
- `ap_phantom_wallet_context`
- `ap_wallet_type`
- `ap_chat_session`

Product meaning:

- the app restores authenticated sessions when possible
- wallet context survives reloads
- anonymous and guest flows still preserve enough local identity to be useful

## 3.5 Main Transaction Execution Paths

### EVM execution path

The frontend:

- selects the correct provider based on wallet type
- checks and switches chain if required
- submits approval transaction first when present
- waits for approval receipt
- then submits the main EVM transaction with `eth_sendTransaction`

### Solana execution path

The frontend:

- requires Phantom
- receives a base64 serialized transaction
- deserializes it into a `VersionedTransaction`
- signs and sends it through Phantom

### Bridge follow-up path

For bridge flows, the frontend also polls the backend bridge-status endpoint after submission.

That means the product handles more than signing. It also tracks cross-chain settlement state.

## 3.6 Extension Architecture

### Popup

Current reality:

- visually designed
- backend health-aware
- uses mock token data
- not fully wired to real wallet or execution logic

### Sidepanel

Current reality:

- sends prompts to `/api/v1/agent`
- has local message history in component state
- displays backend status
- reads a stored wallet address
- does not render rich structured results like the main app

### Background worker

Current reality:

- configures sidepanel open behavior on install
- exposes a simple `PING` / `PONG` message path
- has a placeholder alarm listener for future scheduled tasks

## 4. Backend Architecture

## 4.1 FastAPI Application

The backend boot sequence in `server/app/main.py` does the following:

- creates all SQLAlchemy tables automatically on startup
- configures CORS for localhost frontend origins
- allows all `chrome-extension://.*` origins by regex
- mounts the agent, auth, chats, and portfolio routers
- exposes `/health`

This makes the backend suitable for both local app development and extension-based use.

## 4.2 API Surface

### Health

- `GET /health`

Purpose:

- simple backend reachability check used by the frontend and extension UIs

### Agent

- `POST /api/v1/agent`

Purpose:

- main natural-language request endpoint
- accepts wallet addresses, session state, chain context, chat ID, and wallet type
- returns either plain text or structured-response content

### RPC Proxy

- `POST /api/v1/rpc-proxy`

Purpose:

- proxy JSON-RPC requests to arbitrary RPC endpoints for browser/CORS convenience

### Bridge Status

- `GET /api/v1/bridge-status/{order_id}`

Purpose:

- poll deBridge order status after a bridge transaction is submitted

### Auth

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/metamask`
- `POST /api/v1/auth/phantom`
- `GET /api/v1/auth/me`

### Chats

- `GET /api/v1/chats`
- `POST /api/v1/chats`
- `GET /api/v1/chats/{chat_id}`
- `PATCH /api/v1/chats/{chat_id}`
- `DELETE /api/v1/chats/{chat_id}`

### Portfolio

- `GET /api/portfolio/{wallet_address}`

Purpose:

- multi-chain token and balance scan for the Portfolio tab and related flows

## 4.3 `/agent` Request Lifecycle

The `/agent` endpoint is the most important server-side flow.

The lifecycle is:

1. apply a simple in-memory rate limit by user ID or IP
2. normalize shorthand swap prompts
3. split EVM wallet and Solana wallet context
4. infer effective runtime chain context
5. try a sequence of direct deterministic handlers
6. if no direct handler returns a result, build a LangChain agent
7. try provider fallback across OpenAI, OpenRouter models, and Groq
8. clean the response to remove leaked ReAct scaffolding if necessary
9. persist user and assistant messages if the request is authenticated

This structure is a major technical strength because it balances reliability and flexibility.

## 4.4 Deterministic Routing Layer

The backend has explicit direct handlers for:

- common balance questions
- common swap requests
- bridge requests
- staking-info requests
- yield / APR / APY requests
- LP deposit prompts
- direct staking prompts
- direct pool lookup prompts

Why this matters:

- it reduces dependence on the LLM for high-risk structured actions
- it makes common intents faster and more reliable
- it allows test coverage around concrete intent classes

## 4.5 LLM Provider Strategy

The provider-selection logic supports fallback across:

- direct OpenAI
- OpenRouter models
- Groq

The backend tries multiple models/providers until one succeeds or all fail.

This makes the AI layer more resilient to:

- quota exhaustion
- rate limits
- provider-specific outages
- optional dependency gaps

## 4.6 Session Memory Model

The backend keeps conversation continuity in two different forms.

### DB-backed chat history

Used for authenticated users.

Stored tables:

- `users`
- `chats`
- `chat_messages`

### Process-local agent memory

Used by the LangChain agent.

Implementation detail:

- `ConversationBufferWindowMemory`
- last 6 exchanges kept in a process-local dictionary by session ID

This means visible persistence and model memory are separate layers.

## 5. Data Model

## 5.1 User

Fields include:

- numeric ID
- optional email
- optional password hash
- optional wallet address
- display name
- created timestamp

## 5.2 Chat

Fields include:

- UUID chat ID
- owning user ID
- title
- created timestamp
- updated timestamp

## 5.3 ChatMessage

Fields include:

- numeric message ID
- chat ID
- role
- content
- created timestamp

## 6. Authentication Details

## 6.1 Email/Password

Supported for traditional auth.

Uses:

- bcrypt password hashing
- JWT issuance

## 6.2 MetaMask Verification

The backend verifies:

- a signed message
- recovered address equality
- presence of a timestamp line
- timestamp freshness within five minutes

## 6.3 Phantom Verification

The backend verifies:

- signed message freshness
- Solana public key validity
- signature bytes from base64, hex, or base58 representations
- ed25519 message verification via PyNaCl

## 7. Portfolio And Balance Scanning

The portfolio system supports a broad multi-chain scan.

Tracked chains include:

- Ethereum
- BNB Chain
- Polygon
- Arbitrum
- Optimism
- Base
- Avalanche
- zkSync Era
- Linea
- Scroll
- Mantle
- Fantom
- Gnosis
- Celo
- Cronos
- Solana

The scan uses a combination of:

- public RPC calls
- token metadata lists
- price lookups from CoinGecko and Binance
- Moralis for token-enrichment and Solana SPL visibility where available

The portfolio endpoint is therefore not a trivial single-chain call. It is a multi-source aggregation layer.

## 8. Crypto-Agent Capability Inventory

The main agent module exposes tools for:

- wallet balance lookup
- swap simulation
- token price lookup
- EVM and Solana swap transaction building
- DeFi market overview
- DeFi yield analytics
- staking option discovery
- DexScreener pair search
- liquidity-pool search
- staking transaction building
- LP deposit transaction building
- bridge transaction building
- transfer transaction building

## 9. External Integrations

This repository integrates with several external services.

### LLM providers

- OpenAI
- OpenRouter
- Groq

### DeFi execution and routing

- Enso for EVM action construction
- Jupiter for Solana swaps
- deBridge DLN for cross-chain bridge construction and status tracking

### Data and analytics

- CoinGecko for price data
- Binance ticker API as a fallback / complementary source
- DefiLlama for DeFi analytics and yield opportunities
- DexScreener for token and pair search
- Moralis for wallet token discovery and Solana token data

### Storage groundwork

- BNB Greenfield SDK
- BNB Reed-Solomon tooling

## 10. Greenfield Service Architecture

The Greenfield service in `client/src/services/GreenfieldService.ts` is a notable future-facing subsystem.

It can:

- query storage providers
- select the best storage provider by measured latency
- generate and persist off-chain auth
- create a private bucket per wallet
- compute Reed-Solomon checksums for payloads
- create an on-chain object record
- upload an object to the storage provider

Current state:

- the service exists and is reasonably detailed
- the main app only exposes a visual "Greenfield Memory" status row
- the end-to-end memory UX is not fully wired into user flows yet

## 11. Smart Contract Architecture

`AffiliateHook.sol` implements a CL hook for PancakeSwap Infinity / V4-style pools.

Key behavior:

- after pool initialization, it sets a standard LP fee
- before affiliate-marked swaps, it lowers LP fees for the user path
- it extracts a distributor cut from the input amount using `BeforeSwapDelta`
- it tracks pending fees by currency
- anyone can trigger distribution to the distributor contract

Economic meaning:

- non-affiliate swaps use the standard LP fee
- affiliate swaps receive a user incentive through a lower LP fee
- the platform still captures a smaller distributor fee

Deployment script behavior:

- deploy hook
- read permissions bitmap from the hook
- encode bitmap plus tick spacing into pool parameters
- initialize a new dynamic-fee CL pool with the hook attached

## 12. Tests And What They Prove

The test suite mainly verifies intent-routing and helper logic.

Covered areas include:

- shorthand swap normalization
- staking and bridge routing behavior
- yield-search verification and APY / APR distinctions
- session-memory behavior
- missing-key and error surfacing
- protocol URL generation
- spam / dust balance filtering
- bridge-preview parsing on the frontend
- clipboard helper behavior on the frontend

What this means strategically:

- the repository is not untested
- but testing is concentrated around parser and routing correctness rather than full UI and end-to-end flows

## 13. Major Technical Caveats

These are important because they should shape how publicly polished the eventual weekly-update messaging becomes.

### 13.1 Hardcoded secret exposure

The crypto-agent source contains a hardcoded Moralis API key.

Internal meaning:

- this is a security and hygiene issue
- it should be fixed before production or public release framing

### 13.2 Weak JWT fallback

The JWT secret falls back to a weak development default if the environment variable is missing.

### 13.3 Replay risk in wallet auth

Wallet sign-in is freshness-based but not true nonce-based.

That means the system checks timestamps, but does not implement a durable challenge / nonce replay-prevention model.

### 13.4 Open RPC proxy risk

The RPC proxy accepts arbitrary RPC URLs and forwards them without allowlisting.

This is convenient for development but risky from a production SSRF / abuse perspective.

### 13.5 Process-local memory and rate limiting

The following are in-memory only:

- rate limiting
- LangChain session memory

This means the current architecture is not horizontally robust yet.

### 13.6 SQLite and no migration layer

The database is SQLite and tables are created with `create_all()` on startup.

This is acceptable for local development and prototyping, but not a mature migration strategy.

### 13.7 UI overclaim risk

Some UI copy is broader than the exact backend reality.

Examples include broader marketing statements around:

- protocol coverage
- PnL analytics
- extension maturity
- the exact routing engines currently active in code

The docs in this handoff pack intentionally separate confirmed implementation from marketing language.

## 14. Production-Readiness Summary

Most mature technical areas:

- FastAPI routing and agent orchestration
- wallet auth flows
- DB-backed chats
- structured frontend transaction previews
- multi-chain balance scanning
- bridge, staking, yield, and swap preparation logic

Less mature technical areas:

- frontend component decomposition, because much logic is centralized in `MainApp.tsx`
- extension popup and background-worker depth
- Greenfield memory integration into real user workflows
- secret management and hardening
- deployment / migration maturity
