"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Loader2,
  ArrowRight,
  TrendingUp,
  Shield,
  AlertTriangle,
  CheckCircle2,
  BarChart3,
  Activity,
  Zap,
  Globe,
  Clock,
  ChevronRight,
  Star,
  Flame,
  Scan,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, isValidEvmAddress, isValidSolanaAddress } from "@/lib/utils";
import { useSearchCatalog } from "@/lib/hooks";
import { searchTokens } from "@/lib/api";
import type { SearchResultResponse } from "@/types";

const CHAINS = [
  { id: "all", label: "All Chains", short: "ALL", color: "#10B981", type: "all" },
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

// Mock data for trending and recent
const TRENDING_TOKENS = [
  { symbol: "SOL", name: "Solana", price: "$86.52", change: "+5.2%", chain: "solana", score: 92 },
  { symbol: "ETH", name: "Ethereum", price: "$2,346", change: "+1.4%", chain: "ethereum", score: 95 },
  { symbol: "BNB", name: "BNB", price: "$632.64", change: "-0.25%", chain: "bsc", score: 88 },
  { symbol: "ARB", name: "Arbitrum", price: "$0.1306", change: "+0.68%", chain: "arbitrum", score: 78 },
];

const RECENT_SEARCHES = [
  "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
  "Uniswap V3 ETH/USDC",
  "Jupiter SOL/USDC",
  "Aave USDC lending pool",
];

const ANALYSIS_FEATURES = [
  {
    icon: Shield,
    title: "Security Audit",
    description: "Deep contract analysis with AI-powered vulnerability detection",
    color: "emerald",
  },
  {
    icon: AlertTriangle,
    title: "Risk Scoring",
    description: "Multi-dimensional risk assessment across liquidity, holders, and code",
    color: "amber",
  },
  {
    icon: BarChart3,
    title: "Pool Analytics",
    description: "Advanced liquidity pool metrics, impermanent loss calculator, and yield analysis",
    color: "blue",
  },
  {
    icon: Activity,
    title: "Real-time Monitoring",
    description: "Live price tracking, volume analysis, and whale movement alerts",
    color: "purple",
  },
  {
    icon: Zap,
    title: "Honeypot Detection",
    description: "Simulated trade execution to detect scams and high-tax tokens",
    color: "red",
  },
  {
    icon: Globe,
    title: "Multi-Chain Coverage",
    description: "Unified analysis across Solana, Ethereum, Base, Arbitrum, and more",
    color: "cyan",
  },
];

export default function AnalyzePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [selectedChain, setSelectedChain] = useState<ChainId>("all");
  const [error, setError] = useState<string | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [isResolving, setIsResolving] = useState(false);
  const [showResults, setShowResults] = useState(false);
  
  const { data: searchData, isFetching } = useSearchCatalog(
    debouncedQuery,
    selectedChain === "all" ? undefined : selectedChain
  );

  const detectedType = detectChainType(query);
  const searchResults = searchData?.results ?? [];

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 180);
    return () => clearTimeout(timer);
  }, [query]);

  const handleChainSelect = (id: ChainId) => {
    setError(null);
    setSelectedChain(id);
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
      if (detectedType === "sol" && selectedChain && selectedChain !== "solana" && selectedChain !== "all") {
        setError("Solana addresses can only be analyzed on Solana.");
        return;
      }
      if (detectedType === "evm" && selectedChain === "solana") {
        setError("EVM addresses require an EVM chain selection.");
        return;
      }
      
      const chain = selectedChain === "all" ? (detectedType === "sol" ? "solana" : "ethereum") : selectedChain;
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
      const response = await searchTokens(trimmed, selectedChain === "all" ? undefined : selectedChain, 8);
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

  const getChainColor = (chainId: string) => {
    const chain = CHAINS.find((c) => c.id === chainId);
    return chain?.color || "#10B981";
  };

  return (
    <div className="relative">
      {/* Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="hero-glow top-[-200px] left-1/2 -translate-x-1/2" />
        <div className="hero-orb w-[500px] h-[500px] top-[5%] right-[5%] opacity-50" style={{ animationDelay: "0s" }} />
        <div className="hero-orb w-[400px] h-[400px] bottom-[10%] left-[10%] opacity-30" style={{ animationDelay: "3s" }} />
        <div className="absolute inset-0 grid-pattern opacity-20" />
      </div>

      <div className="container mx-auto max-w-7xl px-4 py-12 relative z-10">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-6">
            <Scan className="w-4 h-4 text-emerald-400" />
            <span className="text-sm text-emerald-400 font-medium">Advanced Analysis Engine</span>
          </div>
          
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold mb-4">
            Analyze Any
            <span className="text-emerald-400"> Token or Pool</span>
          </h1>
          
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Deep security analysis, risk scoring, and real-time intelligence for tokens and liquidity pools across all major chains.
          </p>
        </div>

        {/* Search Section */}
        <div className="max-w-4xl mx-auto mb-16">
          <form onSubmit={handleSubmit} className="relative">
            <div className="glass-card p-2 md:p-4">
              {/* Main Search Input */}
              <div className="relative flex items-center">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search by token name, symbol, or contract address..."
                  value={query}
                  onChange={(e) => { setQuery(e.target.value); setError(null); }}
                  onFocus={() => setIsFocused(true)}
                  onBlur={() => window.setTimeout(() => setIsFocused(false), 120)}
                  className="pl-12 pr-32 h-14 bg-transparent border-none text-base md:text-lg placeholder:text-muted-foreground focus-visible:ring-0"
                />
                <Button
                  type="submit"
                  disabled={isResolving}
                  className="absolute right-2 h-10 px-6 bg-emerald-600 hover:bg-emerald-500 text-black font-semibold rounded-xl"
                >
                  {isResolving ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <>
                      Analyze
                      <ArrowRight className="ml-2 w-4 h-4" />
                    </>
                  )}
                </Button>
              </div>

              {/* Chain Selector */}
              <div className="mt-4 pt-4 border-t border-white/5">
                <div className="flex items-center gap-3 overflow-x-auto pb-2 scrollbar-hide">
                  <span className="text-xs text-muted-foreground shrink-0">Filter by chain:</span>
                  {CHAINS.map((chain) => {
                    const isSelected = selectedChain === chain.id;
                    const isHighlighted = !isSelected && detectedType && 
                      (chain.type === detectedType || chain.id === "all");
                    
                    return (
                      <button
                        key={chain.id}
                        type="button"
                        onClick={() => handleChainSelect(chain.id)}
                        className={cn(
                          "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 border shrink-0",
                          isSelected
                            ? "border-emerald-500/60 bg-emerald-500/15 text-emerald-300"
                            : isHighlighted
                            ? "border-white/30 bg-white/10 text-white/80"
                            : "border-white/10 bg-white/5 text-muted-foreground hover:border-white/20 hover:bg-white/10"
                        )}
                      >
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ background: chain.color }}
                        />
                        {chain.short}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Error */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="mt-3 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400"
                >
                  {error}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Search Results Dropdown */}
            <AnimatePresence>
              {isFocused && debouncedQuery.length >= 2 && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute top-full left-0 right-0 mt-2 rounded-2xl border border-white/10 bg-card/95 backdrop-blur-xl overflow-hidden shadow-2xl z-50"
                >
                  {isFetching ? (
                    <div className="flex items-center gap-3 px-6 py-4 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Searching tokens and pools...
                    </div>
                  ) : sections.length > 0 ? (
                    <div className="divide-y divide-white/5">
                      {sections.map((section) => (
                        <div key={section.key} className="p-2">
                          <div className="px-4 py-2 text-xs uppercase tracking-wider text-muted-foreground font-medium">
                            {section.label}
                          </div>
                          {section.items.slice(0, 5).map((result, idx) => (
                            <motion.button
                              key={`${result.type}-${result.url}`}
                              initial={{ opacity: 0, x: -10 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: idx * 0.05 }}
                              type="button"
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={() => handleResultSelect(result)}
                              className="w-full rounded-xl px-4 py-3 text-left hover:bg-white/5 transition-colors flex items-center gap-3"
                            >
                              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                                <span className="text-xs font-bold text-emerald-400">
                                  {result.title?.charAt(0)}
                                </span>
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-sm truncate">{result.title}</div>
                                <div className="text-xs text-muted-foreground truncate">{result.subtitle}</div>
                              </div>
                              <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
                            </motion.button>
                          ))}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="px-6 py-4 text-sm text-muted-foreground">No tokens or pools found matching "{debouncedQuery}"</div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </form>

          {/* Recent Searches */}
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            <Clock className="w-3 h-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Recent:</span>
            {RECENT_SEARCHES.map((search, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setQuery(search)}
                className="text-xs text-muted-foreground hover:text-emerald-400 transition-colors underline-offset-2 hover:underline"
              >
                {search.length > 25 ? `${search.slice(0, 25)}...` : search}
              </button>
            ))}
          </div>
        </div>

        {/* Trending Section */}
        <div className="mb-16">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <Flame className="w-5 h-5 text-orange-400" />
              <h2 className="text-xl font-semibold">Trending Tokens</h2>
            </div>
            <Link href="/trending">
              <Button variant="ghost" size="sm" className="text-emerald-400 hover:text-emerald-300">
                View All
                <ChevronRight className="ml-1 w-4 h-4" />
              </Button>
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {TRENDING_TOKENS.map((token, i) => (
              <motion.div
                key={token.symbol}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                className="glass-card-hover p-5 cursor-pointer group"
                onClick={() => router.push(`/token/${token.symbol.toLowerCase()}?chain=${token.chain}`)}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold"
                      style={{
                        background: `${getChainColor(token.chain)}20`,
                        border: `1px solid ${getChainColor(token.chain)}40`,
                        color: getChainColor(token.chain),
                      }}
                    >
                      {token.symbol.charAt(0)}
                    </div>
                    <div>
                      <div className="font-semibold">{token.symbol}</div>
                      <div className="text-xs text-muted-foreground">{token.name}</div>
                    </div>
                  </div>
                  
                  <div className="text-right">
                    <div className="font-mono font-semibold">{token.price}</div>
                    <div className={cn(
                      "text-xs",
                      token.change.startsWith("+") ? "text-emerald-400" : "text-red-400"
                    )}>
                      {token.change}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-white/5">
                  <div className="flex items-center gap-1.5">
                    <Shield className="w-3 h-3 text-emerald-400" />
                    <span className="text-xs text-muted-foreground">Score: {token.score}/100</span>
                  </div>
                  
                  <div className="flex items-center gap-1">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: getChainColor(token.chain) }}
                    />
                    <span className="text-[10px] uppercase text-muted-foreground">
                      {token.chain}
                    </span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Features Grid */}
        <div className="mb-16">
          <div className="text-center mb-8">
            <h2 className="text-2xl md:text-3xl font-bold mb-2">
              Advanced
              <span className="text-gradient"> Analysis Features</span>
            </h2>
            <p className="text-muted-foreground">
              Comprehensive security and intelligence toolkit
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {ANALYSIS_FEATURES.map((feature, i) => {
              const Icon = feature.icon;
              return (
                <motion.div
                  key={feature.title}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                  className="glass-card-hover p-6 group"
                >
                  <div className={cn(
                    "w-12 h-12 rounded-xl flex items-center justify-center mb-4 transition-transform group-hover:scale-110",
                    feature.color === "emerald" && "bg-emerald-500/10 border border-emerald-500/20",
                    feature.color === "amber" && "bg-amber-500/10 border border-amber-500/20",
                    feature.color === "blue" && "bg-blue-500/10 border border-blue-500/20",
                    feature.color === "purple" && "bg-purple-500/10 border border-purple-500/20",
                    feature.color === "red" && "bg-red-500/10 border border-red-500/20",
                    feature.color === "cyan" && "bg-cyan-500/10 border border-cyan-500/20",
                  )}>
                    <Icon className={cn(
                      "w-6 h-6",
                      feature.color === "emerald" && "text-emerald-400",
                      feature.color === "amber" && "text-amber-400",
                      feature.color === "blue" && "text-blue-400",
                      feature.color === "purple" && "text-purple-400",
                      feature.color === "red" && "text-red-400",
                      feature.color === "cyan" && "text-cyan-400",
                    )} />
                  </div>
                  
                  <h3 className="text-lg font-semibold mb-2 group-hover:text-emerald-400 transition-colors">
                    {feature.title}
                  </h3>
                  
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* Stats Banner */}
        <div className="glass-card p-8 text-center">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {[
              { value: "50K+", label: "Tokens Analyzed", icon: Scan },
              { value: "12K+", label: "Pools Scanned", icon: Activity },
              { value: "99.2%", label: "Accuracy Rate", icon: CheckCircle2 },
              { value: "8", label: "Chains Supported", icon: Globe },
            ].map((stat, i) => {
              const Icon = stat.icon;
              return (
                <div key={i} className="text-center">
                  <Icon className="w-6 h-6 text-emerald-400 mx-auto mb-2" />
                  <div className="text-2xl md:text-3xl font-bold text-emerald-400 mb-1">{stat.value}</div>
                  <div className="text-xs text-muted-foreground">{stat.label}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
