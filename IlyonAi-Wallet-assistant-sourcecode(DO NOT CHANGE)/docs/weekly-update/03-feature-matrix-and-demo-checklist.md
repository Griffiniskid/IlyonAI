# Feature Matrix And Demo Checklist

## 1. Purpose

This file is the practical inventory for anyone who needs to turn the repository into a weekly-update narrative without accidentally overstating what is implemented.

Use it as the final truth table.

## 2. Feature Matrix

| Feature | What it does | Current state | Main surfaces | Notes |
| --- | --- | --- | --- | --- |
| Intro / landing screen | Explains the product before entering the app | Implemented | Main web app | Polished and presentation-ready |
| Wallet auth: MetaMask | EVM wallet connect, sign-in, JWT auth | Implemented | Main web app | Defaults user toward BNB Chain |
| Wallet auth: Phantom | Solana-first wallet connect with optional backend auth | Implemented with guest fallback | Main web app | Strong feature, but more nuanced than MetaMask |
| Sidebar control rail | Shows wallet, market, user, chats, backend status | Implemented | Main web app | Important for the overall product feel |
| Market ticker | Ambient live market data strip | Implemented | Main web app | Uses CoinGecko-driven pricing |
| Home tab | Dashboard, quick actions, feature framing | Implemented | Main web app | Works as onboarding and launch surface |
| AI chat | Natural-language DeFi interaction | Implemented | Main web app, sidepanel | Main web app is much richer than sidepanel |
| Saved chats | Persist and reload prior conversations | Implemented for authenticated users | Main web app + backend | One of the strongest maturity signals |
| Reasoning animation | Shows staged AI-progress steps while waiting | Implemented | Main web app | UX feature, not true chain-of-thought exposure |
| Structured balance cards | Render portfolio-style answers in chat | Implemented | Main web app | Improves clarity over plain text |
| Structured liquidity cards | Render pool discovery results in chat | Implemented | Main web app | Includes protocol and explorer link behavior |
| Structured universal cards | Render general-purpose action/result cards | Implemented | Main web app | Used for staking links and similar outputs |
| Structured transaction preview | Render execution-ready previews for wallet signing | Implemented | Main web app | Core differentiator |
| EVM swap preparation | Build EVM swap proposal and route info | Implemented | Backend + main web app | Built through backend execution tooling |
| Solana swap preparation | Build Solana swap payload for Phantom signing | Implemented | Backend + main web app | Important for Phantom support |
| Bridge preparation | Build bridge proposal and track order status | Implemented | Backend + main web app | One of the best demo-worthy flows |
| Token transfer preparation | Build token send / transfer tx | Implemented | Backend + main web app | Broadens app beyond pure DeFi |
| Staking info discovery | Return protocol links / staking options | Implemented | Backend + main web app | Clear informational mode |
| Staking transaction building | Build supported native-asset staking proposals | Implemented | Backend + main web app | Separate from staking-info mode |
| Yield analytics | Find APR / APY opportunities and ranked pools | Implemented | Backend + main web app | Verified-pool logic is meaningful |
| Pool lookup | Find pair / LP addresses and pool metadata | Implemented | Backend + main web app | Used by direct prompt routing |
| LP deposit preparation | Build deposit / add-liquidity action | Implemented | Backend + main web app | Depends on pool discovery first |
| Multi-chain portfolio tab | Show token holdings across chains | Implemented | Main web app + backend | Strong practical utility feature |
| Swap composer tab | Guide user into a swap flow, then hand off to chat | Implemented | Main web app | Composer, not final router UI |
| Popup UI | Quick-access extension surface | Partial / placeholder | Browser extension popup | Mostly mock data and presentation state |
| Sidepanel chat | Lightweight extension chat surface | Partial but working | Browser extension sidepanel | Sends prompts, but lacks full rich rendering |
| Background worker | Extension lifecycle and message groundwork | Early / infrastructure | Browser extension background | Minimal functionality today |
| Greenfield memory status in UI | Signals future memory capability | Visual only | Main web app sidebar | Not full end-to-end feature yet |
| Greenfield storage service | Can create buckets and upload memory payloads | Foundation implemented | Client service layer | Not fully wired into the app experience |
| Affiliate hook contract | Adds affiliate-aware fee logic to CL pools | Implemented as separate contract track | Solidity / Foundry | Not integrated into frontend flow yet |

