"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useSmartMoneyOverview } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  TrendingUp,
  TrendingDown,
  Loader2,
  Filter,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { cn, truncateAddress, formatUSD, formatCompact, formatRelativeTime } from "@/lib/utils";

type DirectionFilter = "all" | "inflow" | "outflow";

export default function FlowsPage() {
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [minUsd, setMinUsd] = useState(0);
  const { data, isLoading, isFetching, refetch } = useSmartMoneyOverview();

  const transactions = useMemo(() => {
    if (!data?.recent_transactions) return [];
    let items = data.recent_transactions;
    if (directionFilter !== "all") {
      items = items.filter((t) => t.direction === directionFilter);
    }
    if (minUsd > 0) {
      items = items.filter((t) => Math.abs(t.amount_usd) >= minUsd);
    }
    return items;
  }, [data, directionFilter, minUsd]);

  const summary = useMemo(() => {
    const txs = data?.recent_transactions ?? [];
    const buys = txs.filter((t) => t.direction === "inflow");
    const sells = txs.filter((t) => t.direction === "outflow");
    const buyTotal = buys.reduce((sum, t) => sum + Math.abs(t.amount_usd), 0);
    const sellTotal = sells.reduce((sum, t) => sum + Math.abs(t.amount_usd), 0);
    const net = buyTotal - sellTotal;
    return {
      buyCount: buys.length,
      buyTotal,
      sellCount: sells.length,
      sellTotal,
      net,
    };
  }, [data]);

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-3xl font-bold">Capital Flows</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Smart money transactions on Solana.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn("h-4 w-4 mr-2", isFetching && "animate-spin")} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary bar */}
      <GlassCard className="mb-6 p-4" data-testid="summary-bar">
        <div className="flex flex-wrap items-center gap-6 text-sm">
          <span className="text-emerald-400 font-semibold">
            {summary.buyCount} buys ({formatCompact(summary.buyTotal)})
          </span>
          <span className="text-muted-foreground">&#8226;</span>
          <span className="text-red-400 font-semibold">
            {summary.sellCount} sells ({formatCompact(summary.sellTotal)})
          </span>
          <span className="text-muted-foreground">&#8226;</span>
          <span
            className={cn(
              "font-semibold",
              summary.net >= 0 ? "text-emerald-400" : "text-red-400"
            )}
          >
            Net {summary.net >= 0 ? "+" : ""}{formatCompact(Math.abs(summary.net))}
          </span>
        </div>
      </GlassCard>

      {/* Filter controls */}
      <GlassCard className="mb-6 p-4">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1 block">
              Type
            </label>
            <div className="flex flex-wrap gap-2">
              {(["all", "inflow", "outflow"] as const).map((dir) => (
                <Button
                  key={dir}
                  size="sm"
                  variant={directionFilter === dir ? "default" : "outline"}
                  onClick={() => setDirectionFilter(dir)}
                >
                  {dir === "all" ? "All" : dir === "inflow" ? "Buys" : "Sells"}
                </Button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1 block">
              Min Amount (USD)
            </label>
            <Input
              type="number"
              value={minUsd}
              onChange={(e) => setMinUsd(Number(e.target.value))}
              placeholder="0"
              className="w-32"
            />
          </div>
          <Badge variant="outline">Solana</Badge>
        </div>
      </GlassCard>

      {/* Transaction list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : transactions.length === 0 ? (
        <GlassCard className="text-center py-12">
          <Filter className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">No transactions match the current filters.</p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {transactions.map((tx, index) => {
            const isBuy = tx.direction === "inflow";
            return (
              <GlassCard
                key={tx.signature || `${tx.direction}-${index}`}
                className="p-4 hover:border-emerald-500/30 transition"
              >
                <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                  {/* Left: direction icon + wallet + label */}
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
                        isBuy ? "bg-emerald-500/20" : "bg-red-500/20"
                      )}
                    >
                      {isBuy ? (
                        <TrendingUp className="h-5 w-5 text-emerald-400" />
                      ) : (
                        <TrendingDown className="h-5 w-5 text-red-400" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/wallet/${tx.wallet_address}`}
                          className="font-mono text-sm hover:text-emerald-400 transition"
                        >
                          {truncateAddress(tx.wallet_address, 4)}
                        </Link>
                        {tx.wallet_label && (
                          <Badge variant="secondary" className="text-xs">
                            {tx.wallet_label}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {tx.token_symbol} ({tx.token_name})
                      </p>
                    </div>
                  </div>

                  {/* Right: amount + metadata + link */}
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="text-right">
                      <span
                        className={cn(
                          "font-mono font-semibold text-lg block",
                          isBuy ? "text-emerald-400" : "text-red-400"
                        )}
                      >
                        {isBuy ? "+" : "-"}{formatUSD(Math.abs(tx.amount_usd))}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {tx.amount_tokens.toLocaleString()} {tx.token_symbol}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">{tx.dex_name}</Badge>
                      <Badge variant="outline" className="text-xs">SOL</Badge>
                    </div>

                    <span className="text-xs text-muted-foreground">
                      {formatRelativeTime(tx.timestamp)}
                    </span>

                    <a
                      href={`https://solscan.io/tx/${tx.signature}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted-foreground hover:text-emerald-400 transition"
                      aria-label="View on Solscan"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      {/* Last updated */}
      {data?.updated_at && (
        <p className="text-xs text-muted-foreground text-center mt-6">
          Last updated: {new Date(data.updated_at).toLocaleTimeString()}
        </p>
      )}
    </section>
  );
}
