"use client";

import { useState, useMemo } from "react";
import { useWhaleStream } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import {
  TrendingUp,
  TrendingDown,
  ArrowRight,
  Loader2,
  RefreshCw,
  Activity,
  Users,
  ExternalLink,
  Radio,
} from "lucide-react";
import { cn, truncateAddress, formatUSD, formatRelativeTime } from "@/lib/utils";
import type { SmartMoneyParticipant } from "@/types";

function FlowDirectionLabel({ direction }: { direction: string }) {
  const normalized = direction?.toLowerCase() ?? "neutral";
  if (normalized === "accumulating") {
    return <span className="text-2xl font-semibold text-emerald-400">Accumulating</span>;
  }
  if (normalized === "distributing") {
    return <span className="text-2xl font-semibold text-red-400">Distributing</span>;
  }
  return <span className="text-2xl font-semibold text-muted-foreground">Neutral</span>;
}

function StreamStatusBadge({ status }: { status: string }) {
  if (status === "live") {
    return (
      <Badge variant="outline" className="text-xs border-emerald-500/50 text-emerald-400 gap-1">
        <Radio className="h-3 w-3 animate-pulse" />
        Live
      </Badge>
    );
  }
  if (status === "reconnecting") {
    return (
      <Badge variant="outline" className="text-xs border-yellow-500/50 text-yellow-400 gap-1">
        <Radio className="h-3 w-3" />
        Reconnecting...
      </Badge>
    );
  }
  if (status === "polling") {
    return (
      <Badge variant="outline" className="text-xs border-blue-500/50 text-blue-400 gap-1">
        <RefreshCw className="h-3 w-3" />
        Polling
      </Badge>
    );
  }
  return null;
}

function SolscanWalletLink({
  address,
  chars = 4,
}: {
  address: string;
  chars?: number;
}) {
  return (
    <a
      href={`https://solscan.io/account/${address}`}
      target="_blank"
      rel="noopener noreferrer"
      className="font-mono text-primary hover:underline inline-flex items-center gap-1"
    >
      {truncateAddress(address, chars)}
      <ExternalLink className="h-3 w-3 opacity-50" />
    </a>
  );
}