## 3. Best Demo Candidates

If someone later needs examples of the strongest feature demonstrations from this repository, these are the best choices.

### 3.1 Natural-language swap to structured preview

Suggested example:

- ask to swap a token pair
- show AI reasoning animation
- render a structured transaction preview
- confirm that the wallet remains the final signer

Why it is strong:

- demonstrates the central AI-to-execution thesis
- shows the app is more than a chatbot

### 3.2 Bridge flow

Suggested example:

- request a bridge between chains or from Solana into an EVM destination
- show bridge-specific metadata in the preview
- explain that order status is tracked after submission

Why it is strong:

- shows the product can go beyond same-chain actions
- highlights one of the most advanced structured flows in the codebase

### 3.3 Portfolio scan

Suggested example:

- connect wallet
- open Portfolio tab
- show token table with chain labels and values

Why it is strong:

- easy to understand visually
- proves the product has real utility outside of chat

### 3.4 Yield / pool discovery

Suggested example:

- ask for the best APR or APY pool for a pair
- show the resulting liquidity card or structured action cards

Why it is strong:

- demonstrates that the AI layer can surface DeFi opportunities, not just build transactions

### 3.5 Saved chats

Suggested example:

- create or reopen a chat
- show that the session persists for authenticated users

Why it is strong:

- signals product maturity and continuity

## 4. Good Internal Talking Points

These are safe, evidence-based points someone can use when explaining what this module adds.

- This module turns the project into a more complete AI DeFi execution environment instead of a simple information bot.
- The frontend can parse and render structured outputs instead of dumping raw JSON or plain chat text.
- The backend now has deterministic routing for common high-risk intent categories like swap, bridge, staking, and yield discovery.
- The product now supports both MetaMask and Phantom user journeys, including Solana-aware flows.
- The module includes browser-extension surfaces, which pushes the product beyond a single web-app entry point.
- The repository also contains smart-contract groundwork for affiliate-fee monetization.
- There is early infrastructure for persistent AI memory through BNB Greenfield, even though it is not yet fully surfaced to users.

## 5. Overclaim Prevention

These are the most important things not to oversell.

### 5.1 Popup maturity

Do not describe the popup as a fully operational wallet assistant.

Safer wording:

- a designed popup shell exists
- the popup establishes the extension direction
- the main app is still the primary full-featured experience

### 5.2 Sidepanel parity

Do not imply the sidepanel has full feature parity with the main app.

Safer wording:

- the sidepanel already supports lightweight AI chat access
- the richer structured execution experience is concentrated in the main app

### 5.3 Greenfield memory

Do not describe Greenfield memory as a fully shipped user feature.

Safer wording:

- Greenfield-backed memory infrastructure has been implemented at the service layer
- the main user-facing memory workflow is still being wired through the product

### 5.4 Affiliate hook integration

Do not imply users are already actively routing swaps through the hook from the app.

Safer wording:

- a separate contract track for affiliate-aware fee logic is now built and deployable
- it expands the product's protocol-side monetization capabilities

### 5.5 Marketing copy vs exact implementation

Be careful with broad claims such as:

- every chain in DeFi is supported
- 24h PnL is fully implemented
- every wallet type is production-ready
- all extension surfaces are feature-complete

Safer wording:

- this module adds broad multi-chain coverage with strong EVM support and meaningful Solana support
- the main shipped experience is the full web app backed by the FastAPI agent layer

## 6. Public-Safe Summary

If someone later needs a concise but safe summary of this repository's contribution to the broader project, use something close to this:

This module adds a new AI-native DeFi experience to the broader project. It brings together wallet-based sign-in, persistent AI chat sessions, multi-chain portfolio visibility, structured execution previews for swaps and bridges, staking and liquidity discovery, browser-extension surfaces, and early infrastructure for both Greenfield-backed memory and affiliate-fee protocol logic. The main web app and backend orchestration layer are the most mature pieces today, while the extension shell and some infrastructure tracks are still evolving.
