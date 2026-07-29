# Ilyon v1 — Solana "Safe Trading Terminal" (web, chat-first): Build Spec

_Grounded in the real repo. Companion to `STRATEGY_PIVOT.md`. Written 2026-07-26._

Decisions locked: **Wedge A** (safe trading terminal, monetize the trade) · **Web chat first** · deliverables: build spec + free Rug-Score test + turn-on-revenue/stop-the-bleed.

---

## 0. Headline — how much already exists (the effort reality)

- **Hero loop legs 1 & 2 are fully built.** Pasting a token address in chat already routes to the Sentinel analysis and renders a rich safety card. The *only* real gap is a **Buy button on that card**.
- **Data runs at ~$0.** The token-safety path uses only free sources (DexScreener, RugCheck, public Solana RPC, DefiLlama, GeckoTerminal, CoinGecko free tier). Helius (the thing that keeps dying) is only wired into wallet/whale *extras* that are already fail-soft. One **free** Jupiter key is the only required registration.
- **Revenue is one config + ~3 line edits away.** The swap fee isn't "not monetizable" — it is **literally disabled in code** (`platformFeeBps` forced to `0`) and the fee account is empty.
- **The share/rug-card is mostly built** (Solana Blinks + a dynamic score-badge PNG already exist).

Net: this pivot is mostly **deletion + wiring + one Buy button + one share route**, not new building. Exactly the low-effort path you asked for.

---

## 1. The cut — strip to Solana-only, chat-first (file-level)

The tool registry lazy-imports EVM routing/adapters *inside functions*, so deleting EVM files does **not** break module load — EVM paths just become dead. That's what makes an aggressive cut safe.

### DELETE
- **EVM chain layer:** `src/chains/evm/`
- **EVM data:** `src/data/moralis.py`, `moralis_rotator.py`, `enso_token_resolver.py`
- **EVM/bridge routing:** `src/routing/{enso_client,debridge_client,lifi_client,socket_client}.py` (and gut `quote_service.py`, which imports them)
- **EVM DeFi adapters:** `src/defi/execution/adapters/{aave_v3,balancer,compound_v3,curve,enso_shortcut,erc4626,evm_lst,multicall_bundler,nexus_revoke,pendle_v2,uniswap_v2,uniswap_v2_zap,uniswap_v3_nft,uniswap_v4,claim_compound_composer}.py` (keep `solana_yield_builder.py`, `base.py`, `wallet_assistant.py`)
- **Account abstraction:** `src/aa/`, `src/auth/{biconomy_nexus,session_key_mirror,session_keys,smart_account,zerodev_kernel,ethereum}.py` (keep `solana_session.py`, `password.py`, `merge.py`)
- **AA/EVM routes:** `src/api/routes/{session_keys,eip7702_auth,plan_permit2,bridge_confirmed,debridge_webhook}.py`
- **Whale poller:** `src/services/whale_poller.py` (✅ already disabled by default this session)
- **Web left-panel pages:** `web/app/{dashboard,whales,smart-money,entity,shield,audits,activity,rekt,trending,contract,alerts,defi}/`
- **EVM wallet connectors:** `web/components/agent-app/wallets/metamask.ts`, `web/lib/wallets/metamask.ts`

### KEEP
Chat backend (`agent.py`, `simple_runtime.py`, swap/stake/analyze tools) · Jupiter swap (`solana-yield-builder/adapters/jupiter.js` + `crypto_agent.build_solana_swap`) · Sentinel scoring (`core/scorer.py`, `analyzer.py`, `routes/analysis.py`, `agents/sentinel.py`) · Phantom wallet · token/sentinel cards · `web/app/{agent,portfolio,analyze,token}`.

### TOUCH (edits, not deletes)
- `src/api/app.py` — remove the deleted `setup_*_routes` imports + calls in **both** `create_api_app()` (L202–233) and `setup_api_routes()` (L281–312).
- `src/main.py` — whale-poller block ✅ done; can drop the composed-plan/deBridge notifier block later.
- `src/chains/registry.py` — drop EVM registration.
- **`src/data/moralis.py` importers (must edit or Solana portfolio breaks):** `src/api/routes/portfolio.py` (L14, L123–160) and `src/agent/services.py` (L78–110) — guard/remove `MoralisClient`.
- `web/components/layout/nav-config.ts` (`navGroups` L27–63) — reduce to Chat + Portfolio (+ Settings); consumed by `sidebar.tsx` and `mobile-nav.tsx`.
- **Caveat:** `crypto_agent.py` is one 260KB monolith holding both EVM builders *and* `build_solana_swap` — do NOT delete it; the EVM funcs just become dead.

