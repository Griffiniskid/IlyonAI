# Main Page Redesign — AI-First Landing Page

**Date**: 2026-04-26
**Status**: Approved for implementation
**Branch**: staging (safety checkpoint: `bd6d050`)

---

## 1. Problem Statement

The current main page (`/`) presents AISentinel as a "token and pool analyzer" — which is no longer the project's primary value proposition. The AI chat assistant (at `/agent/chat`) is now the strongest feature, combining natural language DeFi execution with the IlyonAI Sentinel scoring layer. The landing page must reflect this shift and draw users toward the AI assistant as the main entry point, while preserving the search functionality as a secondary/quick-access feature.

---

## 2. Goals

1. **Reposition the AI assistant as the hero feature** — visitors should immediately understand that AISentinel is an AI-powered DeFi trading assistant, not just a scanner.
2. **Preserve existing search functionality** — token/pool search must remain accessible but clearly secondary.
3. **Demonstrate AI depth** — show that the assistant does more than simple Q&A; it orchestrates complex multi-step transactions with visible reasoning chains.
4. **Maintain visual consistency** — reuse existing components, styling, and patterns from the AI chat (`MainApp.tsx`) and current landing page.
5. **Update metadata** — title, description, and keywords should reflect the AI assistant positioning.

---

## 3. Design

### 3.1 Hero Section

**Layout**: Two-column grid (lg:grid-cols-2), same structure as current.

**Left Column (Text)**:
- **Badge**: Inline-flex pill with Sparkles icon: `AI-Powered DeFi Assistant`
- **Headline**:
  ```
  Your Intelligent
  Crypto Trading
  <span class="text-emerald-400">AI Assistant</span>
  ```
- **Subheadline**: "Connect your wallet and trade with confidence. Ask anything in natural language — check balances, find best swap routes, track portfolios, bridge across chains, and get real-time market analysis. Our AI handles the complexity, you just say what you want."
- **CTA Buttons**:
  - Primary: `Open AI Chat` → links to `/agent/chat` (Button with MessageSquare icon)
  - Secondary: `Try Demo Query` → scrolls to reasoning visualization section
- **Trust Indicators** (3 pills):
  - `AI-Powered Trading`
  - `Multi-Chain Support`
  - `Non-Custodial Security`

**Right Column (Chat Preview)**:
- Replaces the current `TokenPreview` demo card.
- Shows an animated conversation cycling through 2-3 example scenarios every 8 seconds.
- Uses the exact message bubble styling from `MainApp.tsx`:
  - User bubbles: emerald gradient, right-aligned
  - AI bubbles: white/5 background, left-aligned
  - Reasoning steps: collapsible purple accordion (same as chat)
  - Structured outputs: swap preview cards, balance reports (same as chat)
- Scenarios to cycle:
  1. "Swap 0.5 SOL to USDC at best rate" → reasoning steps → swap preview card
  2. "What's my portfolio worth?" → reasoning steps → balance report
  3. "Bridge 1 ETH from Ethereum to Solana" → reasoning steps → bridge preview

---

### 3.2 "See The Mind" — AI Reasoning Visualization

**Layout**: Full-width section with `bg-card/30` background, py-24.

**Header**:
- Title: `See How Your AI Thinks`
- Subtitle: `Every request triggers a chain of intelligent decisions`

**Content**: A vertical, auto-animating reasoning chain. Two scenarios cycle every 12 seconds.

**Scenario A: Cross-Chain Bridge**
```
🔍 Parsing Intent
   "Bridge 1 ETH from Ethereum to Solana"
   → Source: Ethereum | Destination: Solana | Amount: 1 ETH

⚡ Querying deBridge DLN
   → Fetching optimal route...
   → Found: Ethereum → Solana via deBridge

📊 Calculating Economics
   → Bridge fee: 0.15%
   → Estimated time: ~45s
   → Min. received: 0.9985 ETH-equivalent on Solana

🔐 Building Transactions
   → Step 1: Approval tx for ETH spend
   → Step 2: Bridge deposit tx
   → Ready for wallet signature
```

**Scenario B: Best Yield Strategy**
```
💰 Analyzing Portfolio
   → Wallet: 0x1234...5678
   → Current holdings: 2.5 ETH, 500 USDC

📈 Scanning Markets
   → Querying active pools on Uniswap, Aave, Curve...
   → Top opportunity: Aave USDC lending @ 8.2% APY

🛡️ Risk Assessment
   → Protocol TVL: $2.1B ✓
   → Contract audited: CertiK ✓
   → Impermanent loss risk: N/A (lending)

⚡ Building Deposit
   → Approve USDC → Deposit to Aave
   → Transaction ready
```

