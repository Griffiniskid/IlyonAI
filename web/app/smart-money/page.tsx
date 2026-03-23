"use client";

import { useSmartMoneyOverview } from "@/lib/hooks";
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
  Wallet,
} from "lucide-react";
import { cn, truncateAddress, formatUSD, formatRelativeTime } from "@/lib/utils";
import type { SmartMoneyParticipant, SmartMoneyFlow } from "@/types";

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
                  <Link
                    href={`/wallet/${p.wallet_address}`}
                    className="font-mono text-primary hover:underline"
                  >
                    {truncateAddress(p.wallet_address, 4)}
                  </Link>
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

export default function SmartMoneyPage() {
  const { data, isLoading, isFetching, refetch } = useSmartMoneyOverview();

  const netFlow = data?.net_flow_usd ?? 0;
  const inflow = data?.inflow_usd ?? 0;
  const outflow = data?.outflow_usd ?? 0;
  const flowDirection = data?.flow_direction ?? "neutral";
  const updatedAt = data?.updated_at ? new Date(data.updated_at) : null;
  const hasValidUpdatedAt = Boolean(updatedAt && !Number.isNaN(updatedAt.getTime()));
  const recentTxns = (data?.recent_transactions ?? []).slice(0, 10);

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-3xl font-bold">Smart Money</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Track coordinated flows and entity-level capital movements across chains.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn("h-4 w-4 mr-2", isFetching && "animate-spin")} />
            Refresh
          </Button>
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

          {/* Top Buyers Table */}
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

            {/* Top Sellers Table */}
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

          {/* Recent Transactions Feed */}
          <GlassCard className="p-4 mb-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">
              Recent Transactions
            </h2>
            {recentTxns.length > 0 ? (
              <div className="space-y-2">
                {recentTxns.map((tx) => {
                  const inflow = isInflowDirection(tx.direction);
                  return (
                    <div
                      key={tx.signature}
                      className="flex flex-wrap items-center gap-3 text-sm border-b border-white/5 pb-2"
                    >
                      {inflow ? (
                        <TrendingUp className="h-4 w-4 text-emerald-500 shrink-0" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-500 shrink-0" />
                      )}
                      <Link
                        href={`/wallet/${tx.wallet_address}`}
                        className="font-mono text-primary hover:underline"
                      >
                        {truncateAddress(tx.wallet_address, 4)}
                      </Link>
                      {tx.wallet_label && (
                        <Badge variant="secondary" className="text-xs">
                          {tx.wallet_label}
                        </Badge>
                      )}
                      <span className="font-mono">{tx.token_symbol}</span>
                      <span
                        className={cn(
                          "font-mono",
                          inflow ? "text-emerald-400" : "text-red-400",
                        )}
                      >
                        {formatUSD(tx.amount_usd)}
                      </span>
                      <span className="text-muted-foreground">{tx.dex_name}</span>
                      <Badge variant="outline" className="text-xs">
                        {tx.chain}
                      </Badge>
                      <span className="text-muted-foreground ml-auto">
                        {formatRelativeTime(tx.timestamp)}
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No recent transactions.</p>
            )}
          </GlassCard>

          {/* Navigation Links */}
          <div className="flex flex-wrap gap-3 mb-6">
            <Button asChild variant="outline" size="sm">
              <Link href="/flows">
                <Activity className="h-4 w-4 mr-2" />
                Explore Flows
                <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/entity">
                <Users className="h-4 w-4 mr-2" />
                Entity Explorer
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/wallet">
                <Wallet className="h-4 w-4 mr-2" />
                Wallet Lookup
              </Link>
            </Button>
          </div>

          {/* Last Updated */}
          {hasValidUpdatedAt && updatedAt && (
            <p className="text-xs text-muted-foreground">
              Last updated: {updatedAt.toLocaleTimeString()} - Flow data refreshes every minute.
            </p>
          )}
        </>
      )}
    </section>
  );
}
