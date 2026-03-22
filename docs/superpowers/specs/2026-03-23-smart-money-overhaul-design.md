# Smart Money Overhaul — Design Spec

## Goal

Transform Smart Money from a vague dashboard of unlabeled numbers into a powerful intelligence tool that surfaces real wallet addresses, transaction context, behavioral signals, risk scoring, and entity clustering — making every page actually useful for tracking coordinated capital movements.

## Context

The backend already has real Helius API data (whale transactions with signatures, wallet addresses, token details, amounts, timestamps, DEX names) and analysis engines (behavior signals, forensics, entity graph). But the frontend barely surfaces any of it. Users see "Smart Money $44.3K" with no address, no chain, no context. The Flows page shows direction + amount with no wallet info. Wallet lookup only works if the wallet happens to be in the top 10 buyers/sellers snapshot.

## Non-Goals

- Building new external API integrations (we use what Helius/DexScreener already provide).
- Multi-chain whale tracking (Helius is Solana-only; EVM whale data requires Moralis integration which is out of scope).
- Persisting entity graph to database (in-memory is fine for now).

---

## Design

### 1. Smart Money Hub (`/smart-money`)

**Current state:** 4 metric cards (net flow, inflow, outflow, entity confidence), 5 top buyers/sellers showing only "Smart Money" + amount.

**New state:** A command center for capital flow intelligence.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Smart Money Hub                               [Refresh] [⟳] │
│ Track coordinated flows and entity-level capital movements  │
├──────────┬──────────┬──────────┬────────────────────────────┤
│ NET FLOW │ INFLOW   │ OUTFLOW  │ FLOW DIRECTION             │
│ -$250.4K │ $147.9K  │ $398.3K  │ 🔴 Distributing            │
│          │          │          │ Sells dominate (73% vol)   │
├──────────┴──────────┴──────────┴────────────────────────────┤
│                                                             │
│ TOP BUYERS                      TOP SELLERS                 │
│ ┌─────────────────────────┐     ┌─────────────────────────┐ │
│ │ 5tzF...uAi9 (Alameda)  │     │ HN7c...YWrH (Wintermute)│ │
│ │ SOL │ +$44.3K │ Jupiter │     │ SOL │ -$110.9K │ Raydium│ │
│ │ 3 txns │ 12m ago       │     │ 7 txns │ 8m ago         │ │
│ ├─────────────────────────┤     ├─────────────────────────┤ │
│ │ 9WzD...WWM (Jump)      │     │ 2AQd...icm (Circle)    │ │
│ │ SOL │ +$27.6K │ Raydium │     │ SOL │ -$67.0K │ Jupiter│ │
│ │ 1 txn │ 25m ago        │     │ 2 txns │ 15m ago        │ │
│ └─────────────────────────┘     └─────────────────────────┘ │
│                                                             │
│ RECENT TRANSACTIONS (last 20)                               │
│ ┌───────────────────────────────────────────────────────────┐│
│ │ 🟢 BUY  5tzF..uAi9  BONK  +$22.6K  Jupiter  12m ago   ││
│ │ 🔴 SELL HN7c..YWrH  SOL   -$41.3K  Raydium   8m ago   ││
│ │ 🟢 BUY  9WzD..WWM   JUP   +$19.0K  Jupiter  25m ago   ││
│ │ ...                                                      ││
│ └───────────────────────────────────────────────────────────┘│
│                                                             │
│ [Explore Flows →]  [Entity Explorer →]  [Wallet Lookup →]  │
│ Last updated: 9:41 PM • Auto-refreshes every 60s           │
└─────────────────────────────────────────────────────────────┘
```

**Changes needed:**

**Backend (`src/api/routes/smart_money.py`):**
- Include `wallet_address` (truncated for display, full for links) in top_buyers/top_sellers — already returned but frontend ignores it.
- Add `flow_direction` field derived from behavior signals ("accumulating", "distributing", "mixed", "neutral").
- Add `sell_volume_percent` field (outflow / (inflow + outflow) * 100).
- Add `transaction_count` per buyer/seller (count of their transactions in the window).
- Add `last_seen` per buyer/seller (most recent transaction timestamp).
- Add `token_symbol` and `dex_name` to top_buyers/top_sellers (from their largest transaction).
- Return `recent_transactions` array (last 20 raw transactions with full detail) — already available from `flows` but with proper field names.

**Frontend (`web/app/smart-money/page.tsx`):**
- Display wallet addresses (truncated, clickable → `/wallet/{address}`).
- Show known labels as badges (Alameda, Jump Trading, Wintermute, Circle).
- Show chain badge, token symbol, DEX name per buyer/seller.
- Show transaction count and last seen time per buyer/seller.
- Add "Recent Transactions" table below buyers/sellers showing the raw feed.
- Replace "Entity Confidence" card with "Flow Direction" indicator.
- Auto-refresh every 60 seconds.

### 2. Flows Page (`/flows`)

**Current state:** Unlabeled direction + amount cards with chain filters that don't work (backend is Solana-only).

**New state:** Rich transaction feed with wallet context.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Capital Flows                                    [Refresh]  │
│ Real-time smart money transaction feed                      │
├─────────────────────────────────────────────────────────────┤
│ Filters: [All ▼] [Min $1,000 ▼] [Buys|Sells|All]          │
│ Summary: 32 buys ($485K) • 18 sells ($312K) • Net +$173K   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 🟢 BUY   5tzF..uAi9 (Alameda)                              │
│    BONK → +$22,600 (45.2M tokens)                           │
│    Jupiter • Solana • tx: 3xKp...mN7z • 12 min ago          │
│                                                             │
│ 🔴 SELL  HN7c..YWrH (Wintermute)                            │
│    SOL → -$41,300 (182.5 SOL)                                │
│    Raydium • Solana • tx: 7yRq...bK2w • 8 min ago           │
│                                                             │
│ 🟢 BUY   Unknown Wallet (9WzD..WWM)                        │
│    JUP → +$19,000 (3,200 tokens)                            │
│    Jupiter • Solana • tx: 2mLp...xN4v • 25 min ago          │
│                                                             │
│ ... (paginated, 50 per page)                                │
└─────────────────────────────────────────────────────────────┘
```

