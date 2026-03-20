"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useWhaleActivity } from "@/lib/hooks";
import * as api from "@/lib/api";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Fish,
  TrendingUp,
  TrendingDown,
  Loader2,
  RefreshCw,
  Filter,
  ExternalLink,
  Clock,
  Search,
} from "lucide-react";
import {
  formatUSD,
  formatCompact,
  formatRelativeTime,
  truncateAddress,
  cn,
} from "@/lib/utils";
import type { ChainName } from "@/types";

const WHALE_CHAINS: ChainName[] = ["solana", "ethereum", "base", "arbitrum"];

export default function WhalesPage() {
  const [minAmount, setMinAmount] = useState(1000);
  const [chainFilter, setChainFilter] = useState<"all" | ChainName>("all");
  const [typeFilter, setTypeFilter] = useState<"buy" | "sell" | undefined>();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const queryClient = useQueryClient();

  const params = {
    minAmountUsd: minAmount,
    chain: chainFilter === "all" ? undefined : chainFilter,
    type: typeFilter,
  };
  const { data, isLoading, isFetching } = useWhaleActivity(params, hasSearched);

  const handleSearch = () => {
    if (hasSearched) {
      // Already searched before — invalidate to re-fetch with current filters
      queryClient.invalidateQueries({ queryKey: ["whales", params] });
    }
    setHasSearched(true);
  };

  const handleForceRefresh = async () => {
    setIsRefreshing(true);
    try {
      const freshData = await api.getWhaleActivity({
        ...params,
        forceRefresh: true,
      });
      queryClient.setQueryData(["whales", params], freshData);
    } catch (e) {
      queryClient.invalidateQueries({ queryKey: ["whales", params] });
    } finally {
      setIsRefreshing(false);
    }
  };

  const busy = isFetching || isRefreshing;

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Fish className="h-8 w-8 text-emerald-500" />
            Whale Tracker
          </h1>
          <p className="text-muted-foreground">
            Monitor large transactions across major chains
          </p>
        </div>
        <Button
          variant="outline"
          onClick={handleForceRefresh}
          disabled={busy}
        >
          <RefreshCw
            className={cn("h-4 w-4 mr-2", busy && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <GlassCard className="mb-8">
        <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-end">
          <div className="flex-1">
            <label className="text-sm text-muted-foreground mb-2 block">
              Minimum Amount (USD)
            </label>
            <Input
              type="number"
              value={minAmount}
              onChange={(e) => setMinAmount(Number(e.target.value))}
              min={1000}
              step={1000}
            />
          </div>
          <div className="flex gap-2">
            <Button
              variant={chainFilter === "all" ? "default" : "outline"}
              onClick={() => setChainFilter("all")}
              className="flex-1 md:flex-initial"
            >
              All Chains
            </Button>
            {WHALE_CHAINS.map((chain) => (
              <Button
                key={chain}
                variant={chainFilter === chain ? "default" : "outline"}
                onClick={() => setChainFilter(chain)}
                className="flex-1 md:flex-initial"
              >
                {chain}
              </Button>
            ))}
          </div>
          <div className="flex gap-2">
            <Button
              variant={typeFilter === undefined ? "default" : "outline"}
              onClick={() => setTypeFilter(undefined)}
              className="flex-1 md:flex-initial"
            >
              All
            </Button>
            <Button
              variant={typeFilter === "buy" ? "default" : "outline"}
              onClick={() => setTypeFilter("buy")}
              className={cn("flex-1 md:flex-initial", typeFilter === "buy" ? "bg-emerald-600" : "")}
            >
              <TrendingUp className="h-4 w-4 mr-1 sm:mr-2" />
              Buys
            </Button>
            <Button
              variant={typeFilter === "sell" ? "default" : "outline"}
              onClick={() => setTypeFilter("sell")}
              className={cn("flex-1 md:flex-initial", typeFilter === "sell" ? "bg-red-600" : "")}
            >
              <TrendingDown className="h-4 w-4 mr-1 sm:mr-2" />
              Sells
            </Button>
          </div>
          <Button
            onClick={handleSearch}
            disabled={busy}
            className="bg-emerald-600 hover:bg-emerald-500 md:ml-auto"
          >
            <Search className="h-4 w-4 mr-2" />
            Search Transactions
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-4">
          Entity confidence: {api.normalizeConfidencePercent(data?.entity_confidence)}%
        </p>
      </GlassCard>

      {/* Initial prompt — before first search */}
      {!hasSearched && !data && (
        <GlassCard className="text-center py-16">
          <Search className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">Search for Whale Activity</h3>
          <p className="text-muted-foreground">
            Set your filters above and click &quot;Search Transactions&quot; to find large trades
          </p>
        </GlassCard>
      )}

      {/* Loading state */}
      {isLoading && hasSearched && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        </div>
      )}

      {/* Transaction list */}
      {data && data.transactions.length > 0 && (
        <div className="space-y-4">
          {data.transactions.map((tx) => (
            <GlassCard
              key={tx.signature}
              className="hover:border-emerald-500/30 transition"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-4">
                <div className="flex items-center gap-3 md:gap-4">
                  {/* Type badge */}
                  <div
                    className={cn(
                      "w-10 h-10 md:w-12 md:h-12 rounded-xl flex items-center justify-center shrink-0",
                      tx.type === "buy"
                        ? "bg-emerald-500/20"
                        : "bg-red-500/20"
                    )}
                  >
                    {tx.type === "buy" ? (
                      <TrendingUp className="h-5 w-5 md:h-6 md:w-6 text-emerald-400" />
                    ) : (
                      <TrendingDown className="h-5 w-5 md:h-6 md:w-6 text-red-400" />
                    )}
                  </div>

                  {/* Token info */}
                  <div className="min-w-0">
                    <Link
                      href={`/token/${tx.token_address}`}
                      className="font-semibold hover:text-emerald-400 transition"
                    >
                      {tx.token_symbol}
                      <span className="text-muted-foreground font-normal ml-2 hidden sm:inline">
                        {tx.token_name}
                      </span>
                    </Link>
                    <div className="text-xs sm:text-sm text-muted-foreground flex items-center gap-1 sm:gap-2">
                      <Clock className="h-3 w-3 shrink-0" />
                      {formatRelativeTime(tx.timestamp)}
                      <span>•</span>
                      {tx.dex_name}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 sm:gap-6 ml-13 md:ml-0">
                  {/* Amount */}
                  <div className="text-left md:text-right flex-1 md:flex-initial">
                    <div
                      className={cn(
                        "font-mono font-bold text-base md:text-lg",
                        tx.type === "buy" ? "text-emerald-400" : "text-red-400"
                      )}
                    >
                      {tx.type === "buy" ? "+" : "-"}
                      {formatUSD(tx.amount_usd)}
                    </div>
                    <div className="text-xs sm:text-sm text-muted-foreground font-mono">
                      {formatCompact(tx.amount_tokens)} tokens
                    </div>
                  </div>

                  {/* Wallet */}
                  <div className="text-right min-w-[80px] sm:min-w-[100px]">
                    <div className="text-xs sm:text-sm">
                      {tx.wallet_label || (
                        <span className="font-mono text-muted-foreground">
                          {truncateAddress(tx.wallet_address, 4)}
                        </span>
                      )}
                    </div>
                    <Badge variant="outline" className="text-xs">
                      Whale
                    </Badge>
                  </div>

                  {/* External link */}
                  <a
                    href={`https://solscan.io/tx/${tx.signature}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-muted-foreground hover:text-foreground transition shrink-0"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Empty state */}
      {data && data.transactions.length === 0 && (
        <GlassCard className="text-center py-12">
          <Fish className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">No Whale Activity</h3>
          <p className="text-muted-foreground">
            No large transactions found matching your filters
          </p>
        </GlassCard>
      )}

      {/* Last updated */}
      {data && (
        <div className="text-center text-sm text-muted-foreground mt-8">
          Minimum: {formatUSD(data.min_amount_usd)} • Last updated:{" "}
          {new Date(data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
