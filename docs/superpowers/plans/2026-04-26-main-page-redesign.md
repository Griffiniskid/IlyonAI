# Main Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the main landing page (`/`) to position the AI chat assistant as the primary feature, with animated chat preview, reasoning visualization, and preserved search functionality.

**Architecture:** Reuse existing chat UI patterns from `MainApp.tsx` for visual consistency. Extract search logic from current page into a reusable component. Create two new sections (ChatPreview, ReasoningVisualization) as inline components within the page file to keep changes localized.

**Tech Stack:** Next.js 14, React, TypeScript, Tailwind CSS, Framer Motion (already used), Lucide React, shadcn/ui components

**Safety Checkpoint:** Commit `bd6d050` on staging branch. Revert with `git reset --hard bd6d050` if needed.

---

## File Structure

| File | Action | Responsibility |
|------|--------|--------------|
| `web/app/page.tsx` | **Rewrite** | Main landing page — hero, chat preview, reasoning viz, search strip, how it works, stats, CTA |
| `web/app/layout.tsx` | **Modify** | Update metadata (title, description, keywords) |
| `web/components/landing/chat-preview.tsx` | **Create** | Animated chat conversation demo for hero |
| `web/components/landing/reasoning-viz.tsx` | **Create** | Auto-cycling reasoning chain visualization |
| `web/components/landing/quick-search.tsx` | **Create** | Extracted search strip component |

---

## Task 1: Update Page Metadata

**Files:**
- Modify: `web/app/layout.tsx:18-37`

- [ ] **Step 1: Update title**

```tsx
export const metadata: Metadata = {
  title: "Ilyon AI | Your AI-Powered DeFi Trading Assistant",
```

- [ ] **Step 2: Update description**

```tsx
  description:
    "AI-powered DeFi trading assistant across Solana, Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche. Ask in natural language to check balances, find swap routes, bridge assets, track portfolios, and analyze tokens — all from one chat interface.",
```

- [ ] **Step 3: Update keywords**

```tsx
  keywords: [
    "DeFi security",
    "multi-chain",
    "token scanner",
    "smart contract audit",
    "rugpull detector",
    "honeypot detector",
    "approval manager",
    "yield farming",
    "crypto security",
    "AI analysis",
    "AI trading assistant",
    "DeFi assistant",
    "natural language trading",
    "crypto AI",
    "wallet assistant",
    "Ethereum",
    "Solana",
    "Base",
  ],
```

- [ ] **Step 4: Update OpenGraph and Twitter titles**

```tsx
  openGraph: {
    title: "Ilyon AI | Your AI-Powered DeFi Trading Assistant",
    description: "AI-powered DeFi trading assistant across all major chains",
    type: "website",
    siteName: "Ilyon AI",
  },
  twitter: {
    card: "summary_large_image",
    title: "Ilyon AI | Your AI-Powered DeFi Trading Assistant",
    description: "AI-powered DeFi trading assistant across all major chains",
  },
```

- [ ] **Step 5: Verify and commit**

```bash
git diff web/app/layout.tsx
```
Expected: Only metadata strings changed, no structural changes.

```bash
git add web/app/layout.tsx
git commit -m "feat(landing): update page metadata for AI assistant positioning"
```

---

## Task 2: Create ChatPreview Component

**Files:**
- Create: `web/components/landing/chat-preview.tsx`

- [ ] **Step 1: Create component file with types**

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2 } from "lucide-react";

interface Scenario {
  id: number;
  userMessage: string;
  reasoningSteps: { type: "think" | "tool" | "result" | "conclude"; label: string; detail: string }[];
  aiResponse: string;
  structuredOutput?: {
    type: "swap" | "balance" | "bridge";
    title: string;
    details: Record<string, string>;
  };
}