**Changes needed:**

**Backend (`src/api/routes/smart_money.py`):**
- Enrich `flows` array to include full transaction fields: `wallet_address`, `wallet_label`, `token_symbol`, `token_name`, `token_address`, `amount_tokens`, `amount_usd`, `dex_name`, `signature`, `timestamp`, `chain`.
- These fields are already available in the whale transaction data — they're just stripped when building the flows response.

**Frontend (`web/app/flows/page.tsx`):**
- Rewrite to display rich transaction cards (not just direction + amount).
- Show wallet address (truncated, linked to `/wallet/{address}`).
- Show wallet label badge if known.
- Show token symbol, amount in tokens AND USD.
- Show DEX name, chain badge, explorer link (Solscan), relative timestamp.
- Add summary bar: total buys count + volume, total sells count + volume, net flow.
- Remove non-functional chain filters (keep only "Solana" for now, add others when backend supports them).
- Filter by buy/sell type and minimum amount.

### 3. Whale Tracker (`/whales`)

**Current state:** Functional but basic. Shows transactions with token, amount, wallet (truncated), and explorer link. Missing wallet context and behavioral signals.

**New state:** Enhanced with behavior context and better wallet identification.

**Changes needed (frontend only — backend already returns this data):**

- Add chain badge per transaction (currently hardcoded to Solscan links).
- Show wallet label badge when known (Alameda, Jump, etc.).
- Add behavior summary section at top when filtering by token: flow direction, concentration score, stickiness score, anomaly flags.
- Show anomaly flag badges on individual transactions when available.
- Make wallet addresses clickable → `/wallet/{address}`.
- Add token logo (from logo_url if available).

### 4. Wallet Lookup (`/wallet/[address]`)

**Current state:** Only works if wallet is in top_buyers/top_sellers snapshot. Shows "coming soon" placeholders for activity and forensics.