function ParticipantTable({
  participants,
  emptyMessage,
}: {
  participants: SmartMoneyParticipant[];
  emptyMessage: string;
}) {
  if (!participants || participants.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/10 text-muted-foreground text-xs uppercase tracking-wide">
            <th className="py-2 text-left">Wallet</th>
            <th className="py-2 text-right">Amount (USD)</th>
            <th className="py-2 text-right">Txns</th>
            <th className="py-2 text-left">Token</th>
            <th className="py-2 text-left">DEX</th>
            <th className="py-2 text-right">Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {participants.map((p) => (
            <tr key={p.wallet_address} className="border-b border-white/5">
              <td className="py-2">
                <div className="flex items-center gap-2">
                  <SolscanWalletLink address={p.wallet_address} />
                  {p.label && (
                    <Badge variant="secondary" className="text-xs">
                      {p.label}
                    </Badge>
                  )}
                </div>
              </td>
              <td className="py-2 text-right font-mono">{formatUSD(p.amount_usd)}</td>
              <td className="py-2 text-right">{p.tx_count}</td>
              <td className="py-2">{p.token_symbol}</td>
              <td className="py-2">{p.dex_name}</td>
              <td className="py-2 text-right text-muted-foreground">
                {formatRelativeTime(p.last_seen)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isInflowDirection(direction: string): boolean {
  const d = direction?.toLowerCase() ?? "";
  return d === "buy" || d === "inflow";
}

type DirectionFilter = "all" | "inflow" | "outflow";

export default function SmartMoneyPage() {
  const { data, isLoading, isFetching, streamStatus } = useWhaleStream();
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [minUsd, setMinUsd] = useState(0);

  const netFlow = data?.net_flow_usd ?? 0;
  const inflow = data?.inflow_usd ?? 0;
  const outflow = data?.outflow_usd ?? 0;
  const flowDirection = data?.flow_direction ?? "neutral";
  const updatedAt = data?.updated_at ? new Date(data.updated_at) : null;
  const hasValidUpdatedAt = Boolean(updatedAt && !Number.isNaN(updatedAt.getTime()));

  const filteredTxns = useMemo(() => {
    let items = data?.recent_transactions ?? [];
    if (directionFilter !== "all") {
      items = items.filter((t) => t.direction === directionFilter);
    }
    if (minUsd > 0) {
      items = items.filter((t) => Math.abs(t.amount_usd) >= minUsd);
    }
    return items.slice(0, 100);
  }, [data, directionFilter, minUsd]);

  const summary = useMemo(() => {
    const txs = data?.recent_transactions ?? [];
    const buys = txs.filter((t) => isInflowDirection(t.direction));
    const sells = txs.filter((t) => !isInflowDirection(t.direction));
    return {
      buyCount: buys.length,
      buyTotal: buys.reduce((s, t) => s + Math.abs(t.amount_usd), 0),
      sellCount: sells.length,
      sellTotal: sells.reduce((s, t) => s + Math.abs(t.amount_usd), 0),
    };
  }, [data]);

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-3xl font-bold">Smart Money</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time whale transaction feed. $10K+ DEX swaps on Solana.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StreamStatusBadge status={streamStatus} />
          <Button asChild size="sm" className="bg-emerald-600 hover:bg-emerald-500">
            <Link href="/whales">
              <Activity className="h-4 w-4 mr-2" />
              Open Whales Feed
              <ArrowRight className="h-4 w-4 ml-2" />
            </Link>
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : (
        <>
          {/* Metrics Row */}
          <div className="grid gap-4 md:grid-cols-4 mb-8">
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Net Flow
              </p>
              <p
                className={cn(
                  "text-2xl font-semibold",
                  netFlow >= 0 ? "text-emerald-400" : "text-red-400",
                )}
              >
                {netFlow >= 0 ? "+" : ""}
                {formatUSD(Math.abs(netFlow))}
              </p>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Inflow
              </p>
              <p className="text-2xl font-semibold text-emerald-400">
                <TrendingUp className="inline h-5 w-5 mr-1" />
                {formatUSD(inflow)}
              </p>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Outflow
              </p>
              <p className="text-2xl font-semibold text-red-400">
                <TrendingDown className="inline h-5 w-5 mr-1" />
                {formatUSD(outflow)}
              </p>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
                Flow Direction
              </p>
              <FlowDirectionLabel direction={flowDirection} />
            </GlassCard>
          </div>

          {/* Top Buyers / Top Sellers */}
          <div className="grid gap-6 lg:grid-cols-2 mb-8">
            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Top Buyers
                </h2>
                <TrendingUp className="h-4 w-4 text-emerald-500" />
              </div>
              <ParticipantTable
                participants={data?.top_buyers ?? []}
                emptyMessage="No buyer data available."
              />
            </GlassCard>

            <GlassCard className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Top Sellers
                </h2>
                <TrendingDown className="h-4 w-4 text-red-500" />
              </div>
              <ParticipantTable
                participants={data?.top_sellers ?? []}
                emptyMessage="No seller data available."
              />
            </GlassCard>
          </div>

          {/* Transaction Feed (merged from flows) */}
          <GlassCard className="p-4 mb-8">
            {/* Summary bar */}
            <div className="flex flex-wrap items-center gap-4 mb-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Transaction Feed
              </h2>
              <div className="flex items-center gap-3 text-xs ml-auto">
                <span className="text-emerald-400">
                  {summary.buyCount} buys ({formatUSD(summary.buyTotal)})
                </span>
                <span className="text-red-400">
                  {summary.sellCount} sells ({formatUSD(summary.sellTotal)})
                </span>
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3 mb-4">
              {(["all", "inflow", "outflow"] as const).map((opt) => (
                <Button
                  key={opt}
                  variant={directionFilter === opt ? "default" : "outline"}
                  size="sm"
                  onClick={() => setDirectionFilter(opt)}
                  className="text-xs capitalize"
                >
                  {opt === "all" ? "All" : opt === "inflow" ? "Buys" : "Sells"}
                </Button>
              ))}
              <input
                type="number"
                placeholder="Min USD"
                value={minUsd || ""}
                onChange={(e) => setMinUsd(Number(e.target.value) || 0)}
                className="px-2 py-1 text-xs rounded bg-white/5 border border-white/10 w-24"
              />
              <Badge variant="outline" className="text-xs">
                Solana
              </Badge>
            </div>

            {/* Transaction list */}
            {filteredTxns.length > 0 ? (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {filteredTxns.map((tx) => {
                  const isInflow = isInflowDirection(tx.direction);
                  return (
                    <div
                      key={tx.signature || `${tx.wallet_address}-${tx.timestamp}`}
                      className="flex flex-wrap items-center gap-3 text-sm border-b border-white/5 pb-2"
                    >
                      {isInflow ? (
                        <TrendingUp className="h-4 w-4 text-emerald-500 shrink-0" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-500 shrink-0" />
                      )}
                      <SolscanWalletLink address={tx.wallet_address} />
                      {tx.wallet_label && (
                        <Badge variant="secondary" className="text-xs">
                          {tx.wallet_label}
                        </Badge>
                      )}
                      <span className="font-mono">{tx.token_symbol}</span>
                      <span
                        className={cn(
                          "font-mono",
                          isInflow ? "text-emerald-400" : "text-red-400",
                        )}
                      >
                        {formatUSD(tx.amount_usd)}
                      </span>
                      <span className="text-muted-foreground">{tx.dex_name}</span>
                      {tx.signature && (
                        <a
                          href={`https://solscan.io/tx/${tx.signature}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-muted-foreground hover:text-primary"
                        >
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      <span className="text-muted-foreground ml-auto">
                        {formatRelativeTime(tx.timestamp)}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-4">
                No transactions match your filters. Whale transactions ($10K+) are accumulated over 24 hours.
              </p>
            )}
          </GlassCard>

          {/* Navigation Links */}
          <div className="flex flex-wrap gap-3 mb-6">
            <Button asChild variant="outline" size="sm">
              <Link href="/entity">
                <Users className="h-4 w-4 mr-2" />
                Entity Explorer
              </Link>
            </Button>
          </div>

          {/* Footer */}
          {hasValidUpdatedAt && updatedAt && (
            <p className="text-xs text-muted-foreground">
              Last updated: {updatedAt.toLocaleTimeString()} - Data streams in real-time via WebSocket.
            </p>
          )}
        </>
      )}
    </section>
  );
}