**Visual Design**:
- Uses the existing reasoning step styling from `MainApp.tsx`:
  - `.step-think`: purple label (#A78BFA)
  - `.step-tool`: blue label (#60A5FA)
  - `.step-result`: green label (#10B981)
  - `.step-conclude`: emerald label (#34D399)
- Each step animates in with stagger (0.15s delay between steps)
- Active step has a pulsing dot (same as `.reasoning-live-step-dot`)
- Completed steps show a checkmark
- Container: glass card with `backdrop-blur`, same as existing cards

---

### 3.3 Quick Search Strip

**Layout**: Full-width band, `bg-card/30`, py-12, between reasoning section and How It Works.

**Content**:
- Left: `🔍 Analyze Any Token or Pool` label (text-lg font-semibold)
- Center: Compact search input (same Input component, h-12)
- Right: Chain selector pills (same ChainSelectorRow, compact mode — smaller pills)

**Behavior**: Identical to current search — type address/name, pick chain, get dropdown results, navigate on select.

---

### 3.4 How It Works

**Layout**: Same grid structure as current (md:grid-cols-3).

**Steps** (replacing current token-analysis flow):
1. **🔗 Connect Wallet** — "Link Phantom or MetaMask. We support Solana + major EVM networks in one app."
2. **💬 Ask the AI** — `Type naturally: "Swap 0.5 SOL to USDC at best rate" or "What's my portfolio worth today?"`
3. **⚡ Execute Instantly** — "Confirm the AI-generated transaction with one click. Fast, transparent, non-custodial."

**Visual**: Same step cards with large numbers, icons, and chevron arrows between them.

---

### 3.5 Stats Section

**Layout**: Same grid (grid-cols-2 md:grid-cols-4).

**Stats**:
- `Tokens Analyzed` → keep current
- `24h Trading Volume` → keep current
- `Multi-Chain TVL` → keep current
- `Safe Tokens` → keep current

*(Note: If "AI Conversations" metric is available from backend, replace one stat. Otherwise keep existing four.)*

---

### 3.6 CTA Section

**Layout**: Same glass card centered layout.

**Content**:
- Title: `Ready to Trade Smarter?`
- Subtitle: `Let AI handle the complexity. You just say what you want.`
- Primary CTA: `Open AI Chat` → `/agent/chat` (Button with MessageSquare icon)
- Secondary CTA: `View Trending` → `/trending`

---

### 3.7 Metadata Updates

**File**: `web/app/layout.tsx`

**Title**: `Ilyon AI | Your AI-Powered DeFi Trading Assistant`

**Description**: `AI-powered DeFi trading assistant across Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche. Ask in natural language to check balances, find swap routes, bridge assets, track portfolios, and analyze tokens — all from one chat interface.`

**Keywords**: Add `AI trading assistant`, `DeFi assistant`, `natural language trading`, `crypto AI`, `wallet assistant` to existing list.

---

## 4. Component Inventory

### New Components (to create)

| Component | Location | Purpose |
|-----------|----------|---------|
| `ChatPreview` | `web/app/page.tsx` (inline or `components/landing/`) | Animated chat conversation demo for hero right column |
| `ReasoningVisualization` | `web/app/page.tsx` (inline or `components/landing/`) | Auto-cycling reasoning chain for "See The Mind" section |

### Modified Components

| Component | Changes |
|-----------|---------|
| `web/app/page.tsx` | Complete rewrite of sections: hero text, replace TokenPreview with ChatPreview, replace Features grid with ReasoningVisualization, update How It Works steps, update CTA |
| `web/app/layout.tsx` | Update title, description, keywords |

### Reused Components/Patterns

| Source | Used For |
|--------|----------|
| `MainApp.tsx` message bubbles | ChatPreview styling |
| `MainApp.tsx` reasoning steps | ReasoningVisualization styling |
| `MainApp.tsx` swap preview cards | ChatPreview structured output examples |
| Existing `FeatureCard` | Not used (replaced by reasoning viz) |
| Existing `StatCard` | Stats section |
| Existing `ChainSelectorRow` | Quick Search Strip |
| Existing search logic | Quick Search Strip behavior |

---

## 5. Animation & Interaction Spec

### Hero Chat Preview
- **Auto-cycle**: Every 8 seconds, fade out current scenario, fade in next
- **Message typing**: Each message appears with a 0.3s fade-up animation (same as chat)
- **Reasoning accordion**: Auto-expands after message appears, shows steps with 0.15s stagger
- **Structured output**: Slides up after reasoning completes

### Reasoning Visualization
- **Auto-cycle**: Every 12 seconds, switch scenario
- **Step reveal**: Steps appear sequentially with 0.2s stagger, each with fade-up
- **Active step**: Pulsing purple dot (same as chat reasoning)
- **Completed step**: Green checkmark appears
- **Progress bar**: Thin emerald line at top showing overall progress through the chain

### Scroll Animations
- All sections use existing `animate-fade-in-up` class with appropriate delays
- Reasoning visualization triggers when scrolled into viewport (IntersectionObserver)

---

## 6. Responsive Behavior

- **Desktop (lg+)**: Full two-column hero, side-by-side reasoning steps
- **Tablet (md)**: Single column hero (text on top, chat preview below), reasoning steps stack vertically
- **Mobile**: All sections single column, chat preview simplified (shorter conversation), reasoning steps collapse to 2 visible at a time with scroll

---

## 7. Assets

No new image assets required. All visuals are code-generated:
- Chat bubbles: CSS + existing Tailwind classes
- Reasoning steps: CSS + Lucide icons
- Structured output cards: Reuse existing swap/balance card components

---

## 8. Accessibility

- All auto-cycling content has `aria-live="polite"` regions
- Pause on hover for chat preview and reasoning visualization
- Keyboard accessible: Tab through CTAs, Enter to pause animations
- Respect `prefers-reduced-motion`: disable auto-cycling, show static final state

---

## 9. Testing Checklist

- [ ] Hero renders correctly on desktop, tablet, mobile
- [ ] Chat preview cycles through all 3 scenarios
- [ ] Reasoning visualization cycles through both scenarios
- [ ] Search strip works identically to current search
- [ ] All CTAs link to correct routes
- [ ] Metadata updates reflect in page title and social previews
- [ ] Reduced motion preference respected
- [ ] No console errors or hydration mismatches

---

## 10. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Chat preview hydration mismatch | Mark as `"use client"`, use `useEffect` to start animations after mount |
| Performance from animations | Use CSS transitions only (no heavy JS), `will-change` on animated elements |
| Breaking existing search | Extract search logic into reusable hook, keep behavior identical |
| Mobile layout overflow | Test all breakpoints, ensure chat bubbles don't exceed viewport |

---

**Approved by**: Product Owner
**Next Step**: Invoke `writing-plans` skill to create implementation plan
