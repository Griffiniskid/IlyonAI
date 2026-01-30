"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useTrendingTokens } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  TrendingUp,
  TrendingDown,
  Flame,
  Sparkles,
  Clock,
  Loader2,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import {
  formatUSD,
  formatCompact,
  formatPercentage,
  formatAge,
  cn,
} from "@/lib/utils";

type Category = "trending" | "gainers" | "losers" | "new";

const categories = [
  { id: "trending" as Category, label: "Trending", icon: Flame },
  { id: "gainers" as Category, label: "Top Gainers", icon: TrendingUp },
  { id: "losers" as Category, label: "Top Losers", icon: TrendingDown },
  { id: "new" as Category, label: "New Pairs", icon: Sparkles },
];

export default function TrendingPage() {
  const [category, setCategory] = useState<Category>("trending");
  const { data, isLoading, refetch, isFetching } = useTrendingTokens(category);

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">Trending Tokens</h1>
          <p className="text-muted-foreground">
            Discover the hottest tokens on Solana
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw
            className={cn("h-4 w-4 mr-2", isFetching && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {/* Category tabs */}
      <div className="flex flex-wrap gap-2 mb-8">
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
              <Icon className="h-4 w-4 mr-2" />
              {cat.label}
            </Button>
          );
        })}
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        </div>
      )}

      {/* Token grid */}
      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {data.tokens.map((token, index) => (
            <Link key={token.address} href={`/token/${token.address}`}>
              <GlassCard className="h-full hover:border-emerald-500/50 transition-all cursor-pointer group">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="text-lg font-bold text-muted-foreground">
                      #{index + 1}
                    </div>
                    {token.logo_url ? (
                      <Image
                        src={token.logo_url}
                        alt={token.symbol}
                        width={40}
                        height={40}
                        className="rounded-full"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-lg font-bold">
                        {token.symbol[0]}
                      </div>
                    )}
                    <div>
                      <div className="font-semibold group-hover:text-emerald-400 transition">
                        {token.symbol}
                      </div>
                      <div className="text-xs text-muted-foreground truncate max-w-[100px]">
                        {token.name}
                      </div>
                    </div>
                  </div>
                  <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition" />
                </div>

                {/* Price */}
                <div className="mb-3">
                  <div className="font-mono font-semibold text-lg">
                    {formatUSD(token.price_usd)}
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "font-mono text-sm",
                        token.price_change_24h >= 0
                          ? "text-emerald-400"
                          : "text-red-400"
                      )}
                    >
                      {formatPercentage(token.price_change_24h)}
                    </span>
                    <span className="text-xs text-muted-foreground">24h</span>
                  </div>
                </div>

                {/* Stats */}
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
                    <div className="font-mono flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatAge(token.age_hours)}
                    </div>
                  </div>
                </div>

                {/* Quick score if available */}
                {token.quick_score !== undefined && (
                  <div className="mt-3 pt-3 border-t border-border/50">
                    <Badge
                      variant={
                        token.quick_score >= 70
                          ? "safe"
                          : token.quick_score >= 40
                          ? "caution"
                          : "danger"
                      }
                    >
                      Score: {token.quick_score}
                    </Badge>
                  </div>
                )}
              </GlassCard>
            </Link>
          ))}
        </div>
      )}

      {/* Empty state */}
      {data && data.tokens.length === 0 && (
        <GlassCard className="text-center py-12">
          <p className="text-muted-foreground">No tokens found</p>
        </GlassCard>
      )}

      {/* Last updated */}
      {data && (
        <div className="text-center text-sm text-muted-foreground mt-8">
          Last updated: {new Date(data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