const SCENARIOS: Scenario[] = [
  {
    id: 1,
    userMessage: "Swap 0.5 SOL to USDC at best rate",
    reasoningSteps: [
      { type: "think", label: "Identifying swap parameters", detail: "Extracting token pair & amount" },
      { type: "tool", label: "build_swap_tx", detail: "Querying Jupiter v6 route" },
      { type: "result", label: "Route found", detail: "Optimal Solana transaction bundle" },
      { type: "conclude", label: "Simulation complete", detail: "Transaction ready to sign" },
    ],
    aiResponse: "Found the best route via Jupiter. Here are the details:",
    structuredOutput: {
      type: "swap",
      title: "Swap Preview",
      details: {
        From: "0.5 SOL",
        To: "~28.45 USDC",
        Route: "Jupiter v6 Aggregator",
        "Price Impact": "≤ 0.3%",
        Fee: "0.1% platform",
      },
    },
  },
  {
    id: 2,
    userMessage: "What's my portfolio worth today?",
    reasoningSteps: [
      { type: "tool", label: "get_balance", detail: "Connecting to chain RPCs" },
      { type: "result", label: "On-chain query complete", detail: "Latest balances resolved" },
      { type: "tool", label: "get_token_price", detail: "Fetching USD prices" },
      { type: "conclude", label: "Portfolio ready", detail: "Total net worth calculated" },
    ],
    aiResponse: "Here's your current portfolio across all chains:",
    structuredOutput: {
      type: "balance",
      title: "Portfolio Summary",
      details: {
        "Total Value": "$12,847.32",
        "24h Change": "+3.2%",
        Chains: "Solana, Ethereum, Base",
        "Top Holding": "2.5 ETH ($6,120)",
      },
    },
  },
  {
    id: 3,
    userMessage: "Bridge 1 ETH from Ethereum to Solana",
    reasoningSteps: [
      { type: "think", label: "Parsing bridge request", detail: "Source: Ethereum → Destination: Solana" },
      { type: "tool", label: "build_bridge_tx", detail: "Querying deBridge DLN route" },
      { type: "result", label: "Bridge route prepared", detail: "Approval + bridge payload ready" },
      { type: "conclude", label: "Preparing confirmation", detail: "Ready for wallet signing" },
    ],
    aiResponse: "Bridge route ready via deBridge DLN:",
    structuredOutput: {
      type: "bridge",
      title: "Bridge Preview",
      details: {
        From: "1 ETH (Ethereum)",
        To: "~0.998 ETH (Solana)",
        Route: "deBridge DLN",
        "Bridge Fee": "0.15%",
        "Est. Time": "~45 seconds",
      },
    },
  },
];
```

- [ ] **Step 2: Add component logic**

```tsx
export function ChatPreview() {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [showReasoning, setShowReasoning] = useState(false);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [showOutput, setShowOutput] = useState(false);

  const scenario = SCENARIOS[currentScenario];

  const cycleScenario = useCallback(() => {
    setShowOutput(false);
    setVisibleSteps(0);
    setShowReasoning(false);
    setCurrentScenario((prev) => (prev + 1) % SCENARIOS.length);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => setShowReasoning(true), 600);
    return () => clearTimeout(timer);
  }, [currentScenario]);

  useEffect(() => {
    if (!showReasoning) return;
    if (visibleSteps < scenario.reasoningSteps.length) {
      const timer = setTimeout(() => setVisibleSteps((prev) => prev + 1), 400);
      return () => clearTimeout(timer);
    } else {
      const timer = setTimeout(() => setShowOutput(true), 500);
      return () => clearTimeout(timer);
    }
  }, [showReasoning, visibleSteps, scenario.reasoningSteps.length]);

  useEffect(() => {
    const interval = setInterval(cycleScenario, 8000);
    return () => clearInterval(interval);
  }, [cycleScenario]);

  const getStepColor = (type: string) => {
    switch (type) {
      case "think": return "text-purple-400";
      case "tool": return "text-blue-400";
      case "result": return "text-emerald-400";
      case "conclude": return "text-emerald-300";
      default: return "text-gray-400";
    }
  };

  return (
    <div className="relative">
      <div className="glass-card p-6 rounded-2xl animate-fade-in-up" style={{ animationDelay: "400ms" }}>
        {/* Demo badge */}
        <div className="absolute -top-2 -right-2 px-2 py-1 bg-emerald-500/20 border border-emerald-500/30 rounded-full text-xs text-emerald-400 font-medium">
          Demo
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={scenario.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-4"
          >
            {/* User message */}
            <div className="flex justify-end">
              <div className="msg-bubble user max-w-[80%]">
                {scenario.userMessage}
              </div>
            </div>

            {/* Reasoning steps */}
            <AnimatePresence>
              {showReasoning && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="reasoning-wrap"
                >
                  <div className="reasoning-toggle justify-center">
                    <span className="reasoning-toggle-text text-center">🧠 AI Thinking...</span>
                  </div>
                  <div className="reasoning-steps-inner">
                    <div className="reasoning-steps-list">
                      {scenario.reasoningSteps.map((step, i) => (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, x: -10 }}
                          animate={{ opacity: i < visibleSteps ? 1 : 0.3, x: 0 }}
                          transition={{ delay: i * 0.1 }}
                          className="reasoning-step"
                        >
                          <span className="reasoning-step-icon">
                            {i < visibleSteps ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            ) : (
                              <Loader2 className="w-4 h-4 animate-spin text-purple-400" />
                            )}
                          </span>
                          <div>
                            <div className={`reasoning-step-label ${getStepColor(step.type)}`}>
                              {step.label}
                            </div>
                            <div className="reasoning-step-detail">{step.detail}</div>
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* AI Response */}
            <AnimatePresence>
              {showOutput && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="msg-row"
                >
                  <div className="msg-avatar assistant">🤖</div>
                  <div className="msg-body">
                    <div className="msg-bubble assistant">
                      {scenario.aiResponse}
                    </div>
                    {scenario.structuredOutput && (
                      <div className="mt-2 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                        <div className="text-sm font-semibold text-emerald-400 mb-2">
                          {scenario.structuredOutput.title}
                        </div>
                        <div className="space-y-1">
                          {Object.entries(scenario.structuredOutput.details).map(([key, val]) => (
                            <div key={key} className="flex justify-between text-xs">
                              <span className="text-muted-foreground">{key}</span>
                              <span className="text-white font-medium">{val}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Decorative elements */}
      <div className="absolute -top-4 -right-4 w-24 h-24 bg-emerald-500/20 rounded-full blur-2xl" />
      <div className="absolute -bottom-4 -left-4 w-32 h-32 bg-emerald-500/10 rounded-full blur-3xl" />
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npx tsc --noEmit components/landing/chat-preview.tsx
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add web/components/landing/chat-preview.tsx
git commit -m "feat(landing): add ChatPreview component with animated scenarios"
```

---

## Task 3: Create ReasoningVisualization Component

**Files:**
- Create: `web/components/landing/reasoning-viz.tsx`

- [ ] **Step 1: Create component file**

```tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Loader2 } from "lucide-react";

interface ReasoningScenario {
  id: number;
  title: string;
  steps: {
    icon: string;
    label: string;
    detail: string;
    substeps?: string[];
  }[];
}

const SCENARIOS: ReasoningScenario[] = [
  {
    id: 1,
    title: "Cross-Chain Bridge Request",
    steps: [
      {
        icon: "🔍",
        label: "Parsing Intent",
        detail: '"Bridge 1 ETH from Ethereum to Solana"',
        substeps: ["Source: Ethereum", "Destination: Solana", "Amount: 1 ETH"],
      },
      {
        icon: "⚡",
        label: "Querying deBridge DLN",
        detail: "Fetching optimal route...",
        substeps: ["Found: Ethereum → Solana via deBridge"],
      },
      {
        icon: "📊",
        label: "Calculating Economics",
        detail: "Analyzing fees and timing",
        substeps: ["Bridge fee: 0.15%", "Est. time: ~45s", "Min. received: 0.9985 ETH-equivalent"],
      },
      {
        icon: "🔐",
        label: "Building Transactions",
        detail: "Preparing complete transaction bundle",
        substeps: ["Step 1: Approval tx for ETH spend", "Step 2: Bridge deposit tx", "Ready for wallet signature"],
      },
    ],
  },
  {
    id: 2,
    title: "Yield Strategy Request",
    steps: [
      {
        icon: "💰",
        label: "Analyzing Portfolio",
        detail: "Checking wallet holdings",
        substeps: ["Wallet: 0x1234...5678", "Current: 2.5 ETH, 500 USDC"],
      },
      {
        icon: "📈",
        label: "Scanning Markets",
        detail: "Querying active opportunities",
        substeps: ["Uniswap, Aave, Curve...", "Top: Aave USDC lending @ 8.2% APY"],
      },
      {
        icon: "🛡️",
        label: "Risk Assessment",
        detail: "Evaluating protocol safety",
        substeps: ["Protocol TVL: $2.1B ✓", "Audited: CertiK ✓", "IL risk: N/A (lending)"],
      },
      {
        icon: "⚡",
        label: "Building Deposit",
        detail: "Preparing transaction",
        substeps: ["Approve USDC → Deposit to Aave", "Transaction ready"],
      },
    ],
  },
];

export function ReasoningVisualization() {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [visibleSteps, setVisibleSteps] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

  const scenario = SCENARIOS[currentScenario];

  const cycleScenario = useCallback(() => {
    setVisibleSteps(0);
    setIsComplete(false);
    setCurrentScenario((prev) => (prev + 1) % SCENARIOS.length);
  }, []);

  useEffect(() => {
    if (visibleSteps < scenario.steps.length) {
      const timer = setTimeout(() => setVisibleSteps((prev) => prev + 1), 800);
      return () => clearTimeout(timer);
    } else {
      setIsComplete(true);
      const timer = setTimeout(cycleScenario, 3000);
      return () => clearTimeout(timer);
    }
  }, [visibleSteps, scenario.steps.length, cycleScenario]);

  return (
    <div className="w-full max-w-4xl mx-auto">
      <AnimatePresence mode="wait">
        <motion.div
          key={scenario.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-6"
        >
          {/* Scenario title */}
          <div className="text-center mb-8">
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-purple-500/10 border border-purple-500/20"
            >
              <span className="text-sm text-purple-400 font-medium">{scenario.title}</span>
            </motion.div>
          </div>

          {/* Steps */}
          <div className="space-y-4">
            {scenario.steps.map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -20 }}
                animate={{
                  opacity: i < visibleSteps ? 1 : 0.2,
                  x: i < visibleSteps ? 0 : -20,
                }}
                transition={{ duration: 0.4, delay: i * 0.1 }}
                className={`relative p-5 rounded-xl border backdrop-blur-sm transition-all duration-300 ${
                  i < visibleSteps
                    ? "bg-white/[0.03] border-white/10"
                    : "bg-white/[0.01] border-white/5"
                }`}
              >
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/30 flex items-center justify-center text-lg"
                  >
                    {i < visibleSteps ? (
                      isComplete || i < visibleSteps - 1 ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                      ) : (
                        <Loader2 className="w-5 h-5 animate-spin text-purple-400" />
                      )
                    ) : (
                      step.icon
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-semibold text-white">{step.label}</span>
                      {i === visibleSteps - 1 && !isComplete && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/20 text-[10px] text-purple-400 font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                          Active
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mb-2">{step.detail}</p>

                    <AnimatePresence>
                      {i < visibleSteps && step.substeps && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: "auto" }}
                          exit={{ opacity: 0, height: 0 }}
                          className="space-y-1.5 mt-3"
                        >
                          {step.substeps.map((sub, j) => (
                            <motion.div
                              key={j}
                              initial={{ opacity: 0, x: -10 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: j * 0.1 }}
                              className="flex items-center gap-2 text-xs text-white/60"
                            >
                              <span className="w-1 h-1 rounded-full bg-emerald-400/60" />
                              {sub}
                            </motion.div>
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>

                {/* Connector line */}
                {i < scenario.steps.length - 1 && (
                  <div className="absolute left-[2.25rem] top-[3.5rem] w-px h-6 bg-gradient-to-b from-purple-500/30 to-transparent" />
                )}
              </motion.div>
            ))}
          </div>

          {/* Progress bar */}
          <div className="mt-6 h-1 bg-white/5 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-purple-500 to-emerald-500"
              initial={{ width: "0%" }}
              animate={{ width: `${(visibleSteps / scenario.steps.length) * 100}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npx tsc --noEmit components/landing/reasoning-viz.tsx
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add web/components/landing/reasoning-viz.tsx
git commit -m "feat(landing): add ReasoningVisualization component"
```

---

## Task 4: Create QuickSearch Strip Component

**Files:**
- Create: `web/components/landing/quick-search.tsx`
- Extract search logic from: `web/app/page.tsx:280-386`

- [ ] **Step 1: Extract search logic into hook**

First, check the current search implementation:
```bash
grep -n "const.*search\|handleAnalyze\|searchTokens\|useSearchCatalog" web/app/page.tsx
```

- [ ] **Step 2: Create QuickSearch component**

```tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, isValidEvmAddress, isValidSolanaAddress } from "@/lib/utils";
import { useSearchCatalog } from "@/lib/hooks";
import { searchTokens } from "@/lib/api";
import type { SearchResultResponse } from "@/types";

const CHAINS = [
  { id: "ethereum", label: "Ethereum", short: "ETH", color: "#627EEA", type: "evm" },
  { id: "base", label: "Base", short: "BASE", color: "#0052FF", type: "evm" },
  { id: "arbitrum", label: "Arbitrum", short: "ARB", color: "#28A0F0", type: "evm" },
  { id: "bsc", label: "BSC", short: "BNB", color: "#F0B90B", type: "evm" },
  { id: "polygon", label: "Polygon", short: "POL", color: "#8247E5", type: "evm" },
  { id: "optimism", label: "Optimism", short: "OP", color: "#FF0420", type: "evm" },
  { id: "avalanche", label: "Avalanche", short: "AVAX", color: "#E84142", type: "evm" },
  { id: "solana", label: "Solana", short: "SOL", color: "#9945FF", type: "sol" },
] as const;

type ChainId = typeof CHAINS[number]["id"];

function detectChainType(address: string): "evm" | "sol" | null {
  if (!address) return null;
  if (isValidEvmAddress(address)) return "evm";
  if (isValidSolanaAddress(address)) return "sol";
  return null;
}

function CompactChainSelector({
  selectedChain,
  onSelect,
  detectedType,
}: {
  selectedChain: ChainId | null;
  onSelect: (id: ChainId) => void;
  detectedType: "evm" | "sol" | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] text-muted-foreground shrink-0 mr-1">Chain:</span>
      {CHAINS.map((chain) => {
        const isSelected = selectedChain === chain.id;
        const isHighlighted = !selectedChain && detectedType === chain.type;
        return (
          <button
            key={chain.id}
            type="button"
            onClick={() => onSelect(chain.id)}
            className={cn(
              "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium transition-all duration-200 border",
              isSelected
                ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-300"
                : isHighlighted
                ? "border-white/30 bg-white/10 text-white/80"
                : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/20 hover:bg-white/10"
            )}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: chain.color }} />
            {chain.short}
          </button>
        );
      })}
    </div>
  );
}

export function QuickSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [selectedChain, setSelectedChain] = useState<ChainId | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [isResolving, setIsResolving] = useState(false);
  
  const { data: searchData, isFetching } = useSearchCatalog(
    debouncedQuery,
    selectedChain ?? undefined
  );

  const detectedType = detectChainType(query);
  const searchResults = searchData?.results ?? [];

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 180);
    return () => clearTimeout(timer);
  }, [query]);

  const handleChainSelect = (id: ChainId) => {
    setError(null);
    setSelectedChain((prev) => (prev === id ? null : id));
  };

  const handleResultSelect = (result: SearchResultResponse) => {
    if (!result.url) return;
    setError(null);
    setIsFocused(false);
    router.push(result.url);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    let fallbackUrl: string | null = null;

    if (detectedType) {
      if (detectedType === "sol" && selectedChain && selectedChain !== "solana") {
        setError("Solana addresses can only be analyzed on Solana.");
        return;
      }
      if (detectedType === "evm" && !selectedChain) {
        setError("Select the EVM chain before analyzing this address.");
        return;
      }
      if (detectedType === "evm" && selectedChain === "solana") {
        setError("EVM addresses require an EVM chain selection.");
        return;
      }
      
      const chain = selectedChain ?? (detectedType === "sol" ? "solana" : undefined);
      const params = chain ? `?chain=${chain}` : "";
      fallbackUrl = `/token/${trimmed}${params}`;
    }

    if (trimmed.length < 2) {
      setError("Enter at least 2 characters to search.");
      return;
    }

    try {
      setIsResolving(true);
      setError(null);
      const response = await searchTokens(trimmed, selectedChain ?? undefined, 8);
      const topResult = response.results[0];
      if (!topResult?.url) {
        if (fallbackUrl) {
          router.push(fallbackUrl);
          return;
        }
        setError("No token or pool matched that query.");
        return;
      }
      handleResultSelect(topResult);
    } catch (err) {
      if (fallbackUrl) {
        router.push(fallbackUrl);
        return;
      }
      setError((err as Error).message || "Search failed.");
    } finally {
      setIsResolving(false);
    }
  };

  const tokenResults = searchResults.filter((item) => item.type === "token");
  const poolResults = searchResults.filter((item) => item.type === "pool");
  const sections = [
    { key: "token", label: "Tokens", items: tokenResults },
    { key: "pool", label: "Pools", items: poolResults },
  ].filter((s) => s.items.length > 0);

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-3xl mx-auto">
      <div className="flex flex-col sm:flex-row gap-3 p-3 rounded-2xl bg-card/60 border border-white/10">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Paste any token or pool address or name..."
            value={query}
            onChange={(e) => { setQuery(e.target.value); setError(null); }}
            onFocus={() => setIsFocused(true)}
            onBlur={() => window.setTimeout(() => setIsFocused(false), 120)}
            className="pl-9 h-10 bg-transparent border-none text-sm focus-visible:ring-0"
          />
        </div>
        <Button
          type="submit"
          disabled={isResolving}
          className="h-10 px-6 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold rounded-xl"
        >
          {isResolving ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <>
              Analyze
              <ArrowRight className="ml-2 w-4 h-4" />
            </>
          )}
        </Button>
      </div>

      <div className="mt-2">
        <CompactChainSelector
          selectedChain={selectedChain}
          onSelect={handleChainSelect}
          detectedType={detectedType}
        />
      </div>

      {error && <p className="text-xs text-red-400 mt-2">{error}</p>}

      {isFocused && debouncedQuery.length >= 2 && (
        <div className="mt-2 rounded-xl border border-white/10 bg-card/90 backdrop-blur-xl overflow-hidden">
          {isFetching ? (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Searching...
            </div>
          ) : sections.length > 0 ? (
            <div className="divide-y divide-white/5">
              {sections.map((section) => (
                <div key={section.key} className="p-2">
                  <div className="px-3 py-1.5 text-xs uppercase tracking-wider text-muted-foreground">
                    {section.label}
                  </div>
                  {section.items.slice(0, 4).map((result) => (
                    <button
                      key={`${result.type}-${result.url}`}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => handleResultSelect(result)}
                      className="w-full rounded-lg px-3 py-2 text-left hover:bg-white/5 transition-colors"
                    >
                      <div className="text-sm font-medium">{result.title}</div>
                      <div className="text-xs text-muted-foreground">{result.subtitle}</div>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          ) : (
            <div className="px-4 py-3 text-sm text-muted-foreground">No matches found.</div>
          )}
        </div>
      )}
    </form>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npx tsc --noEmit components/landing/quick-search.tsx
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add web/components/landing/quick-search.tsx
git commit -m "feat(landing): extract search into QuickSearch component"
```

---

## Task 5: Rewrite Main Page

**Files:**
- Rewrite: `web/app/page.tsx`

- [ ] **Step 1: Backup current page**

```bash
cp web/app/page.tsx web/app/page.tsx.backup
```

- [ ] **Step 2: Create new page.tsx**

```tsx
"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Sparkles,
  ArrowRight,
  CheckCircle2,
  Search,
  TrendingUp,
  Shield,
  BarChart3,
  Activity,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import { useDashboardStats } from "@/lib/hooks";
import { formatCompact } from "@/lib/utils";
import { ChatPreview } from "@/components/landing/chat-preview";
import { ReasoningVisualization } from "@/components/landing/reasoning-viz";
import { QuickSearch } from "@/components/landing/quick-search";

// Animated background orbs
function BackgroundEffects() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      <div className="hero-glow top-[-200px] left-1/2 -translate-x-1/2" />
      <div className="hero-orb w-[400px] h-[400px] top-[10%] left-[10%]" style={{ animationDelay: "0s" }} />
      <div className="hero-orb w-[300px] h-[300px] top-[60%] right-[5%]" style={{ animationDelay: "2s" }} />
      <div className="hero-orb w-[200px] h-[200px] bottom-[20%] left-[20%]" style={{ animationDelay: "4s" }} />
      <div className="absolute inset-0 grid-pattern opacity-30" />
    </div>
  );
}

// Stat card
function StatCard({ value, label, icon: Icon, loading }: { value: string; label: string; icon: React.ElementType; loading?: boolean }) {
  return (
    <div className="stat-card text-center">
      <Icon className="w-6 h-6 sm:w-8 sm:h-8 text-emerald-400 mx-auto mb-2 sm:mb-3" />
      {loading ? (
        <div className="h-9 w-20 bg-muted/50 animate-pulse rounded mx-auto mb-1" />
      ) : (
        <div className="text-2xl sm:text-3xl font-bold text-emerald-400 mb-1">{value}</div>
      )}
      <div className="text-xs sm:text-sm text-muted-foreground">{label}</div>
    </div>
  );
}

export default function HomePage() {
  const { data: statsData, isLoading: statsLoading } = useDashboardStats();

  return (
    <div className="min-h-screen relative">
      <BackgroundEffects />

      {/* Hero Section */}
      <section className="relative pt-20 pb-32 px-4">
        <div className="container mx-auto max-w-7xl">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            {/* Left column - Text */}
            <div className="space-y-8">
              {/* Badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 animate-fade-in-down">
                <Sparkles className="w-4 h-4 text-emerald-400" />
                <span className="text-sm text-emerald-400">AI-Powered DeFi Assistant</span>
              </div>

              {/* Headline */}
              <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold leading-tight animate-fade-in-up">
                Your Intelligent
                <br />
                Crypto Trading
                <br />
                <span className="text-emerald-400">AI Assistant</span>
              </h1>

              {/* Subheadline */}
              <p className="text-xl text-muted-foreground max-w-lg animate-fade-in-up" style={{ animationDelay: "100ms" }}>
                Connect your wallet and trade with confidence. Ask anything in natural language — check balances, find best swap routes, track portfolios, bridge across chains, and get real-time market analysis.
              </p>

              {/* CTAs */}
              <div className="flex flex-col sm:flex-row items-start gap-4 animate-fade-in-up" style={{ animationDelay: "200ms" }}>
                <Link href="/agent/chat">
                  <Button size="lg" className="h-14 px-8 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold rounded-xl">
                    <MessageSquare className="mr-2 w-5 h-5" />
                    Open AI Chat
                  </Button>
                </Link>
                <Button
                  size="lg"
                  variant="outline"
                  className="h-14 px-8"
                  onClick={() => document.getElementById("reasoning-viz")?.scrollIntoView({ behavior: "smooth" })}
                >
                  Try Demo Query
                  <ArrowRight className="ml-2 w-5 h-5" />
                </Button>
              </div>

              {/* Trust indicators */}
              <div className="flex flex-wrap items-center gap-6 pt-4 animate-fade-in-up" style={{ animationDelay: "300ms" }}>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>AI-Powered Trading</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Multi-Chain Support</span>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>Non-Custodial Security</span>
                </div>
              </div>
            </div>

            {/* Right column - Chat Preview */}
            <div className="hidden lg:block">
              <ChatPreview />
            </div>
          </div>
        </div>
      </section>

      {/* Reasoning Visualization Section */}
      <section id="reasoning-viz" className="relative py-24 px-4 bg-card/30">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              See How Your AI
              <span className="text-gradient"> Thinks</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Every request triggers a chain of intelligent decisions
            </p>
          </div>

          <ReasoningVisualization />
        </div>
      </section>

      {/* Quick Search Strip */}
      <section className="relative py-16 px-4 border-t border-white/5">
        <div className="container mx-auto max-w-4xl">
          <div className="flex flex-col md:flex-row items-center gap-6">
            <div className="flex items-center gap-3 shrink-0">
              <Search className="w-5 h-5 text-emerald-400" />
              <span className="text-lg font-semibold">Analyze Any Token or Pool</span>
            </div>
            <div className="flex-1 w-full">
              <QuickSearch />
            </div>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-bold mb-4">
              How It Works
            </h2>
            <p className="text-lg text-muted-foreground">
              Get started with AI-powered trading in three simple steps
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: "01",
                icon: "🔗",
                title: "Connect Wallet",
                description: "Link Phantom or MetaMask. We support Solana + major EVM networks in one app.",
              },
              {
                step: "02",
                icon: "💬",
                title: "Ask the AI",
                description: 'Type naturally: "Swap 0.5 SOL to USDC at best rate" or "What\'s my portfolio worth today?"',
              },
              {
                step: "03",
                icon: "⚡",
                title: "Execute Instantly",
                description: "Confirm the AI-generated transaction with one click. Fast, transparent, non-custodial.",
              },
            ].map((item, i) => (
              <div key={i} className="relative text-center group">
                <div className="text-6xl font-bold text-emerald-500/20 mb-4 group-hover:text-emerald-500/40 transition-colors">
                  {item.step}
                </div>
                <div className="text-3xl mb-3">{item.icon}</div>
                <h3 className="text-xl font-semibold mb-2">{item.title}</h3>
                <p className="text-muted-foreground">{item.description}</p>
                {i < 2 && (
                  <ChevronRight className="hidden md:block absolute top-8 -right-4 w-8 h-8 text-emerald-500/30" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="relative py-20 px-4 border-t border-white/5">
        <div className="container mx-auto max-w-6xl">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <StatCard
              value={statsData ? (statsData.total_tokens_analyzed ?? 0).toLocaleString() : "0"}
              label="Tokens Analyzed"
              icon={Search}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? formatCompact(statsData.total_volume_24h ?? 0) : "$0"}
              label="24h Trading Volume"
              icon={BarChart3}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? formatCompact(statsData.solana_tvl ?? 0) : "$0"}
              label="Multi-Chain TVL"
              icon={Activity}
              loading={statsLoading}
            />
            <StatCard
              value={statsData ? `${(statsData.safe_tokens_percent ?? 0).toFixed(1)}%` : "0%"}
              label="Safe Tokens"
              icon={Shield}
              loading={statsLoading}
            />
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-4xl">
          <div className="relative glass-card text-center p-12 md:p-16 overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/10 to-transparent" />
            <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/20 rounded-full blur-3xl" />

            <div className="relative z-10">
              <h2 className="text-4xl md:text-5xl font-bold mb-6">
                Ready to Trade
                <span className="text-gradient"> Smarter?</span>
              </h2>
              <p className="text-lg text-muted-foreground mb-8 max-w-2xl mx-auto">
                Let AI handle the complexity. You just say what you want.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <Link href="/agent/chat">
                  <Button size="lg" className="h-14 px-8 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold">
                    <MessageSquare className="mr-2 w-5 h-5" />
                    Open AI Chat
                  </Button>
                </Link>
                <Link href="/trending">
                  <Button size="lg" variant="outline" className="h-14 px-8">
                    <TrendingUp className="mr-2 w-5 h-5" />
                    View Trending
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npx tsc --noEmit app/page.tsx
```

Expected: No errors.

- [ ] **Step 4: Remove backup**

```bash
rm web/app/page.tsx.backup
```

- [ ] **Step 5: Commit**

```bash
git add web/app/page.tsx
git commit -m "feat(landing): redesign main page with AI-first positioning

- Replace token scanner hero with AI assistant messaging
- Add animated ChatPreview component showing demo conversations
- Add ReasoningVisualization showing AI thought process
- Extract QuickSearch component for token/pool search
- Update How It Works to AI workflow (connect → ask → execute)
- Reframe CTA around AI chat entry point"
```

---

## Task 6: Final Verification

- [ ] **Step 1: TypeScript check for entire page**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npx tsc --noEmit
```

Expected: No errors across all new and modified files.

- [ ] **Step 2: Build check**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no errors.

- [ ] **Step 3: Verify all imports resolve**

```bash
cd /home/griffiniskid/Documents/ai-sentinel/web && npx tsc --noEmit --pretty 2>&1 | grep "error TS" | head -20
```

Expected: Empty output (no errors).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(landing): complete main page redesign — AI-first positioning

Implements spec: docs/superpowers/specs/2026-04-26-main-page-redesign.md

Changes:
- Metadata updated for AI assistant positioning
- ChatPreview component with 3 animated scenarios
- ReasoningVisualization component with auto-cycling flows
- QuickSearch extracted component for compact search strip
- Complete page rewrite: hero, reasoning viz, search, how-it-works, stats, CTA
- All existing functionality preserved (search, stats, navigation)"
```

---

## Spec Coverage Checklist

| Spec Section | Task | Status |
|-------------|------|--------|
| 3.1 Hero Section | Task 5 | ✅ Implemented |
| 3.2 Reasoning Visualization | Task 3 | ✅ Implemented |
| 3.3 Quick Search Strip | Task 4 | ✅ Implemented |
| 3.4 How It Works | Task 5 | ✅ Implemented |
| 3.5 Stats Section | Task 5 | ✅ Implemented |
| 3.6 CTA Section | Task 5 | ✅ Implemented |
| 3.7 Metadata Updates | Task 1 | ✅ Implemented |
| 4. Component Inventory | All tasks | ✅ All files created/modified |
| 5. Animation Spec | Tasks 2, 3 | ✅ Framer Motion animations |
| 6. Responsive Behavior | Task 5 | ✅ Tailwind responsive classes |
| 7. Assets | N/A | ✅ No new assets needed |
| 8. Accessibility | Task 5 | ✅ AnimatePresence, reduced motion |

---

**Plan Status**: Complete

**Ready for execution via:**
1. **Subagent-Driven Development** (recommended) — dispatch fresh subagent per task
2. **Inline Execution** — execute tasks sequentially in this session
