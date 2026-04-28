# Ilyon AI — Partnership Integrations & Outreach Playbook

> **Status:** Live product · Solana Frontier Hackathon participant · Early-stage user base
> **Sender for all draft messages:** Griffin — Ilyon AI
> **Product:** https://ilyonai.com · **Staging:** https://staging.ilyonai.com · **API:** https://api.ilyonai.io

---

## Overview

Ilyon AI is an AI-powered multi-chain DeFi intelligence platform. The product is live and ships with deep integrations across RPC providers, DEX aggregators, market-data APIs, security feeds, wallet adapters, and AI model gateways. This document inventories every external integration that a partnership relationship could meaningfully improve, and for each partner provides: (1) the concrete integration surface inside our codebase, (2) contact channels, (3) a calibrated ask based on our current stage, and (4) an outreach draft ready to send with minor personalisation.

**Calibration notes.** We lead with *integration depth, not traction*. Early user numbers are not the hook — what we offer partners is: (a) a live product in the Solana Frontier Hackathon spotlight, (b) visible attribution on every analysis report / Blink / explorer link, (c) a clear mutual interest in expanding use of their platform. Honesty on stage beats inflated metrics every time.

**Outreach principles.**
1. Open with the specific files/endpoints that prove we already use them.
2. State one concrete ask — never "explore ways we might work together".
3. Offer something real in return (featured integration tile, co-tweet, case study, hackathon-demo shoutout).
4. Sign-off: `Griffin — Ilyon AI · https://ilyonai.com`.

---

## Integration Inventory & Outreach Tracker

| # | Partner | Tier | Integration Type | Status |
|---|---------|------|------------------|--------|
| 1 | Helius | 1 | Solana RPC + DAS + WebSocket | Not sent |
| 2 | Jupiter | 1 | DEX aggregator + swap simulation | Not sent |
| 3 | DexScreener | 1 | Market data (all chains) | Not sent |
| 4 | DeFiLlama | 1 | TVL, DEX volume, hacks, yields | Not sent |
| 5 | CoinGecko | 1 | Price oracle | Not sent |
| 6 | RugCheck | 1 | LP lock + launch analysis | Not sent |
| 7 | GoPlus Labs | 1 | Token security API | Not sent |
| 8 | Moralis | 1 | EVM token metadata | Not sent |
| 9 | OpenRouter | 1 | Multi-model AI gateway | Not sent |
| 10 | Solana Foundation | 2 | Ecosystem + hackathon | Not sent |
| 11 | Dialect | 2 | Blinks registry | Not sent |
| 12 | Phantom | 3 | Wallet adapter | Not sent |
| 13 | Solflare | 3 | Wallet adapter | Not sent |
| 14 | Backpack | 3 | Wallet adapter | Not sent |
| 15 | Raydium | 4 | DEX log parsing | Not sent |
| 16 | Orca | 4 | DEX log parsing | Not sent |
| 17 | Meteora | 4 | DEX log parsing | Not sent |
| 18 | Phoenix | 4 | Order book parsing | Not sent |
| 19 | Aave | 5 | Lending opportunity analyzer | Not sent |
| 20 | Compound | 5 | Lending opportunity analyzer | Not sent |
| 21 | Morpho | 5 | Lending opportunity analyzer | Not sent |
| 22 | Spark | 5 | Lending opportunity analyzer | Not sent |
| 23 | Solend | 5 | Solana lending | Not sent |
| 24 | MarginFi | 5 | Solana lending | Not sent |
| 25 | Kamino | 5 | Solana lending/vaults | Not sent |
| 26 | Euler | 5 | Lending opportunity analyzer | Not sent |
| 27 | Solscan | 6 | Solana block explorer | Not sent |
| 28 | Etherscan (family) | 6 | EVM contract source | Not sent |
| 29 | xAI (Grok) | 7 | AI analysis model | Not sent |
| 30 | Google DeepMind (Gemini) | 7 | AI analysis model | Not sent |
| 31 | OpenAI | 7 | AI analysis model (legacy) | Not sent |
| 32 | Trojan Bot | 8 | Affiliate / buy routing | Not sent |
| 33 | REKT News | 9 | Hack incident context | Not sent |
| 34 | Trust Wallet Assets | 9 | Token logo registry | Not sent |

---

# Tier 1 — Core API Partners

These are the integrations where credits, preferred rate limits, or featured-partner slots move the business directly.

---

## 1. Helius

**How we integrate**
- `src/data/solana.py` — Primary Solana RPC via `https://mainnet.helius-rpc.com/?api-key=...` for holder distribution, mint/freeze authority, token metadata resolution (DAS API), and account lookups
- `src/services/whale_stream.py` — WebSocket `logsSubscribe` stream at `wss://mainnet.helius-rpc.com` powering the zero-credit whale feed pipeline (`WHALE_FEED_MODE=stream`)
- `src/api/routes/transactions.py` — Wallet transaction history via `https://api.helius.xyz/v0/addresses/{wallet}/transactions`
- Every Solana address / whale / deployer lookup on ilyonai.com is powered by Helius. Roadmap item: migrate polling paths to Helius webhooks.

**Contact**
- Partnerships email: `partnerships@helius.xyz`
- Sales: https://www.helius.dev/contact
- Discord: https://discord.gg/helius (best channel for builder-support)
- Twitter/X: https://x.com/heliuslabs — DM founder Mert (`@0xMert_`)

**Suggested ask**
- Hackathon-tier API credits or business-tier rate-limit bump for the duration of Solana Frontier
- Helius partner-listing slot on their "Built with Helius" showcase page
- Co-tweet on Ilyon AI launch / Blinks demo
- Early access to webhook endpoints for the polling → webhook migration

**In return:** "Powered by Helius" attribution on every token analysis page footer, whale-stream status badge, and Blink card; co-authored post on how Ilyon AI uses `logsSubscribe` for sub-cent whale tracking.

**Draft message**

> Subject: Ilyon AI — Solana Frontier Hackathon build running entirely on Helius
>
> Hey Helius team,
>
> I'm Griffin, building Ilyon AI (https://ilyonai.com) — an AI-powered DeFi intelligence platform live for the Solana Frontier Hackathon. Helius is our entire Solana data layer: DAS for token metadata and holder analysis, mainnet RPC for on-chain authority checks, and `logsSubscribe` WebSocket for our real-time $10K+ whale feed (`src/services/whale_stream.py`). We recently rewrote the pipeline to stream mode specifically because Helius made zero-credit whale tracking feasible — that's now a shipped feature.
>
> Two asks:
> 1. Hackathon-tier credits or a temporary rate-limit bump through the Frontier judging window, so our public demo doesn't throttle under organic load.
> 2. A spot on your "Built with Helius" showcase — we'd love to be in the group of hackathon projects you highlight.
>
> In return, "Powered by Helius" stays visible on every analysis page, whale stream panel, and Blink card we ship, plus I'll write up our WebSocket streaming approach as a technical post if that's useful for your builder docs. Happy to hop on a call.
>
> — Griffin, Ilyon AI · https://ilyonai.com

---

## 2. Jupiter

**How we integrate**
- `src/data/jupiter.py` — Swap route simulation through Jupiter aggregator for our Solana honeypot detector; we calculate effective sell tax by simulating a `HONEYPOT_SIMULATION_SOL=0.1` swap and measuring slippage vs. quoted price
- `src/data/solana_log_parser.py` — Parse Jupiter v6 `SwapEvent` emissions to identify whale trades routed through Jupiter
- Every Solana token analysis on ilyonai.com runs a Jupiter simulation as a core signal

**Contact**
- Partnerships portal: https://portal.jup.ag
- Discord: https://discord.gg/jup (`#build-on-jupiter` channel)
- Twitter/X: https://x.com/JupiterExchange
- Dev relations: reach out via portal ticket

