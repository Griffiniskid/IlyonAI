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
    <form onSubmit={handleSubmit} className="w-full">
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