**New state:** Full wallet intelligence page for any address.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Wallet: 5tzF...uAi9                    [Copy] [Explorer ↗] │
│ Label: Alameda Research                                     │
├──────────┬──────────┬──────────┬───────────────────────────┤
│ RISK     │ VOLUME   │ TXNS     │ ENTITY                    │
│ 🟢 CLEAN │ $44.3K   │ 3        │ entity-a1b2c3d4          │
│ Score:92 │ (30 day) │ (30 day) │ 4 linked wallets          │
├──────────┴──────────┴──────────┴───────────────────────────┤
│                                                             │
│ RECENT TRANSACTIONS                                         │
│ 🟢 BUY  BONK  +$22.6K  Jupiter  12m ago                   │
│ 🟢 BUY  JUP   +$19.0K  Jupiter  25m ago                   │
│ 🔴 SELL SOL   -$15.2K  Raydium  1h ago                    │
│                                                             │
│ FORENSICS                                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Tokens Deployed: 0 │ Rugged: 0 │ Rug Rate: 0%         │ │
│ │ Patterns: None detected                                 │ │
│ │ Funding Risk: Low (0.12)                                │ │
│ │ Confidence: 85%                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ LINKED WALLETS (via entity-a1b2c3d4)                       │
│ 9WzD...WWM • HN7c...YWrH • 2AQd...icm                    │
│ Reason: Flow-based clustering                               │
└─────────────────────────────────────────────────────────────┘
```

**Changes needed:**

**Backend — New endpoint: `GET /api/v1/wallets/{address}/profile`**
- Aggregate data from multiple sources:
  1. GraphStore: entity ID, linked wallets, link reason
  2. Whale transactions: recent transactions for this wallet (filter from whale feed)
  3. Known whales: label if available
- Return: `{ wallet, label, entity_id, linked_wallets, link_reason, recent_transactions, volume_usd, transaction_count }`

**Backend — New endpoint: `GET /api/v1/wallets/{address}/forensics`**
- Call `WalletForensicsEngine.analyze_wallet(address)`.
- Return: `{ risk_level, reputation_score, tokens_deployed, rugged_tokens, rug_percentage, patterns_detected, pattern_severity, funding_risk, confidence, evidence_summary }`

**Frontend (`web/app/wallet/[address]/page.tsx`):**
- Rewrite to call both new endpoints.
- Display risk score with color-coded badge (CLEAN=green, LOW=blue, MEDIUM=yellow, HIGH=orange, CRITICAL=red).
- Show recent transactions list (same rich format as Flows page).
- Show forensics section: deployment stats, patterns, funding risk.
- Show linked wallets section if entity exists.
- Handle any wallet address, not just those in the smart money snapshot.

### 5. Entity Pages (`/entity`, `/entity/[id]`)

**Current state:** Entity list page fetches from API but entities are never populated. Detail page shows wallets + reason but has no data.

**Changes needed:**

**Backend (`src/api/routes/smart_money.py` or `entity.py`):**
- Auto-populate GraphStore entities from whale transaction analysis: group wallets that trade the same tokens in coordinated patterns.
- Simple heuristic for MVP: wallets that appear in both top_buyers and top_sellers within the same time window get linked as "coordinated trading".
- On startup or when smart money overview is refreshed, run entity linking.

**Frontend (`web/app/entity/page.tsx`):**
- Keep existing list + search UI.
- Add wallet count and reason badges.
- If no entities exist, show explanatory message: "Entity clusters are built from whale transaction patterns. Check back after the system has observed coordinated activity."

**Frontend (`web/app/entity/[id]/page.tsx`):**
- Keep existing detail page.
- Add total volume across all linked wallets.
- Add recent transactions from all linked wallets (merged, sorted by time).

---

## Files Changed

### Backend
| File | Change |
|------|--------|
| `src/api/routes/smart_money.py` | Enrich overview response with full transaction fields, flow direction, per-wallet stats |
| `src/api/routes/wallet.py` (new) | New wallet profile + forensics endpoints |
| `src/api/app.py` | Register new wallet routes |
| `src/api/routes/entity.py` | Add entity auto-population on overview refresh |

### Frontend
| File | Change |
|------|--------|
| `web/app/smart-money/page.tsx` | Full rewrite — wallet addresses, labels, behavior, transaction feed |
| `web/app/flows/page.tsx` | Full rewrite — rich transaction cards with full context |
| `web/app/whales/page.tsx` | Enhance with labels, chain badges, behavior summary |
| `web/app/wallet/[address]/page.tsx` | Full rewrite — profile, transactions, forensics, entity links |
| `web/app/entity/page.tsx` | Minor improvements, empty state messaging |
| `web/app/entity/[id]/page.tsx` | Add volume and merged transaction feed |
| `web/lib/api.ts` | Add wallet profile + forensics API functions |
| `web/lib/hooks.ts` | Add useWalletProfile, useWalletForensics hooks |
| `web/types/index.ts` | Add WalletProfile, ForensicsResult types |

## Testing

- Smart Money Hub displays wallet addresses, labels, transaction counts, and timestamps.
- Flows page shows full transaction details with wallet, token, amount, DEX, explorer link.
- Wallet lookup works for ANY address (not just those in the smart money snapshot).
- Wallet forensics section shows risk scoring and pattern detection.
- Entity list populates after smart money overview refresh.
- Whale tracker shows chain badges and wallet labels.
- All existing tests continue to pass.
