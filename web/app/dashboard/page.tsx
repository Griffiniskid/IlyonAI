"use client";

import { useState } from "react";
import Link from "next/link";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useTrendingTokens, useWhaleActivity, useDashboardStats } from "@/lib/hooks";
import {
  Activity,
  Users,
  BarChart3,
  Zap,
  Shield,
  Eye,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  ExternalLink,
  Flame,
  DollarSign,
  TrendingUp,
  Coins,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  PieChart,
  Pie,
} from "recharts";
import { formatUSD, formatCompact, formatPercentage, cn } from "@/lib/utils";
import type { RiskDistributionItem, VolumeDataPoint, MarketDistributionItem } from "@/types";

// Stat Card Component
function StatCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
  trend,
  loading,
}: {
  title: string;
  value: string;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
  icon: React.ElementType;
  trend?: number[];
  loading?: boolean;
}) {
  return (
    <GlassCard className="relative overflow-hidden">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs sm:text-sm text-muted-foreground mb-1">{title}</p>
          {loading ? (
            <div className="h-8 w-24 bg-muted/50 animate-pulse rounded" />
          ) : (
            <p className="text-lg sm:text-2xl font-bold truncate">{value}</p>
          )}
          {change && !loading && (
            <div className="flex items-center gap-1 mt-1">
              {changeType === "positive" ? (
                <ArrowUpRight className="w-3 h-3 sm:w-4 sm:h-4 text-emerald-400 shrink-0" />
              ) : changeType === "negative" ? (
                <ArrowDownRight className="w-3 h-3 sm:w-4 sm:h-4 text-red-400 shrink-0" />
              ) : null}
              <span
                className={cn(
                  "text-xs sm:text-sm truncate",
                  changeType === "positive"
                    ? "text-emerald-400"
                    : changeType === "negative"
                    ? "text-red-400"
                    : "text-muted-foreground"
                )}
              >
                {change}
              </span>
            </div>
          )}
        </div>
        <div className="w-9 h-9 sm:w-12 sm:h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0 ml-2">
          <Icon className="w-4 h-4 sm:w-6 sm:h-6 text-emerald-400" />
        </div>
      </div>

      {/* Mini trend chart */}
      {trend && trend.length > 0 && (
        <div className="absolute bottom-0 left-0 right-0 h-12 opacity-30">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trend.map((v) => ({ v }))}>
              <Area
                type="monotone"
                dataKey="v"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </GlassCard>
  );
}

// Quick Token Card
function QuickTokenCard({
  rank,
  symbol,
  name,
  price,
  change,
  address,
  chain,
}: {
  rank: number;
  symbol: string;
  name: string;
  price: number;
  change: number;
  address: string;
  chain?: string;
}) {
  return (
    <Link href={`/token/${address}${chain ? `?chain=${chain}` : ""}`}>
      <div className="token-row group cursor-pointer">
        <div className="flex items-center gap-4 flex-1">
          <span className="text-muted-foreground font-mono w-6">#{rank}</span>
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-emerald-400/20 to-emerald-600/20 flex items-center justify-center text-emerald-400 font-bold border border-emerald-500/20">
            {symbol[0]}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-semibold group-hover:text-emerald-400 transition-colors truncate">
              {symbol}
            </div>
            <div className="text-xs text-muted-foreground truncate">{name}{chain ? ` · ${chain}` : ""}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono">{formatUSD(price)}</div>
          <div
            className={cn(
              "text-sm font-mono",
              change >= 0 ? "text-emerald-400" : "text-red-400"
            )}
          >
            {formatPercentage(change)}
          </div>
        </div>
        <ExternalLink className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ml-2" />
      </div>
    </Link>
  );
}

// Format relative time
function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);

  if (diffSecs < 60) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.floor(diffHours / 24)}d ago`;
}

// Smart Money Alert
function SmartMoneyAlert({
  type,
  wallet,
  walletAddress,
  token,
  amount,
  timestamp,
}: {
  type: "buy" | "sell";
  wallet: string;
  walletAddress: string;
  token: string;
  amount: number;
  timestamp: string;
}) {
  return (
    <Link href={`/wallet/${walletAddress}`} className="block">
      <div className="flex items-center gap-4 p-4 rounded-xl bg-white/5 hover:bg-white/10 transition-colors cursor-pointer">
        <div
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center",
            type === "buy" ? "bg-emerald-500/20" : "bg-red-500/20"
          )}
        >
          {type === "buy" ? (
            <ArrowUpRight className="w-5 h-5 text-emerald-400" />
          ) : (
            <ArrowDownRight className="w-5 h-5 text-red-400" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{wallet}</span>
            <span className="text-muted-foreground">{type === "buy" ? "bought" : "sold"}</span>
            <span className="text-emerald-400">{token}</span>
          </div>
          <div className="text-sm text-muted-foreground">
            {formatUSD(amount)} · {formatRelativeTime(timestamp)}
          </div>
        </div>
      </div>
    </Link>
  );
}

// Format volume for chart axis (handles billions)
function formatVolumeAxis(value: number): string {
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(1)}B`;
  } else if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(0)}M`;
  } else if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`;
  }
  return `$${value.toFixed(0)}`;
}

