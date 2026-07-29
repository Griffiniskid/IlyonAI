"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isValidEvmAddress, isValidSolanaAddress } from "@/lib/utils";
import { useSearchCatalog } from "@/lib/hooks";
import { searchTokens } from "@/lib/api";
import type { SearchResultResponse } from "@/types";

// Solana-only Token Safety search. Screens tokens (not pools); routes every
// result into /token-safety?address=… which auto-runs the rug scan.
export function QuickSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [isResolving, setIsResolving] = useState(false);

  const { data: searchData, isFetching } = useSearchCatalog(debouncedQuery, "solana");

  // Token Safety only screens tokens (not LP pools) and only on Solana.
  const tokenResults = (searchData?.results ?? []).filter(
    (item) => item.type === "token" && item.address
  );

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query.trim()), 180);
    return () => clearTimeout(timer);
  }, [query]);

  const goToSafety = (address: string) => {
    setError(null);
    setIsFocused(false);
    router.push(`/token-safety?address=${encodeURIComponent(address)}`);
  };

  const handleResultSelect = (result: SearchResultResponse) => {
    if (result.address) goToSafety(result.address);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    if (isValidSolanaAddress(trimmed)) {
      goToSafety(trimmed);
      return;
    }
    if (isValidEvmAddress(trimmed)) {
      setError("Ilyon is Solana-only — paste a Solana token address.");
      return;
    }
    if (trimmed.length < 2) {
      setError("Enter at least 2 characters to search.");
      return;
    }

    try {
      setIsResolving(true);
      setError(null);
      const response = await searchTokens(trimmed, "solana", 8);
      const top = response.results.find((r) => r.type === "token" && r.address);
      if (top?.address) {
        goToSafety(top.address);
        return;
      }
      setError("No Solana token matched that — try pasting the token address.");
    } catch (err) {
      setError((err as Error).message || "Search failed.");
    } finally {
      setIsResolving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div className="flex flex-col sm:flex-row gap-3 p-3 rounded-2xl bg-card/60 border border-white/10">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Paste a Solana token address or name..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setError(null);
            }}
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

      {error && <p className="text-xs text-red-400 mt-2">{error}</p>}

      {isFocused && debouncedQuery.length >= 2 && (
        <div className="mt-2 rounded-xl border border-white/10 bg-card/90 backdrop-blur-xl overflow-hidden">
          {isFetching ? (
            <div className="flex items-center gap-2 px-4 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Searching...
            </div>
          ) : tokenResults.length > 0 ? (
            <div className="p-2">
              {tokenResults.slice(0, 6).map((result) => (
                <button
                  key={`token-${result.address}`}
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
          ) : (
            <div className="px-4 py-3 text-sm text-muted-foreground">No Solana token found.</div>
          )}
        </div>
      )}
    </form>
  );
}