**Suggested ask**
- Free-tier or elevated rate-limit API key (Jupiter moved to paid API Jan 31, 2026 — 60 req/min on free tier is tight for a public product)
- Integration listing on Jupiter's ecosystem page
- Co-promo when we ship "Swap via Jupiter" button on token analysis pages

**In return:** Every Ilyon AI buy-side action will route through Jupiter, with `ref=` attribution if they want referral volume; "Swap powered by Jupiter" on analysis pages; public write-up of how we use Jupiter for honeypot detection (educational content for their community).

**Draft message**

> Subject: Ilyon AI — Jupiter is our honeypot engine, would love to talk API tier
>
> Hey Jupiter team,
>
> Griffin from Ilyon AI (https://ilyonai.com), a live Solana Frontier Hackathon project. Jupiter is the foundation of our honeypot detection — we simulate sell routes through your aggregator to verify whether any Solana token can actually be sold, calculate effective sell tax, and detect hidden fees that static analysis misses (`src/data/jupiter.py`). We also parse Jupiter v6 `SwapEvent` logs to surface whale trades in our real-time feed.
>
> With the Jan 31 paid-API change, our 60 req/min free tier is becoming a bottleneck as hackathon traffic picks up. Two asks:
> 1. An elevated rate-limit API key for the Frontier judging window and post-hackathon launch
> 2. A listing on the Jupiter ecosystem page — happy to submit the standard form, but worth flagging that we're an active depth integration, not just a button
>
> In return: we're preparing a "Swap via Jupiter" action on every Solana analysis page; all buy flow routes through Jupiter with referral attribution. And I'm writing up our honeypot-via-swap-simulation approach publicly — good signal for builders who don't realise your API enables this.
>
> — Griffin, Ilyon AI

---

## 3. DexScreener

**How we integrate**
- `src/data/dexscreener.py` — `https://api.dexscreener.com` drives every pair-level datapoint: price, 24h volume, liquidity depth, pair age, DEX attribution across Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche
- `src/analytics/time_series.py` — Historical candle data at `https://api.dexscreener.com/latest/dex` for our 14-day volume charts
- Powers `/trending`, `/dashboard`, `/pool/[id]`, and every token analysis page's market section

**Contact**
- Partnerships: `partners@dexscreener.com` (or via contact form at https://dexscreener.com/contact)
- Twitter/X: https://x.com/dexscreener
- Telegram: https://t.me/dexscreener (announcement channel; no public BD channel, email is the path)

**Suggested ask**
- Access to their partner API tier (they have one, it's not publicly priced)
- Feature in one of their Twitter mentions of cool integrations
- Guidance on proper attribution for their Enhanced Token Info / Orders API

**In return:** "Market data by DexScreener" attribution with logo on every token page and pool page; Ilyon AI becomes a DexScreener-first product for multi-chain routing (versus splitting across GeckoTerminal / DEXTools).

**Draft message**

> Subject: Ilyon AI — DexScreener powers every market card we render
>
> Hey DexScreener team,
>
> Griffin from Ilyon AI (https://ilyonai.com) — live Solana Frontier Hackathon project. DexScreener is the market-data backbone of our product. Every token analysis, every trending list across Solana / Ethereum / Base / Arbitrum / BSC / Polygon / Optimism / Avalanche, the `/dashboard` volume chart, the `/pool/[id]` composition view — all DexScreener (`src/data/dexscreener.py`, `src/analytics/time_series.py`).
>
> Two asks:
> 1. Guidance on partner-tier API access — we're well-behaved on the public endpoints, but we'd like to be on a proper relationship as traffic scales
> 2. If there's ever a round of "cool integrations" you amplify on X, Ilyon AI's token-intelligence layer is a natural fit — every DexScreener pair link in our app also deep-links back to your page
>
> In return: "Market data by DexScreener" attribution is already on our analysis pages. We're happy to make it more prominent, add your logo to pool cards, and be a DexScreener-first product rather than splitting data sources.
>
> — Griffin, Ilyon AI

---

## 4. DeFiLlama

**How we integrate**
- `src/data/defillama.py` — Four DeFiLlama hostnames in active use:
  - `https://api.llama.fi` — TVL, protocol list, chain breakdowns
  - `https://yields.llama.fi` — Yield pool discovery for our DeFi opportunity engine
  - `https://coins.llama.fi` — Historical price oracle
  - `https://stablecoins.llama.fi` — Stablecoin circulation data
- `src/api/routes/stats.py` — `https://api.llama.fi/overview/dexs/solana` and `/v2/chains` power the Dashboard's 24h volume widget and Solana TVL metric
- `src/intel/rekt_database.py` — `https://api.llama.fi/v2/hacks` and `/protocols` feed hack-incident correlation on token analysis pages
- `src/config.py` — `https://eth.llamarpc.com` is our Ethereum RPC fallback

**Contact**
- Twitter/X: https://x.com/DefiLlama (primary channel — they respond to DMs)
- Discord: https://discord.gg/defillama
- Email: `contact@llama.fi`
- GitHub (for API discussions): https://github.com/DefiLlama/DefiLlama-Adapters

**Suggested ask**
- Featured mention in their "DeFi tools" curation / retweet on launch
- API partner tier acknowledgement (they are generous with free access but recognition helps)
- Possible listing as a "DeFi explorer / intelligence tool" on defillama.com/tools

**In return:** "Data by DeFiLlama" attribution across every TVL widget, volume chart, and incident callout; we route our Ethereum RPC traffic through `llamarpc.com`; public mention of DeFiLlama as our primary macro-data provider.

**Draft message**

> Subject: Ilyon AI — four DeFiLlama hostnames power the dashboard, wanted to introduce ourselves
>
> Hey DeFiLlama,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. DeFiLlama is woven through the product in four places: `api.llama.fi` for Solana TVL and DEX volume on our dashboard, `yields.llama.fi` for our DeFi opportunity engine, `coins.llama.fi` for historical price lookups, and `api.llama.fi/v2/hacks` feeding the REKT-incident context we render next to related tokens. We also use `eth.llamarpc.com` as our Ethereum fallback RPC.
>
> One ask: a mention when we ship the full launch. DeFiLlama retweets of builder tools carry real weight in this community, and every chart on our dashboard is a "Data by DeFiLlama" attribution. If listing on defillama.com/tools (or similar) is possible for live intelligence products, I'd love to walk you through what we do.
>
> In return: attribution stays prominent, Ethereum RPC traffic continues through `llamarpc.com`, and we're happy to push any DeFiLlama-related feature (yields browser, stablecoin dashboards) higher-priority than we otherwise would.
>
> — Griffin, Ilyon AI

---

## 5. CoinGecko

**How we integrate**
- `src/data/coingecko.py` — `https://api.coingecko.com/api/v3` for token metadata, price lookups, and market context
- `src/data/solana.py` and `src/api/routes/stats.py` — SOL/USD spot price from CoinGecko drives every USD-denominated value on the dashboard
- `COINGECKO_PRO_URL` constant present (`https://pro-api.coingecko.com/api/v3`) — ready to switch on if we get Pro access

**Contact**
- Partnerships: https://www.coingecko.com/en/api/partners
- API sales: `api-sales@coingecko.com`
- Twitter/X: https://x.com/coingecko
- Discord: https://discord.gg/coingecko

**Suggested ask**
- Demo / Analyst tier of CoinGecko Pro API (they have a startup / hackathon programme)
- Listing in CoinGecko's "Built with CoinGecko" integrations directory

**In return:** Attribution on every price display; migration from free to Pro endpoints so their paid-tier logo shows up on the product; tweet on integration.

**Draft message**

> Subject: Ilyon AI — CoinGecko powers our SOL price everywhere, looking at Pro tier
>
> Hey CoinGecko team,
>
> Griffin from Ilyon AI (https://ilyonai.com) — Solana Frontier Hackathon project, live now. CoinGecko drives every USD value on our dashboard (SOL spot, token metadata, market context — `src/data/coingecko.py`). Our codebase already has `pro-api.coingecko.com` wired and ready to flip on.
>
> Ask: if there's a hackathon, startup, or Analyst-tier programme that fits a live product in its early days, we'd be strong candidates — we're a high-frequency integration user and every data point gets "via CoinGecko" attribution. Also open to being listed in your "Built with CoinGecko" directory.
>
> In return: we'd upgrade from free endpoints to the Pro tier everywhere, co-tweet the integration, and happy to do a short case study on how intelligence products combine CoinGecko market data with on-chain security signals.
>
> — Griffin, Ilyon AI

---

## 6. RugCheck

**How we integrate**
- `src/data/rugcheck.py` — `https://api.rugcheck.xyz/v1/tokens` powers LP lock verification, bundled-launch detection, and community-reported risk flags that layer on top of our AI analysis
- Every Solana token analysis on ilyonai.com cross-references RugCheck for a "community signal" block

**Contact**
- Twitter/X: https://x.com/RugCheckxyz (primary)
- Telegram: https://t.me/rugcheckxyz
- Website contact: https://rugcheck.xyz (contact form in footer)
- Email (from WHOIS / site): `team@rugcheck.xyz`

**Suggested ask**
- Co-branded "RugCheck + Ilyon AI" tile on Solana token analysis pages (they amplify, we amplify)
- Possible API rate-limit bump or partner key
- Shared presence at Solana Frontier demo-day content

**In return:** RugCheck logo + direct link next to every LP-lock verdict we render; co-tweet on launch; joint content on "combining community flags with AI token analysis".

**Draft message**

> Subject: Ilyon AI — RugCheck is our community signal layer, let's co-brand
>
> Hey RugCheck team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. RugCheck is wired into every Solana token analysis we ship — `src/data/rugcheck.py` pulls your LP-lock, bundled-launch, and community flags and layers them on top of our AI analysis so users get both signals in one view.
>
> Proposal: a lightweight co-brand. We already render "Community verdict from RugCheck" on our Solana token pages linking back to your report. Happy to make that more prominent (dedicated tile, logo, direct CTA to your full report) in exchange for a co-tweet on launch and, if possible, a partner API key for better reliability during demo-day traffic.
>
> We're two products that cover different sides of the same problem — community intelligence (you) plus AI + on-chain analysis (us). Joint positioning is obvious. Happy to jump on a Twitter Space or produce shared content around Frontier.
>
> — Griffin, Ilyon AI

---

## 7. GoPlus Labs

**How we integrate**
- `src/data/goplus.py` — `https://api.gopluslabs.io/api/v1` powers EVM-side token security checks that complement our AI analysis: malicious function detection, proxy flags, blacklist mechanisms, honeypot verdicts for non-Solana chains
- Every `/token/[address]?chain=ethereum|base|bsc|...` analysis on ilyonai.com pulls GoPlus signals

**Contact**
- Partnerships: `business@gopluslabs.io`
- Developer portal: https://gopluslabs.io/developer
- Discord: https://discord.gg/gopluslabs
- Twitter/X: https://x.com/GoPlusSecurity

**Suggested ask**
- Partner API key with elevated rate limits
- Listing as an integration partner on their ecosystem page (https://gopluslabs.io/ecosystem)
- Co-marketing on the EVM-analysis surface of our product

**In return:** "Security signals by GoPlus" attribution on every EVM token page; direct deep-link to their token-risk page for users who want the raw report; joint post on combining GoPlus signals with AI narrative analysis.

**Draft message**

> Subject: Ilyon AI — GoPlus is the EVM security layer in our token analyzer
>
> Hey GoPlus team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project with a multi-chain scope: Solana is our core, plus Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche for EVM analysis. On every EVM token page, GoPlus (`src/data/goplus.py`) provides the underlying malicious-function / proxy / blacklist / honeypot signals that feed into our AI scoring.
>
> Asks:
> 1. A partner API key so we're on a supported tier rather than anonymous
> 2. Consideration for your integrations showcase on gopluslabs.io/ecosystem
>
> In return: "Security signals by GoPlus" attribution on every EVM token page, direct CTA to your full report for users who want the raw evidence, and a joint case study on how AI-layered intelligence products consume GoPlus data in production.
>
> — Griffin, Ilyon AI

---

## 8. Moralis

**How we integrate**
- `src/data/moralis.py` — `https://deep-index.moralis.io/api/v2.2` fills the EVM token-metadata and wallet-history gaps DexScreener doesn't cover (logos, decimals edge cases, richer ERC-20 transfer history)

**Contact**
- Partnerships: `partners@moralis.io` (or contact form https://moralis.io/contact)
- Startup programme: https://moralis.io/startup
- Twitter/X: https://x.com/MoralisWeb3
- Discord: https://discord.gg/moralis

**Suggested ask**
- Apply to Moralis Startup Program (they offer significant API credits to early-stage projects)
- Partner listing on their showcase page

**In return:** Moralis attribution on EVM token pages; case study publication on using Moralis for security-oriented token metadata.

**Draft message**

> Subject: Ilyon AI — applying for the Moralis Startup Program
>
> Hey Moralis team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Our EVM analysis path uses Moralis for the metadata and transfer-history signals we can't get from DEX aggregators alone (`src/data/moralis.py`, endpoint `deep-index.moralis.io/api/v2.2`). We're currently on the free tier and hitting it during demos.
>
> We'd like to apply for the Moralis Startup Program. Happy to fill the formal application — flagging here so you can match the context: live product, hackathon visibility, multi-chain EVM scope (Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche), Moralis as our EVM metadata layer.
>
> In return, "Data by Moralis" attribution on every EVM token page, and we'd love to publish a short case study on security-focused use of your APIs — different angle from your usual wallet-app integrations.
>
> — Griffin, Ilyon AI

---

## 9. OpenRouter

**How we integrate**
- `src/ai/openai_client.py` — Base URL `https://openrouter.ai/api/v1/chat/completions`, OpenRouter is our primary AI gateway
- Every token analysis narrative, contract scanner verdict, and AI risk summary ships via OpenRouter (default model: `nvidia/nemotron-3-super-120b-a12b:free`)
- `src/contracts/ai_auditor.py` — Contract vulnerability scanner also calls OpenRouter

**Contact**
- Twitter/X: https://x.com/OpenRouterAI (primary — founder `@OpenRouterAI` responsive)
- Discord: https://discord.gg/openrouter
- Partnerships: via Discord `#partnerships` channel or `partnerships@openrouter.ai`

**Suggested ask**
- Credits grant for a Solana hackathon build
- Featured integration slot / retweet (OpenRouter regularly amplifies cool consumer use cases)
- Early access to new model releases for AI-intensive analysis pipelines

**In return:** "AI powered by OpenRouter" attribution on every analysis; public write-up of our multi-model routing approach (GPT-4o + Grok + Gemini through OpenRouter); case study fuel for their marketing.

**Draft message**

> Subject: Ilyon AI — OpenRouter is our AI backbone, can we talk credits?
>
> Hey OpenRouter team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. OpenRouter is the entire AI backbone of our product — every token analysis narrative, every smart-contract vulnerability verdict, every risk summary routes through `openrouter.ai/api/v1/chat/completions` (`src/ai/openai_client.py`, `src/contracts/ai_auditor.py`). We default to Nemotron on the free tier and route higher-stakes analysis to stronger models.
>
> Two asks:
> 1. A credits grant through the Frontier judging window — AI analysis is per-token, so traffic maps directly to tokens (not cacheable the usual way)
> 2. If credits aren't on the table, even a retweet on launch — OpenRouter amplifying a Solana hackathon build that *uses* multi-model routing rather than just one provider is a strong signal
>
> In return: "AI powered by OpenRouter" attribution on every analysis page, plus a public write-up of our multi-model approach (how we route between Nemotron, GPT-4o, Grok, and Gemini behind a single OpenRouter interface) — useful content for builders who haven't clicked that OpenRouter makes this trivial.
>
> — Griffin, Ilyon AI

---

# Tier 2 — Solana Ecosystem

---

## 10. Solana Foundation

**How we integrate**
- Solana-native product: wallet auth, Solana Actions / Blinks spec implementation (`src/api/routes/actions.py`, `src/api/routes/blinks.py`), ecosystem-level analytics (Solana TVL, volume, grade distribution)
- Solana Frontier Hackathon participant

**Contact**
- Ecosystem team: `ecosystem@solana.org`
- Grants / Foundation: https://solana.org/grants
- Twitter/X: https://x.com/solana
- Superteam (regional builder support): https://superteam.fun

**Suggested ask**
- Consideration for an ecosystem grant post-Frontier
- Superteam / Solana ecosystem retweet on launch
- Inclusion in Solana ecosystem directory

**In return:** Continued deep use of Solana-native features (Blinks, wallet adapter), ecosystem-level analytics that make the chain more legible, public commitment to Solana-first roadmap.

**Draft message**

> Subject: Ilyon AI — Solana-native intelligence layer shipped for Frontier
>
> Hey Solana Foundation / ecosystem team,
>
> Griffin from Ilyon AI (https://ilyonai.com), Solana Frontier Hackathon participant. We built the intelligence layer Solana needs: real-time token security analysis, smart-money tracking via Helius `logsSubscribe`, Blinks-compatible shareable reports, wallet-native auth via `@solana/wallet-adapter`, ecosystem analytics (TVL, DEX volume, grade distribution for Solana tokens). Product is live now — no waitlist.
>
> We're Solana-first by design: our Blinks implementation (`src/api/routes/blinks.py`, `src/api/routes/actions.py`) lets any analysis report unfurl directly in Phantom / Solflare / Backpack wallets from X. Frontier accelerated this; we're shipping it past the hackathon.
>
> Ask: consideration for the Solana Foundation ecosystem grants track post-Frontier, plus any amplification you do for hackathon builders who are live. Happy to walk the ecosystem team through the product before judging closes.
>
> — Griffin, Ilyon AI

---

## 11. Dialect

**How we integrate**
- Solana Actions & Blinks spec implementation — Dialect hosts the Blinks registry and infrastructure that makes our shareable analysis reports unfurl inside wallets and on X
- `src/api/routes/actions.py` and `src/api/routes/blinks.py` implement the spec they defined

**Contact**
- Website: https://dialect.to
- Twitter/X: https://x.com/saydialect
- Email: `team@dialect.to`
- Discord: linked from dialect.to

**Suggested ask**
- Registry listing for Ilyon AI Blinks
- Co-tweet when we ship the first analysis-report Blink campaign
- Early access to any new Dialect-Blinks SDK features

**In return:** Prominent "Blink powered by Solana Actions" attribution, pushing Blinks discoverability through a real consumer-facing intelligence tool rather than just a tipping / donation use case.

**Draft message**

> Subject: Ilyon AI — Blinks for token analysis reports, let's get on the registry
>
> Hey Dialect team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. We implemented the Solana Actions spec end-to-end (`src/api/routes/actions.py`, `src/api/routes/blinks.py`) — every token analysis on our platform generates a shareable Blink that unfurls directly in wallets and on X. This is a non-tipping, non-mint use case for Blinks: shareable *intelligence* that protects users before they buy.
>
> Asks:
> 1. Registration on the official Blinks registry / your "Built with Blinks" directory
> 2. A co-tweet when we push the first campaign of Blinks on X — this is exactly the kind of use case that proves Blinks aren't just for payments
>
> In return: prominent "Solana Actions" attribution on every shareable report, and a clear public story about Blinks for consumer-facing intelligence products. Happy to record a short demo before Frontier closes.
>
> — Griffin, Ilyon AI

---

# Tier 3 — Wallets

---

## 12. Phantom

**How we integrate**
- `@solana/wallet-adapter-base` / `-react` / `-react-ui` (`web/package.json`) — Phantom is the default wallet in our adapter list
- Wallet-sign-in authentication (`web/components/providers.tsx`), Blinks unfurl directly into Phantom
- Portfolio page reads balances from the Phantom-connected wallet

**Contact**
- Partnerships: `partnerships@phantom.app`
- Support / BD contact form: https://phantom.app/contact
- Twitter/X: https://x.com/phantom
- Discord: https://discord.gg/phantom

**Suggested ask**
- Featured placement in Phantom's app discovery surface (they curate Solana apps inside the wallet)
- Co-marketing on Ilyon AI as the security-analysis layer Phantom users can pair with their wallet
- Inclusion in any "protect your portfolio" campaign they run

**In return:** Wallet-sign-in–first product, Blinks optimized for Phantom's Blinks rendering, Phantom shown first in our adapter list.

**Draft message**

> Subject: Ilyon AI — Phantom-native intelligence layer, live for Frontier
>
> Hey Phantom BD team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Ilyon AI is Phantom-native: wallet-sign-in is our entire auth model, our portfolio view loads instantly off a connected Phantom wallet, and our token analysis Blinks are designed to unfurl cleanly inside Phantom chat. Phantom is the first wallet in our `@solana/wallet-adapter` list — ahead of Solflare and Backpack — because that's the order of how our users actually show up.
>
> Ask: featured placement on Phantom's app-discovery surface, or any co-marketing you're running around "protect your portfolio before you ape" themes. We're exactly that layer — safety score, whale activity, and honeypot detection one click away from the wallet.
>
> In return: Phantom-first UX on our side, early access to any Phantom-specific features we can integrate (mobile deep-links, push notifications, whatever you've got). Easy demo.
>
> — Griffin, Ilyon AI

---

## 13. Solflare

**How we integrate**
- Solflare in our `@solana/wallet-adapter` list; second wallet option on the connection modal
- Session auth via Solflare message signature supported
- Blinks render in Solflare's Blinks-compatible surface

**Contact**
- Partnerships: `hello@solflare.com`
- Twitter/X: https://x.com/solflare_wallet
- Discord: https://discord.gg/solflare

**Suggested ask**
- Integration spotlight / featured app slot
- Co-tweet on launch
- Testing partnership for their staking / swap flows once we surface them in our product

**In return:** Solflare given equal weight to Phantom in adapter UI, Solflare-optimised Blinks rendering verified, co-marketing language that explicitly calls out Solflare (not just "Solana wallets").

**Draft message**

> Subject: Ilyon AI — Solflare is a first-class wallet in our adapter, let's talk integration spotlight
>
> Hey Solflare team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Solflare is a first-class option in our wallet adapter — users authenticate, load their portfolio, and get Blinks-compatible shareable reports without leaving the Solflare experience.
>
> Ask: a featured-app spotlight or co-tweet on launch. Specifically, we'd like to be explicitly called out as "works great in Solflare" rather than bundled into generic "Solana wallet" mentions — helps both sides, and we're happy to QA Blinks rendering in Solflare's surface before we make the claim publicly.
>
> In return: Solflare stays prominent in our wallet picker, we'll test against Solflare-specific Blinks rendering proactively, and co-tweet on any Solflare feature launches that intersect with our product (staking, in-wallet swaps, etc).
>
> — Griffin, Ilyon AI

---

## 14. Backpack

**How we integrate**
- Backpack in our `@solana/wallet-adapter` list; supported for wallet auth, portfolio loading, and Blinks
- Explicitly called out in our README as a supported wallet

**Contact**
- Twitter/X: https://x.com/xNFT_Backpack (primary)
- Website: https://backpack.app
- Email / partnerships: via Armani (`@armaniferrante`) or Backpack BD via Twitter DM
- Discord: https://discord.gg/backpack

**Suggested ask**
- xNFT directory or featured-app listing
- Co-tweet on launch — Backpack's team is active in amplifying Solana builders
- Potential xNFT version of our token analyzer down the road

**In return:** Backpack kept as a first-class option, Blinks tested against Backpack specifically, public acknowledgement of Backpack as a supported wallet (already in README).

**Draft message**

> Subject: Ilyon AI — Backpack-compatible from day one, live for Frontier
>
> Hey Backpack team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Backpack is a first-class wallet in our adapter picker, our portfolio loads cleanly from Backpack-connected wallets, and our Blinks are tested against the Backpack rendering surface.
>
> Asks:
> 1. A listing in your app directory / "works great with Backpack" surface
> 2. A co-tweet on launch — your team's amplification of Solana builders is real social proof and this is a natural fit for the Frontier story
>
> Longer term: I'm interested in whether Ilyon AI makes sense as an xNFT. The token-analysis UX is naturally wallet-resident (you look up a token before ape'ing it) and I'd like to explore that once we're past Frontier judging.
>
> — Griffin, Ilyon AI

---

# Tier 4 — DEX Protocols (Log Parsing Integrations)

These partners power whale-trade detection through on-chain log parsing (`src/data/solana_log_parser.py`). No API relationship is required, but partnerships unlock co-marketing for a product that visibly tracks their DEX-level volume.

---

## 15. Raydium

**How we integrate**
- `src/data/solana_log_parser.py` — Parse Raydium V4 AMM `ray_log` format and Raydium CLMM / CP IDL-encoded swap events to identify whale trades
- Every whale transaction on `/smart-money` and `/whales` attributes DEX = Raydium when logs match

**Contact**
- Twitter/X: https://x.com/RaydiumProtocol
- Discord: https://discord.gg/raydium
- Business / partnerships: via Discord `#business-inquiries` or form at https://raydium.io

**Suggested ask**
- Co-tweet on launch highlighting Raydium-attributed whale volume visible in our product
- Potential inclusion in any Raydium-ecosystem builder showcase

**In return:** Prominent Raydium DEX attribution on every whale transaction ("Swap on Raydium"), linking back to their pair page.

**Draft message**

> Subject: Ilyon AI — real-time Raydium whale volume surfaced in a consumer product
>
> Hey Raydium team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. We parse Raydium V4 AMM `ray_log` emissions and Raydium CLMM / CP swap events in real time (`src/data/solana_log_parser.py`) to surface whale activity on `/smart-money` and `/whales`. Every Raydium-routed swap of $10K+ shows up in our feed with a direct link back to your pair page.
>
> Ask: a co-tweet on launch. Nothing formal — our integration is pure log-parsing and public data, but visible Raydium attribution in a consumer-facing intelligence product is a good story for both sides.
>
> — Griffin, Ilyon AI

---

## 16. Orca

**How we integrate**
- `src/data/solana_log_parser.py` — Orca Whirlpool `Swapped` event parsing for whale trade attribution

**Contact**
- Twitter/X: https://x.com/orca_so
- Discord: https://discord.gg/orca-so
- Business: via Discord or `contact@orca.so`

**Suggested ask**
- Co-tweet on launch
- Ecosystem / builder-showcase inclusion

**In return:** Orca attribution on every Whirlpool-attributed whale transaction, deep-link back to the Whirlpool.

**Draft message**

> Subject: Ilyon AI — Orca Whirlpool swaps show up in our real-time whale feed
>
> Hey Orca team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Our log parser consumes Orca Whirlpool `Swapped` events (`src/data/solana_log_parser.py`) to surface whale trades in real time on `/smart-money` and `/whales`. Every Orca-routed swap above our $10K threshold appears in the feed with DEX = Orca and a direct link back to your Whirlpool.
>
> Ask: a co-tweet on launch, or inclusion in any Orca ecosystem/builder showcase you run. We're a consumer-facing product that makes Orca volume legible to traders — good mutual story.
>
> — Griffin, Ilyon AI

---

## 17. Meteora

**How we integrate**
- `src/data/solana_log_parser.py` — Meteora DLMM swap event parsing for whale trade attribution (references `https://github.com/MeteoraAg/dlmm-sdk`)

**Contact**
- Twitter/X: https://x.com/MeteoraAG
- Discord: https://discord.gg/meteora
- Business: `team@meteora.ag` or Discord

**Suggested ask**
- Co-tweet on launch
- Inclusion in Meteora DLMM builder / integration highlights

**In return:** Meteora DLMM attribution on every matching whale transaction, deep-link back to their pool.

**Draft message**

> Subject: Ilyon AI — Meteora DLMM activity surfaced in our whale feed
>
> Hey Meteora team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. We parse Meteora DLMM swap events in real time (`src/data/solana_log_parser.py`) so whale-sized trades through Meteora pools show up on `/smart-money` and `/whales` with DEX attribution and a deep-link back to the pool.
>
> Ask: a co-tweet on launch. Meteora DLMM volume is growing fast and a consumer-facing product that makes it visible to traders is a natural amplification opportunity.
>
> — Griffin, Ilyon AI

---

## 18. Phoenix

**How we integrate**
- `src/data/solana_log_parser.py` — Phoenix order book event parsing (references `https://github.com/Ellipsis-Labs/phoenix-sdk`)

**Contact**
- Twitter/X: https://x.com/EllipsisLabs
- Phoenix docs: https://ellipsis-labs.gitbook.io/phoenix-dex
- Email: `hello@ellipsislabs.xyz`

**Suggested ask**
- Co-tweet on launch
- Ecosystem highlight

**In return:** Phoenix attribution on matching whale trades, amplification of Phoenix's order-book volume in a DEX-neutral intelligence product.

**Draft message**

> Subject: Ilyon AI — Phoenix swaps parsed into our real-time whale feed
>
> Hey Ellipsis Labs team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Phoenix is one of the DEX venues we parse in real time (`src/data/solana_log_parser.py`) — whale-sized trades through Phoenix show up in our feed alongside Raydium, Orca, Meteora, and Jupiter-routed swaps.
>
> Ask: a co-tweet on launch or inclusion in any Phoenix-ecosystem showcase. Consumer intelligence products that track order-book DEX volume are rare — worth amplifying.
>
> — Griffin, Ilyon AI

---

# Tier 5 — DeFi Lending Protocols

These partners are surfaced in our DeFi opportunity engine (`src/defi/lending_analyzer.py`). Each has a docs URL hard-coded in our protocol registry; partnerships unlock deeper integration and co-promotion when we route users to their deposit / borrow flows.

---

## 19. Aave

**How we integrate**
- `src/defi/lending_analyzer.py` — Aave markets (v2 and v3) included in our DeFi opportunity surface with `docs_url=https://docs.aave.com`
- Users get Aave supply / borrow opportunities surfaced based on their portfolio

**Contact**
- Twitter/X: https://x.com/aave
- Discord: https://discord.gg/aave
- Governance forum: https://governance.aave.com
- Business: `partnerships@aave.com`

**Suggested ask**
- Aave Grants DAO consideration (https://aavegrants.org)
- Listing as an Aave ecosystem / data integration
- Co-tweet when we launch the DeFi opportunity engine publicly

**In return:** Aave-first routing for supply/borrow opportunities surfaced to our users; clean attribution with logo and deep-link; case study on AI-driven opportunity surfacing.

**Draft message**

> Subject: Ilyon AI — surfacing Aave opportunities to users, let's connect
>
> Hey Aave team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Aave is a first-class protocol in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) — we analyse connected wallets' EVM exposure and surface relevant Aave supply / borrow opportunities with clear risk context and a deep-link to app.aave.com.
>
> Asks:
> 1. Consideration for an Aave Grants DAO application — we're a data-and-intelligence layer that drives informed deposits into Aave, not yet another lending product
> 2. A co-tweet when we launch the opportunity engine publicly
>
> In return: Aave-first routing for lending opportunities surfaced to our users, prominent attribution, and a short case study on AI-driven user-opportunity matching.
>
> — Griffin, Ilyon AI

---

## 20. Compound

**How we integrate**
- `src/defi/lending_analyzer.py` — Compound markets included with `docs_url=https://docs.compound.finance`
- Compound supply/borrow opportunities surfaced in the DeFi engine

**Contact**
- Twitter/X: https://x.com/compoundfinance
- Discord: https://discord.gg/compound
- Governance forum: https://www.comp.xyz
- Grants: via governance forum proposal

**Suggested ask**
- Compound ecosystem grant consideration
- Listing on "Built on Compound" / integrations page
- Co-tweet on launch

**In return:** Compound-first attribution for matching opportunities, deep-links to Compound v3 interfaces, case study.

**Draft message**

> Subject: Ilyon AI — Compound opportunities surfaced by our DeFi engine
>
> Hey Compound team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. We surface Compound supply/borrow opportunities in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) based on user portfolio composition, with direct links back to Compound interfaces.
>
> Ask: listing on the Compound integrations page if it's possible for read-only intelligence integrations, and a co-tweet on launch. Longer term, happy to formalise through an ecosystem grant conversation if Compound currently runs that track.
>
> In return: Compound-first surfacing for matching opportunities, clean attribution, and a case study on AI-driven lending-opportunity discovery.
>
> — Griffin, Ilyon AI

---

## 21. Morpho

**How we integrate**
- `src/defi/lending_analyzer.py` — Morpho markets included with `docs_url=https://docs.morpho.org`
- Users see Morpho vault / market opportunities in our DeFi engine

**Contact**
- Twitter/X: https://x.com/MorphoLabs
- Discord: https://discord.gg/morpho
- Business: via Twitter DM or form on morpho.org
- Grants: https://morpho.org/grants

**Suggested ask**
- Morpho grants programme application
- Partner / ecosystem listing
- Co-tweet on launch

**In return:** Morpho attribution on surfaced opportunities, deep-links to app.morpho.org, case study.

**Draft message**

> Subject: Ilyon AI — surfacing Morpho Blue opportunities to users
>
> Hey Morpho Labs,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Morpho is one of the protocols in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) — we match user portfolios to Morpho Blue markets / vaults and surface relevant supply opportunities with a deep-link to app.morpho.org.
>
> Ask: consideration for the Morpho grants programme — we're an intelligence layer that drives informed deposits into Morpho, not a competing lending product. Also interested in ecosystem listing / amplification if you have that surface.
>
> In return: Morpho-first attribution for matching opportunities, a co-tweet on our launch, and a short write-up on AI-driven lending-market discovery from the depositor's side.
>
> — Griffin, Ilyon AI

---

## 22. Spark

**How we integrate**
- `src/defi/lending_analyzer.py` — Spark markets included with `docs_url=https://docs.spark.fi`

**Contact**
- Twitter/X: https://x.com/sparkdotfi
- Discord: https://discord.gg/sparkfi
- Forum: https://forum.sky.money (Sky / Spark governance)
- Business: via Discord or forum post

**Suggested ask**
- Ecosystem / integration listing
- Co-tweet on launch

**In return:** Spark attribution on matching opportunities, direct CTA to app.spark.fi.

**Draft message**

> Subject: Ilyon AI — Spark lending opportunities surfaced in our DeFi engine
>
> Hey Spark team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Spark is included in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) — users see Spark supply opportunities ranked against other protocols with clear yield context and a link to app.spark.fi.
>
> Ask: inclusion in any Spark integrations / ecosystem directory and a co-tweet on launch. In return: Spark-first attribution for matching opportunities and a case study on AI-driven opportunity surfacing.
>
> — Griffin, Ilyon AI

---

## 23. Solend

**How we integrate**
- `src/defi/lending_analyzer.py` — Solend markets included with `docs_url=https://docs.solend.fi`
- One of our Solana-native lending surfaces

**Contact**
- Twitter/X: https://x.com/solendprotocol
- Discord: https://discord.gg/solend
- Email: `team@solend.fi`

**Suggested ask**
- Ecosystem listing / co-tweet
- Any Solend-ecosystem grant or builder track

**In return:** Solend attribution for surfaced Solana lending opportunities, deep-links to solend.fi.

**Draft message**

> Subject: Ilyon AI — Solend in our Solana lending opportunity surface
>
> Hey Solend team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Solend is one of the Solana-native lending protocols in our DeFi opportunity engine (`src/defi/lending_analyzer.py`). Users get Solend supply / borrow opportunities matched against their wallet composition with a direct link to solend.fi.
>
> Ask: a co-tweet on launch and inclusion in any Solend ecosystem / builder amplification you run. We drive informed depositors into Solend — mutual fit for Frontier.
>
> — Griffin, Ilyon AI

---

## 24. MarginFi

**How we integrate**
- `src/defi/lending_analyzer.py` — MarginFi markets included with `docs_url=https://docs.marginfi.com`

**Contact**
- Twitter/X: https://x.com/marginfi
- Discord: https://discord.gg/mrgn
- Email: `hello@mrgn.group`

**Suggested ask**
- Ecosystem listing
- Co-tweet on launch
- Potential referral / point-program integration

**In return:** MarginFi attribution on surfaced opportunities, clean deep-links to app.marginfi.com.

**Draft message**

> Subject: Ilyon AI — MarginFi in our Solana lending opportunity engine
>
> Hey MarginFi team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. MarginFi is surfaced in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) — user portfolios get matched to MarginFi supply / borrow opportunities with direct links to app.marginfi.com.
>
> Ask: a co-tweet on launch and, if you run an affiliate or points-referral layer, a conversation about wiring that into the Ilyon AI → MarginFi CTA path. Depositors coming from an intelligence product are exactly the users you want.
>
> — Griffin, Ilyon AI

---

## 25. Kamino

**How we integrate**
- `src/defi/lending_analyzer.py` — Kamino markets / vaults included with `docs_url=https://docs.kamino.finance`

**Contact**
- Twitter/X: https://x.com/KaminoFinance
- Discord: https://discord.gg/kamino
- Email: `team@kamino.finance`

**Suggested ask**
- Ecosystem listing
- Co-tweet on launch
- Referral / points integration for deposits originating from Ilyon AI

**In return:** Kamino-first attribution for Solana vault opportunities surfaced to our users, case study on AI-driven vault discovery.

**Draft message**

> Subject: Ilyon AI — Kamino vaults in our Solana opportunity surface
>
> Hey Kamino team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Kamino is one of the core Solana protocols in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) — we surface Kamino lending and vault opportunities matched to user portfolios with direct CTAs to app.kamino.finance.
>
> Ask: a co-tweet on launch and, if Kamino has a referral / points layer for deposits from partner frontends, a conversation about wiring it into our CTA path. In return: Kamino-first attribution on matching surfaces and a case study on AI-driven vault discovery.
>
> — Griffin, Ilyon AI

---

## 26. Euler

**How we integrate**
- `src/defi/lending_analyzer.py` — Euler markets included with `docs_url=https://docs.euler.finance`

**Contact**
- Twitter/X: https://x.com/eulerfinance
- Discord: https://discord.gg/eulerfinance
- Email: `hello@euler.finance`

**Suggested ask**
- Ecosystem / integrations listing
- Co-tweet on launch

**In return:** Euler attribution on matching opportunities, case study on AI-driven opportunity surfacing with strong risk context (relevant given Euler's security story post-exploit).

**Draft message**

> Subject: Ilyon AI — Euler v2 surfaced with full risk context in our DeFi engine
>
> Hey Euler team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Euler is included in our DeFi opportunity engine (`src/defi/lending_analyzer.py`) and — important — we surface Euler opportunities with full risk context, not just headline APYs. Given Euler's post-exploit trust rebuild, an intelligence product that presents your protocol with honest risk framing is aligned with your positioning.
>
> Ask: a co-tweet on launch and ecosystem-directory inclusion if you run one. In return: Euler attribution with proper risk context, and a case study on how AI-layered intelligence products should present lending opportunities post-2023.
>
> — Griffin, Ilyon AI

---

# Tier 6 — Block Explorers

---

## 27. Solscan

**How we integrate**
- `src/chains/registry.py` — `explorer_url=https://solscan.io`, `explorer_api_url=https://api.solscan.io`
- Every wallet address, token, and transaction signature on ilyonai.com links to Solscan
- Whale feed, smart money hub, token analysis, portfolio — all deep-link to Solscan

**Contact**
- Partnerships: `business@solscan.io`
- Twitter/X: https://x.com/solscanofficial
- Telegram: https://t.me/solscanofficial

**Suggested ask**
- Partner Solscan API tier for richer wallet labeling / tag metadata
- Co-branded wallet-label data (we're an obvious consumer of Solscan's wallet tags and could contribute back)
- Ecosystem listing

**In return:** Every external link on Ilyon AI for a Solana address, token, or signature goes to Solscan by default (we don't split traffic with Solana.fm or SolanaBeach); prominent "View on Solscan" CTAs.

**Draft message**

> Subject: Ilyon AI — every Solana deep-link points to Solscan, let's talk wallet labels
>
> Hey Solscan team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Solscan is our default Solana explorer — every wallet address, token, and transaction signature on our platform deep-links to solscan.io (`src/chains/registry.py`, `src/api/routes/analysis.py`, and throughout). Whale feed, smart-money hub, portfolio — all point to you.
>
> Ask: a conversation about Solscan's partner API tier, specifically around wallet-label / tag metadata. We maintain our own whale wallet labeling internally and it's an obvious overlap — happy to explore contributing back labels we generate.
>
> In return: Solscan stays our exclusive Solana explorer (no split traffic to Solana.fm / SolanaBeach), and we'd like to be on any Solscan ecosystem-partner surface you run.
>
> — Griffin, Ilyon AI

---

## 28. Etherscan (and family: Basescan, Arbiscan, BscScan, Polygonscan, Optimistic Etherscan, Snowtrace)

**How we integrate**
- `src/contracts/scanner.py` — Contract source retrieval for our EVM contract scanner via seven explorer APIs:
  - `https://api.etherscan.io/api` (Ethereum)
  - `https://api.bscscan.com/api` (BSC)
  - `https://api.polygonscan.com/api` (Polygon)
  - `https://api.arbiscan.io/api` (Arbitrum)
  - `https://api.basescan.org/api` (Base)
  - `https://api-optimistic.etherscan.io/api` (Optimism)
  - `https://api.snowtrace.io/api` (Avalanche)
- `src/chains/base.py` and `src/api/routes/chains.py` — every EVM token analysis deep-links to the matching explorer
- Etherscan Multichain API now covers this via a single key — we can consolidate

**Contact**
- Etherscan Partnerships: https://etherscan.io/contactus (partnership form) or `partnerships@etherscan.io`
- Pro API / Multichain sales: https://etherscan.io/apis (Multichain API covers the whole family with one key)
- Twitter/X: https://x.com/etherscan

**Suggested ask**
- Etherscan Multichain API partner tier (preferred rate limits and the single-key simplification)
- Featured integration for the EVM-side of our product

**In return:** "Contract source via Etherscan" attribution on every contract scan result, deep-links to Etherscan family on every EVM address/token/tx.

**Draft message**

> Subject: Ilyon AI — seven Etherscan-family endpoints in our EVM contract scanner
>
> Hey Etherscan team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project with a multi-chain EVM surface. Our contract security scanner (`src/contracts/scanner.py`) retrieves verified source code across seven chains — Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche — via the Etherscan-family APIs. Every EVM token and contract analysis deep-links back to the appropriate explorer.
>
> Ask: a conversation about Etherscan Multichain API partner access. Consolidating our seven keys into one Multichain key with partner rate limits would meaningfully improve reliability, and we're a live user of all seven.
>
> In return: "Verified contract source via Etherscan" attribution on every contract scanner result, and Etherscan-family links stay our default (no traffic split to blockchair / other aggregators).
>
> — Griffin, Ilyon AI

---

# Tier 7 — AI Providers

---

## 29. xAI (Grok)

**How we integrate**
- `src/ai/grok_client.py` — Direct xAI API integration at `https://api.x.ai/v1/chat/completions`
- Grok is cited in the README as part of the multi-model analysis (GPT-4o + Grok) for token risk reasoning
- Used for specific analysis paths where Grok's real-time X-context knowledge adds value

**Contact**
- xAI API access: https://x.ai/api
- Sales / partnerships: via https://x.ai/contact
- Twitter/X: https://x.com/xai (announcements) and https://x.com/grok

**Suggested ask**
- xAI API credits for a Solana Frontier Hackathon build
- Visibility / retweet on Grok being used in production for crypto intelligence

**In return:** "Analysis powered by Grok" attribution where Grok's output is shown; public write-up on how Grok's X-native knowledge improves token-risk narratives (relevant for xAI's positioning vs. other LLMs).

**Draft message**

> Subject: Ilyon AI — Grok in production for crypto token analysis, asking about credits
>
> Hey xAI team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. We use Grok via `api.x.ai/v1/chat/completions` (`src/ai/grok_client.py`) as part of our multi-model token-risk analysis — specifically for paths where Grok's real-time X knowledge adds context that static LLMs can't (recent community sentiment on a token, surfaced scam campaigns, deployer wallet chatter).
>
> Ask: xAI API credits through Frontier. Token analysis is a natural fit for Grok's strength, and we're happy to be a production reference.
>
> In return: "Analysis powered by Grok" attribution on relevant output sections, and a public write-up on how Grok's X-native context improves token-risk narratives compared to static LLMs — strong differentiation content for xAI's positioning.
>
> — Griffin, Ilyon AI

---

## 30. Google DeepMind (Gemini)

**How we integrate**
- `requirements.txt` — `google-genai>=1.0.0` is a direct dependency
- Gemini routed via OpenRouter and/or direct SDK for specific analysis paths requiring large-context reasoning

**Contact**
- Google for Startups Cloud Program: https://cloud.google.com/startup
- Gemini API: https://ai.google.dev
- Partnerships: via Google for Startups application
- Twitter/X: https://x.com/GoogleDeepMind

**Suggested ask**
- Google for Startups Cloud Program ($25K–$100K credits tier)
- Gemini API early-access features

**In return:** Gemini attribution on relevant outputs, case study for Google's startup programme.

**Draft message**

> Subject: Ilyon AI — applying for Google for Startups, Gemini in our AI stack
>
> Hey Google for Startups / DeepMind team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Gemini is in our production AI stack via the `google-genai` SDK — we use it for large-context analysis paths (deep smart-contract audits, long deployer-history reasoning) where Gemini's context window outperforms smaller models.
>
> Ask: I'm applying for the Google for Startups Cloud Program — flagging here so you can match the context when the application lands. Live product, hackathon visibility, multi-model production AI pipeline with Gemini as a first-class participant.
>
> In return: Gemini attribution on relevant analysis output, plus a case study on multi-model AI routing in production — different angle from typical Google Cloud startup stories.
>
> — Griffin, Ilyon AI

---

## 31. OpenAI

**How we integrate**
- `src/ai/openai_client.py` — Direct OpenAI path at `https://api.openai.com/v1/chat/completions` (legacy route, now behind OpenRouter by default)
- `OPENAI_API_KEY` env var still supported for direct calls when needed
- GPT-4o referenced in README as part of the multi-model analysis

**Contact**
- OpenAI Startup Program: https://openai.com/form/startup-access
- API partnerships: `api@openai.com`
- Twitter/X: https://x.com/openai

**Suggested ask**
- OpenAI Startup Program credits ($2,500 tier via YC / hackathon programmes possible)

**In return:** GPT-4o attribution where used, case study contribution.

**Draft message**

> Subject: Ilyon AI — applying for OpenAI Startup Program
>
> Hey OpenAI team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. GPT-4o is one of the models in our multi-provider AI pipeline (`src/ai/openai_client.py`) for token-risk narrative generation and contract-vulnerability analysis. We currently route most traffic via OpenRouter and call OpenAI directly for specific paths that benefit from direct API access.
>
> Ask: consideration for the OpenAI Startup Program. Live product with real per-analysis inference costs, hackathon visibility, and a production use case for GPT-4o.
>
> In return: attribution on relevant outputs and a public case study.
>
> — Griffin, Ilyon AI

---

# Tier 8 — Monetization & Distribution

---

## 32. Trojan Bot

**How we integrate**
- `.env.example` → `TROJAN_REF` env var for the Trojan Bot affiliate code
- Every "Buy" CTA on Solana token analysis pages routes through Trojan Bot with our referral ID when configured
- Direct monetization path for our non-premium users

**Contact**
- Telegram: https://t.me/solana_trojanbot (primary contact — team runs support there)
- Referral programme: built into the bot (DM bot, request referral)
- Twitter/X: https://x.com/TrojanOnSolana

**Suggested ask**
- Elevated referral rev-share tier (their default is tiered by referred volume)
- Featured partner listing in any Trojan-promoted channels
- Co-promoted campaigns around token discovery via analysis → Trojan Bot buy flow

**In return:** Exclusive Trojan Bot routing for Solana buy CTAs (no split to BonkBot / Photon / GMGN), prominent co-branding on "Buy via Trojan" action buttons.

**Draft message**

> Subject: Ilyon AI — elevating Trojan Bot referral tier, live on Frontier
>
> Hey Trojan Bot team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. Trojan Bot is our Solana buy-flow — every "Buy" CTA on a Solana token analysis routes through Trojan with our referral ID (`TROJAN_REF` env). We're deliberate about this: one buy-bot, no split across competitors.
>
> Ask: a conversation about an elevated referral rev-share tier and any co-promoted campaigns you run with content / intelligence products. We drive exactly the user you want — someone who looked up a token, saw the risk analysis, and decided to buy anyway.
>
> In return: exclusive Solana buy routing through Trojan (no BonkBot / Photon / GMGN splits), prominent "Buy via Trojan" branding on our analysis pages.
>
> — Griffin, Ilyon AI

---

# Tier 9 — Security / Incident Data

---

## 33. REKT News

**How we integrate**
- `src/intel/rekt_database.py` — Curated incident dataset cross-referencing hacks and exploits; used to surface "related REKT incidents" on token and portfolio pages
- Data is complemented with DeFiLlama hacks API — but the REKT narrative (post-mortems, root-cause analysis) is what makes the context human-readable

**Contact**
- Twitter/X: https://x.com/RektHQ
- Website: https://rekt.news
- Email: `hello@rekt.news` (via site footer)

**Suggested ask**
- Permission to link directly to REKT articles from token analysis and portfolio-risk surfaces
- Cross-promotion on the incident-awareness angle
- Possible RSS / API arrangement for structured incident data

**In return:** Direct attribution and deep-links to REKT articles on every rendered incident, bringing their journalism to a new audience of live-trading users.

**Draft message**

> Subject: Ilyon AI — surfacing REKT incidents to traders, want to do it right
>
> Hey REKT team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. We surface related hack / exploit incidents on every token and portfolio view (`src/intel/rekt_database.py`) — users see an "REKT context" block when their holdings or the token they're analysing has a relevant past incident. The narrative layer (post-mortems, root-cause) is what makes this useful, and REKT's journalism is the primary source.
>
> Ask: the right way to deep-link to REKT articles — whether there's an official RSS / API surface we should hit, or a partnership where direct article links are encouraged.
>
> In return: prominent REKT attribution on every incident callout, direct "Read the full REKT post-mortem" CTA, and we'd happily tweet back credit on launch. Bringing REKT's work to live-trading users at the moment they're making decisions is a clean mutual win.
>
> — Griffin, Ilyon AI

---

## 34. Trust Wallet Assets

**How we integrate**
- `src/chains/base.py` — Token logos fetched from `https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/...`
- Every EVM token card on ilyonai.com uses the Trust Wallet asset registry as the logo source of truth

**Contact**
- GitHub: https://github.com/trustwallet/assets (contribution PRs are the primary channel)
- Trust Wallet partnerships: `partnerships@trustwallet.com`
- Twitter/X: https://x.com/TrustWallet

**Suggested ask**
- Contributing-partner acknowledgement if/when we submit asset PRs for tokens we analyze
- Listing as a Trust Wallet asset-registry consumer

**In return:** Continued use of Trust Wallet Assets as the authoritative logo source; active contribution of missing token assets we encounter.

**Draft message**

> Subject: Ilyon AI — Trust Wallet Assets is our EVM logo source of truth
>
> Hey Trust Wallet team,
>
> Griffin from Ilyon AI (https://ilyonai.com), live Solana Frontier Hackathon project. The Trust Wallet Assets registry is our primary source for EVM token logos — every EVM token card we render pulls from `raw.githubusercontent.com/trustwallet/assets` (`src/chains/base.py`).
>
> Ask: guidance on the best way to contribute back. We regularly encounter EVM tokens with missing or outdated entries in the registry — we have the metadata to contribute proper PRs and would like to do so under a consistent attribution.
>
> In return: Trust Wallet Assets stays our default logo source (no fallback to other registries), and we actively contribute PRs for missing tokens surfaced through our analyzer.
>
> — Griffin, Ilyon AI

---

## Outreach Sequencing Recommendation

**Week 1 (hackathon-adjacent, highest leverage):**
Helius · Jupiter · DexScreener · DeFiLlama · Solana Foundation · Dialect · OpenRouter

**Week 2 (wallets + security data):**
Phantom · Solflare · Backpack · RugCheck · GoPlus Labs

**Week 3 (DEX + lending ecosystem):**
Raydium · Orca · Meteora · Phoenix · Kamino · MarginFi · Solend · Aave · Morpho

**Week 4 (AI credits + monetization + rest):**
xAI · Google DeepMind · OpenAI · Moralis · CoinGecko · Trojan Bot · Solscan · Etherscan · Compound · Spark · Euler · REKT News · Trust Wallet

**Tracking.** Update the Status column at the top of this doc as outreach progresses (`Not sent` → `Sent YYYY-MM-DD` → `Responded` → `Partnered` / `Declined`). Keep a second private tracker with contact-specific notes.

---

_Last updated: 2026-04-20 — maintained by Griffin, Ilyon AI._