// Format volume for tooltip (more precise)
function formatVolumeTooltip(value: number): string {
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  } else if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  } else if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(2)}K`;
  }
  return `$${value.toFixed(2)}`;
}

export default function DashboardPage() {
  const { data: statsData, isLoading: statsLoading, refetch: refetchStats } = useDashboardStats();
  const { data: trendingData, isLoading: trendingLoading, refetch: refetchTrending } = useTrendingTokens("trending");
  const { data: whaleData, isLoading: whalesLoading, refetch: refetchWhales } = useWhaleActivity({ limit: 5 });
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([refetchStats(), refetchTrending(), refetchWhales()]);
    setRefreshing(false);
  };

  // Generate trend data from volume chart
  const volumeTrend = statsData?.volume_chart?.map((d: VolumeDataPoint) => d.volume) || [];

  // Calculate market distribution percentages for pie chart
  const marketDistributionData = statsData?.market_distribution?.map((item: MarketDistributionItem) => ({
    name: item.name,
    value: item.value,
    color: item.color,
  })) || [];

  const totalMarketItems = marketDistributionData.reduce((sum: number, item: { value: number }) => sum + item.value, 0);

  return (
    <div id="market-overviews" className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
          <p className="text-muted-foreground">
            Real-time overview of the Solana token ecosystem
          </p>
        </div>
        <Button
          variant="outline"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          <RefreshCw className={cn("h-4 w-4 mr-2", refreshing && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Stats Grid - Updated metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4 mb-8">
        <StatCard
          title="24h Volume"
          value={statsData ? formatCompact(statsData.total_volume_24h) : "$0"}
          change={statsData ? `${statsData.volume_change_24h > 0 ? "+" : ""}${statsData.volume_change_24h.toFixed(1)}%` : undefined}
          changeType={statsData ? (statsData.volume_change_24h >= 0 ? "positive" : "negative") : "neutral"}
          icon={BarChart3}
          trend={volumeTrend}
          loading={statsLoading}
        />
        <StatCard
          title="Solana TVL"
          value={statsData ? formatCompact(statsData.solana_tvl || 0) : "$0"}
          change="Total value locked"
          changeType="neutral"
          icon={DollarSign}
          loading={statsLoading}
        />
        <StatCard
          title="Total Liquidity"
          value={statsData ? formatCompact(statsData.total_liquidity) : "$0"}
          change="Tracked tokens"
          changeType="neutral"
          icon={TrendingUp}
          loading={statsLoading}
        />
        <StatCard
          title="SOL Price"
          value={statsData ? `$${(statsData.sol_price || 0).toFixed(2)}` : "$0"}
          change={statsData ? `${statsData.sol_price_change_24h > 0 ? "+" : ""}${(statsData.sol_price_change_24h || 0).toFixed(2)}% (24h)` : undefined}
          changeType={statsData ? (statsData.sol_price_change_24h >= 0 ? "positive" : "negative") : "neutral"}
          icon={Coins}
          loading={statsLoading}
        />
      </div>

      {/* Charts Row */}
      <div className="grid lg:grid-cols-3 gap-4 md:gap-6 mb-8">
        {/* Volume Chart - Now with proper hourly data */}
        <GlassCard className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4 md:mb-6">
            <h3 className="text-base md:text-lg font-semibold">Trading Volume (24h)</h3>
            <Badge variant="outline">Live</Badge>
          </div>
          <div className="h-48 md:h-64">
            {statsLoading ? (
              <div className="flex items-center justify-center h-full">
                <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={statsData?.volume_chart || []}>
                  <defs>
                    <linearGradient id="volumeGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis 
                    dataKey="time" 
                    stroke="rgba(255,255,255,0.5)" 
                    fontSize={12}
                    interval="preserveStartEnd"
                    tickFormatter={(value) => value}
                  />
                  <YAxis
                    stroke="rgba(255,255,255,0.5)"
                    fontSize={12}
                    tickFormatter={formatVolumeAxis}
                    width={70}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(222, 47%, 7%)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "8px",
                      color: "#e2e8f0",
                    }}
                    itemStyle={{ color: "#e2e8f0" }}
                    labelStyle={{ color: "#94a3b8" }}
                    formatter={(value: number) => [formatVolumeTooltip(value), "Volume"]}
                    labelFormatter={(label) => `Time: ${label}`}
                  />
                  <Area
                    type="monotone"
                    dataKey="volume"
                    stroke="#10b981"
                    strokeWidth={2}
                    fill="url(#volumeGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </GlassCard>

        {/* Market Distribution Donut Chart */}
        <GlassCard>
          <h3 className="text-lg font-semibold mb-6">Market Distribution</h3>
          <div className="h-48">
            {statsLoading ? (
              <div className="flex items-center justify-center h-full">
                <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : marketDistributionData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={marketDistributionData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {marketDistributionData.map((entry: { name: string; color: string }, index: number) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(222, 47%, 7%)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "8px",
                      color: "#e2e8f0",
                    }}
                    itemStyle={{ color: "#e2e8f0" }}
                    labelStyle={{ color: "#94a3b8" }}
                    formatter={(value: number, name: string) => [
                      `${value} (${totalMarketItems > 0 ? ((value / totalMarketItems) * 100).toFixed(0) : 0}%)`,
                      name
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                No data available
              </div>
            )}
          </div>
          {/* Legend */}
          <div className="grid grid-cols-2 gap-2 mt-4">
            {marketDistributionData.map((item: { name: string; value: number; color: string }) => (
              <div key={item.name} className="flex items-center gap-2 text-sm">
                <div 
                  className="w-3 h-3 rounded-full" 
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-muted-foreground">{item.name}</span>
                <span className="ml-auto font-medium">
                  {totalMarketItems > 0 ? ((item.value / totalMarketItems) * 100).toFixed(0) : 0}%
                </span>
              </div>
            ))}
          </div>
        </GlassCard>
      </div>

      {/* Second row: Risk Analysis */}
      <div className="grid lg:grid-cols-3 gap-4 md:gap-6 mb-8">
        {/* Risk Distribution Chart */}
        <GlassCard>
          <h3 className="text-lg font-semibold mb-6">Grade Distribution</h3>
          <div className="h-48">
            {statsLoading ? (
              <div className="flex items-center justify-center h-full">
                <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : (statsData?.risk_distribution || []).some((d: RiskDistributionItem) => d.count > 0) ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statsData?.risk_distribution || []} layout="vertical">
                  <XAxis type="number" stroke="rgba(255,255,255,0.5)" fontSize={12} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="rgba(255,255,255,0.5)"
                    fontSize={12}
                    width={60}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(222, 47%, 7%)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: "8px",
                      color: "#e2e8f0",
                    }}
                    itemStyle={{ color: "#e2e8f0" }}
                    labelStyle={{ color: "#94a3b8" }}
                  />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {(statsData?.risk_distribution || []).map((entry: RiskDistributionItem, index: number) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                No tokens analyzed yet
              </div>
            )}
          </div>
          <div className="text-center mt-4">
            <p className="text-sm text-muted-foreground">
              <span className="text-emerald-400 font-semibold">
                {statsData?.total_tokens_analyzed || 0}
              </span> tokens analyzed total
              {(statsData?.tokens_analyzed_today || 0) > 0 && (
                <span> · <span className="text-emerald-400 font-semibold">{statsData?.tokens_analyzed_today}</span> today</span>
              )}
            </p>
          </div>
        </GlassCard>

        {/* Trending Tokens */}
        <GlassCard className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Flame className="w-5 h-5 text-orange-400" />
              <h3 className="text-lg font-semibold">Trending Tokens</h3>
            </div>
            <Link href="/trending">
              <Button variant="ghost" size="sm">
                View All
                <ExternalLink className="w-4 h-4 ml-1" />
              </Button>
            </Link>
          </div>
          <div className="space-y-2">
            {trendingLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : trendingData?.tokens.slice(0, 5).map((token, i) => (
              <QuickTokenCard
                key={`${token.chain}-${token.address}`}
                rank={i + 1}
                symbol={token.symbol}
                name={token.name}
                price={token.price_usd}
                change={token.price_change_24h}
                address={token.address}
                chain={token.chain}
              />
            ))}
            {!trendingLoading && (!trendingData?.tokens || trendingData.tokens.length === 0) && (
              <p className="text-center text-muted-foreground py-8">
                No trending tokens found
              </p>
            )}
          </div>
        </GlassCard>
      </div>

      {/* Smart Money Alerts */}
      <GlassCard>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-yellow-400" />
            <h3 className="text-lg font-semibold">Smart Money Activity</h3>
          </div>
          <Link href="/whales">
            <Button variant="ghost" size="sm">
              View All
              <ExternalLink className="w-4 h-4 ml-1" />
            </Button>
          </Link>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          {whalesLoading ? (
            <div className="col-span-2 flex items-center justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : whaleData?.transactions.slice(0, 4).map((tx, i) => (
            <SmartMoneyAlert
              key={tx.signature || i}
              type={tx.type as "buy" | "sell"}
              wallet={tx.wallet_label || `${tx.wallet_address.slice(0, 4)}...${tx.wallet_address.slice(-4)}`}
              walletAddress={tx.wallet_address}
              token={tx.token_symbol}
              amount={tx.amount_usd}
              timestamp={tx.timestamp}
            />
          ))}
          {!whalesLoading && (!whaleData?.transactions || whaleData.transactions.length === 0) && (
            <div className="col-span-2 text-center py-8">
              <Users className="w-12 h-12 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground">No whale activity detected</p>
            </div>
          )}
        </div>
      </GlassCard>

      {/* Last updated */}
      <p className="text-xs text-muted-foreground text-center mt-8">
        Last updated: {new Date().toLocaleTimeString()}
      </p>
    </div>
  );
}
