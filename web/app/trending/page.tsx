"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useQueryClient } from "@tanstack/react-query";
import { useTrendingTokens } from "@/lib/hooks";
import * as api from "@/lib/api";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Clock, ExternalLink, Flame, Loader2, RefreshCw, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { cn, formatAge, formatCompact, formatPercentage, formatUSD } from "@/lib/utils";
import type { ChainName } from "@/types";

type Category = "trending" | "gainers" | "losers" | "new";

const categories = [
  { id: "trending" as Category, label: "Trending", icon: Flame },
  { id: "gainers" as Category, label: "Top Gainers", icon: TrendingUp },
  { id: "losers" as Category, label: "Top Losers", icon: TrendingDown },
  { id: "new" as Category, label: "New Pairs", icon: Sparkles },
];

const chains: Array<{ value: "all" | ChainName; label: string }> = [
  { value: "all", label: "All Chains" },
  { value: "solana", label: "Solana" },
  { value: "ethereum", label: "Ethereum" },
  { value: "base", label: "Base" },
  { value: "arbitrum", label: "Arbitrum" },
  { value: "bsc", label: "BSC" },
  { value: "polygon", label: "Polygon" },
  { value: "optimism", label: "Optimism" },
  { value: "avalanche", label: "Avalanche" },
];

export default function TrendingPage() {
  const [category, setCategory] = useState<Category>("trending");
  const [chain, setChain] = useState<"all" | ChainName>("all");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const activeChain = chain === "all" ? null : chain;
  const { data, isLoading, isFetching } = useTrendingTokens(category, activeChain);
  const queryClient = useQueryClient();

  const handleForceRefresh = async () => {
    setIsRefreshing(true);
    try {
      const freshData = await api.getTrendingTokens(category, 20, true, activeChain ?? undefined);
      queryClient.setQueryData(["trending", category, activeChain ?? "all"], freshData);
    } catch {
      queryClient.invalidateQueries({ queryKey: ["trending", category, activeChain ?? "all"] });
    } finally {
      setIsRefreshing(false);
    }
  };

  const busy = isFetching || isRefreshing;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="mb-2 text-3xl font-bold">Trending Tokens</h1>
          <p className="text-muted-foreground">Discover high-velocity tokens across Solana and major EVM chains.</p>
        </div>
        <Button variant="outline" onClick={handleForceRefresh} disabled={busy}>
          <RefreshCw className={cn("mr-2 h-4 w-4", busy && "animate-spin")} />
          Refresh
        </Button>
      </div>

      <div className="mb-8 flex flex-wrap gap-2">
        {categories.map((cat) => {
          const Icon = cat.icon;
          const isActive = category === cat.id;
          return (
            <Button
              key={cat.id}
              variant={isActive ? "default" : "outline"}
              onClick={() => setCategory(cat.id)}
              className={cn(isActive && "bg-emerald-600 hover:bg-emerald-500")}
            >
              <Icon className="mr-2 h-4 w-4" />
              {cat.label}
            </Button>
          );
        })}
      </div>

      <GlassCard className="mb-6">
        <div className="flex flex-wrap gap-2">
          {chains.map((item) => (
            <Button
              key={item.value}
              variant={chain === item.value ? "default" : "outline"}
              size="sm"
              onClick={() => setChain(item.value)}
              className={cn(chain === item.value && "bg-sky-600 hover:bg-sky-500")}
            >
              {item.label}
            </Button>
          ))}
        </div>
      </GlassCard>

      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.tokens.map((token, index) => (
            <Link key={`${token.chain}-${token.address}`} href={`/token/${token.address}?chain=${token.chain}`}>
              <GlassCard className="group h-full cursor-pointer transition-all hover:border-emerald-500/50">
                <div className="mb-3 flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="text-lg font-bold text-muted-foreground">#{index + 1}</div>
                    {token.logo_url ? (
                      <Image src={token.logo_url} alt={token.symbol} width={40} height={40} className="rounded-full" />
                    ) : (
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted text-lg font-bold">{token.symbol[0]}</div>
                    )}
                    <div>
                      <div className="font-semibold transition group-hover:text-emerald-400">{token.symbol}</div>
                      <div className="max-w-[120px] truncate text-xs text-muted-foreground">{token.name}</div>
                    </div>
                  </div>
                  <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 transition group-hover:opacity-100" />
                </div>

                <div className="mb-3 flex items-center gap-2">
                  <Badge variant="outline" className="capitalize">{token.chain}</Badge>
                  <Badge variant="secondary">{token.dex_name}</Badge>
                </div>

                <div className="mb-3">
                  <div className="font-mono text-lg font-semibold">{formatUSD(token.price_usd)}</div>
                  <div className="flex items-center gap-2">
                    <span className={cn("font-mono text-sm", token.price_change_24h >= 0 ? "text-emerald-400" : "text-red-400")}>
                      {formatPercentage(token.price_change_24h)}
                    </span>
                    <span className="text-xs text-muted-foreground">24h</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <div className="text-muted-foreground">Market Cap</div>
                    <div className="font-mono">{formatCompact(token.market_cap)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Liquidity</div>
                    <div className="font-mono">{formatCompact(token.liquidity_usd)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Volume 24h</div>
                    <div className="font-mono">{formatCompact(token.volume_24h)}</div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">Age</div>
                    <div className="flex items-center gap-1 font-mono">
                      <Clock className="h-3 w-3" />
                      {formatAge(token.age_hours)}
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-2 border-t border-border/50 pt-3">
                  {token.txns_1h != null && (
                    <Badge variant={token.txns_1h >= 500 ? "safe" : token.txns_1h >= 100 ? "caution" : "danger"}>
                      {token.txns_1h.toLocaleString()} txns (1h)
                    </Badge>
                  )}
                  {token.age_hours < 1 && <Badge variant="outline">New</Badge>}
                </div>
              </GlassCard>
            </Link>
          ))}
        </div>
      )}

      {data && data.tokens.length === 0 && (
        <GlassCard className="py-12 text-center">
          <p className="text-muted-foreground">No tokens found for this category and chain.</p>
        </GlassCard>
      )}

      {data && (
        <div className="mt-8 text-center text-sm text-muted-foreground">
          Last updated: {new Date(data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
