"use client";

import { TrendingUp, TrendingDown, DollarSign, Droplets, BarChart3, Clock } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import type { MarketDataResponse } from "@/types";
import { formatUSD, formatCompact, formatPercentage, formatAge, cn } from "@/lib/utils";

interface MarketDataProps {
  market: MarketDataResponse;
}

export function MarketData({ market }: MarketDataProps) {
  const stats = [
    {
      label: "Price",
      value: formatUSD(market.price_usd),
      change: market.price_change_24h,
      icon: DollarSign,
    },
    {
      label: "Market Cap",
      value: formatUSD(market.market_cap),
      icon: BarChart3,
    },
    {
      label: "Liquidity",
      value: formatUSD(market.liquidity_usd),
      icon: Droplets,
    },
    {
      label: "Volume 24h",
      value: formatUSD(market.volume_24h),
      icon: TrendingUp,
    },
    {
      label: "Age",
      value: formatAge(market.age_hours),
      icon: Clock,
    },
  ];

  const priceChanges = [
    { label: "5m", value: market.price_change_5m },
    { label: "1h", value: market.price_change_1h },
    { label: "6h", value: market.price_change_6h },
    { label: "24h", value: market.price_change_24h },
  ];

  return (
    <GlassCard>
      <div className="flex items-center gap-2 mb-4">
        <BarChart3 className="h-5 w-5 text-emerald-500" />
        <h3 className="font-semibold">Market Data</h3>
      </div>

      {/* Main stats */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {stats.slice(0, 4).map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className="space-y-1">
              <div className="text-xs text-muted-foreground flex items-center gap-1">
                <Icon className="h-3 w-3" />
                {stat.label}
              </div>
              <div className="font-mono font-semibold">{stat.value}</div>
              {stat.change !== undefined && (
                <div
                  className={cn(
                    "text-xs font-medium",
                    stat.change >= 0 ? "text-emerald-400" : "text-red-400"
                  )}
                >
                  {formatPercentage(stat.change)}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Age and DEX */}
      <div className="flex items-center justify-between py-2 border-t border-border/50">
        <div className="text-sm">
          <span className="text-muted-foreground">Age: </span>
          <span className="font-medium">{formatAge(market.age_hours)}</span>
        </div>
        <div className="text-sm">
          <span className="text-muted-foreground">DEX: </span>
          <span className="font-medium">{market.dex_name}</span>
        </div>
      </div>

      {/* Price changes row */}
      <div className="mt-3 pt-3 border-t border-border/50">
        <div className="text-xs text-muted-foreground mb-2">Price Changes</div>
        <div className="flex justify-between">
          {priceChanges.map((pc) => (
            <div key={pc.label} className="text-center">
              <div className="text-xs text-muted-foreground">{pc.label}</div>
              <div
                className={cn(
                  "font-mono text-sm font-medium",
                  pc.value >= 0 ? "text-emerald-400" : "text-red-400"
                )}
              >
                {formatPercentage(pc.value)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Trading activity */}
      <div className="mt-3 pt-3 border-t border-border/50">
        <div className="text-xs text-muted-foreground mb-2">24h Activity</div>
        <div className="flex justify-between text-sm">
          <div>
            <span className="text-emerald-400">{market.buys_24h}</span>
            <span className="text-muted-foreground"> buys</span>
          </div>
          <div>
            <span className="text-red-400">{market.sells_24h}</span>
            <span className="text-muted-foreground"> sells</span>
          </div>
          <div>
            <span className="text-foreground">{market.txns_24h}</span>
            <span className="text-muted-foreground"> total</span>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