---

## 2. Data stack — run at ~$0 recurring

The analysis orchestrator (`analyzer._collect_solana_data`, analyzer.py:265) already fans out **only free-capable** calls. Per signal:

| Signal | Free source (already in repo) |
|---|---|
| Price / 24h / liquidity / volume / chart | **DexScreener** `get_token` (no key). Fallback: CoinGecko free + DefiLlama oracle. |
| New pairs / trending / gainers | DexScreener boosts+profiles+search (no key) |
| Mint / freeze authority | **public-RPC `getAccountInfo`** (`solana.get_onchain_data`) + RugCheck (cross-check) |
| LP lock % / rug score / risks | **RugCheck** `check_token` (no key) |
| Top-holder concentration | public-RPC `getTokenLargestAccounts` (top-20) — auto-activates when Helius key is removed |
| Honeypot / sellable | `honeypot.check` (Jupiter sell-quote — **free Jupiter key** + public-RPC simulate) |
| Deployer / rug / audit history | `rekt_database` (hardcoded + free DefiLlama hacks/protocols) |
| Metadata / symbol / logo | DexScreener + public-RPC mint account |

**Changes to go near-zero-cost:**
1. **Empty `HELIUS_API_KEY`/`HELIUS_API_KEYS`** → forces top-holders onto the free RPC path; DAS wallet/whale calls no-op (fail-soft). Token reports keep working. (Stops the "max usage reached" pain permanently.)
2. **Provision one FREE Jupiter key** (`JUPITER_API_KEY`, portal.jup.ag) — required since 2026-01-31 for honeypot + swaps. The one registration.
3. Fix the two unauthenticated Jupiter price calls (`solana.py:1144`, `stats.py:151`) — route via `JupiterClient` or the free DefiLlama oracle, else SOL price 401s and falls back to a hardcoded `200.0`.

**Bottom line: recurring data cost ≈ $0.** Helius is optional; Birdeye isn't used.

---

## 3. The hero loop — one gap

`paste token → Sentinel safety card → one-tap Buy.`

- **Leg 1 (analysis):** ✅ `POST /api/v1/analyze` → `TokenAnalyzer.analyze` → `TokenScorer.calculate` (verdict SAFE/CAUTION/RISKY/DANGEROUS/SCAM). Fully built.
- **Leg 2 (trigger from chat):** ✅ `detect_intent` has a **bare-address detector** (`simple_runtime.py:4510`): a lone Solana mint routes to `analyze_token_full_sentinel` → emits `sentinel_token_report` card → renders as `SentinelTokenReportCard` (score, verdict pills, security grid, holder bars, red/green flags). Fully built.
- **Leg 3 (Buy) — THE GAP:** the card has **no CTA**. Swap infra is fully built (`build_solana_swap` via Jupiter → `swap_quote`/`solana_swap_proposal` card → `MainApp.executeSolanaSwap` signs via Phantom). To wire:
  1. Thread `onBuy?(address)` through `CardRenderer` props → `SentinelTokenReportCard` → a **Buy button**.
  2. In `MainApp` (card renderer mount) pass `onBuy={(addr)=>send(\`swap 0.1 SOL to ${addr}\`)}` — use the **swap** form (buy-by-mint isn't parsed; `_detect_buy_intent` only accepts symbols and returns a clarification).
  3. Verify a **raw SPL mint as `token_out`** resolves through `wallet_swap.py` symbol resolution (add an is-address short-circuit if not). **Test with a live mint before shipping.**
  4. (Optional polish) an amount field on the card instead of a fixed 0.1 SOL; teach `_detect_buy_intent` to accept a mint so "buy `<mint>`" works in chat too.

**Effort: S.** One callback + one button + one verification.

---

## 4. Turn on revenue — the fee is DISABLED, here's the exact turn-on

There are two Jupiter paths; the **live** one (`build_solana_swap`, the tool the agent actually calls) **forces `platformFeeBps: 0`** and sends no `feeAccount` → **earns $0**. The other path (`_build_jupiter_swap_tx`) is 90% wired but its fee account is empty. `_PLATFORM_FEE_BPS = 50` (0.5%) already exists.

**How Jupiter fees work:** the Referral Program — one **Referral Account** (program `REFER4Zgmy…`), plus one **fee ATA per output mint**, owned by that referral account. Pass `platformFeeBps` on `/quote` and `feeAccount` (the output mint's fee ATA) on `/swap`. Fee is taken in the **output** token. *Must send both together — `platformFeeBps` without a valid `feeAccount` makes `/swap` hard-reject.*

**You provide (one-time, off-chain):**
1. A Solana wallet you control (pays rent for fee ATAs).
2. A **Jupiter Referral Account** (referral.jup.ag or `@jup-ag/referral-sdk initializeReferralAccount`) — save the pubkey.
3. A **fee ATA per output mint** you'll collect in — start with USDC, SOL/WSOL, USDT (`initializeReferralTokenAccount`) — save each pubkey.
4. Fee bps (50 = 0.5% is already the constant).

**Then I edit (live path — `crypto_agent.build_solana_swap`):**
- `crypto_agent.py:4815`: `"platformFeeBps": 0,` → `"platformFeeBps": _PLATFORM_FEE_BPS,`
- Delete `crypto_agent.py:4842` (`quote.pop("platformFee", None)`)
- `/swap` body (`4848–4852`): add `"feeAccount": <fee_ATA_for_output_mint>` via a `mint → fee ATA` lookup, with a guard (mints without a fee ATA fall back to `platformFeeBps 0` so they still swap).
- Config: add `"jupiter_fee_account"` back to `.env` `API_KEYS` (a per-mint lookup, not one static value).

**Effort: M** (mostly your one-time Jupiter Referral setup; the code is ~3 edits + a small mint→ATA map).

---

## 5. Free Rug-Score share test — mostly built, add generic-link sharing

Already exists: `/token/[address]` page with a **Share** button → `createBlink` → a Solana Actions URL + a **dynamic score-badge PNG** (`icon_generator.py`) + unfurl metadata. But it only unfurls in **Solana Action clients (Dialect/X Blinks)** — a link pasted in **Telegram/Discord/X gets only the site-wide OG** (no per-token preview; the page is `use client` with no `generateMetadata`).

**Add (to make it viral anywhere):**
1. `web/app/rug/[address]/page.tsx` — a **server** wrapper rendering the read-only safety card (no swap/Blink buttons) with `generateMetadata()` that fetches `/api/v1/analyze` and sets OG/Twitter title+desc+image.
2. `web/app/rug/[address]/opengraph-image.tsx` (next/og, 1200×630: symbol + score/100 + grade + verdict + color band) — OR reuse the existing `icon_generator.py` PNG via a new `GET /api/v1/og/{address}.png`.
3. Point the Share button at `{webapp_url}/rug/{address}`; keep the Blink as the wallet-native variant.

**This is the cheapest demand test** — ship it standalone, measure shares, then add Buy.

**Effort: M.**

---

## 6. Build order (fast, EV-first)

1. **Stop the bleed** ✅ whale poller off (pending deploy — VPS is down). Empty Helius keys, add free Jupiter key.
2. **Turn on revenue** (after you do the Jupiter Referral setup) — ~3 edits. Immediate money on existing volume.
3. **Buy button** on the Sentinel card (S) — completes the hero loop.
4. **The cut** — delete EVM + left-panel; slim nav to Chat + Portfolio. Big stability win.
5. **Free Rug-Score share route + OG image** (M) — the growth loop / demand test.
6. Polish: amount input, verdict-threshold single source of truth (`sentinel_features.py` and `scorer.py` disagree — pick one), copy tweaks.

---

## 7. Open decisions / inputs I need from you
- **Jupiter Referral Account + fee ATAs** — I can't create these (they need your keypair/signature). Do the one-time setup and give me the referral account + fee-ATA pubkeys; then revenue is ~3 edits.
- **Verdict thresholds disagree** (`sentinel_features.py` SAFE≥70 vs `scorer.py` SAFE≥80). Pick one source of truth so the chat card and share card match.
- **One-tap Buy default amount** (e.g. 0.1 SOL) and whether to add an amount field in v1.
- **Rug-Score share:** new `/rug/[address]` route vs. refactor `/token` — I recommend the new route (cleaner, no `use client` refactor).

## 8. Status
- ✅ Whale poller disabled (committed `3e583c18`, pushed) — **pending deploy: the VPS is currently unreachable (host/network outage; not a code issue). Reboot via Contabo if it doesn't self-recover; it'll deploy when back.**
