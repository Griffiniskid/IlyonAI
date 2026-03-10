"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Brain,
  Filter,
  Loader2,
  Radar,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Waves,
} from "lucide-react";

import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn, formatCompact } from "@/lib/utils";
import * as api from "@/lib/api";
import type {
  DefiAnalyzerResponse,
  DefiOpportunityResponse,
  DefiProtocolMatch,
  LendingMarketResponse,
  PoolResponse,
  YieldOpportunityResponse,
} from "@/types";

const CHAINS = ["all", "ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche", "solana"];

function scoreVariant(score: number) {
  if (score >= 80) return "safe" as const;
  if (score >= 60) return "caution" as const;
  if (score >= 40) return "risky" as const;
  return "danger" as const;
}

function RiskBadge({ level }: { level: "HIGH" | "MEDIUM" | "LOW" }) {
  return <Badge variant={level === "HIGH" ? "danger" : level === "MEDIUM" ? "caution" : "safe"}>{level}</Badge>;
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03] py-5">
      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-sm text-muted-foreground">{hint}</div>
    </GlassCard>
  );
}

function OpportunityCard({ item }: { item: DefiOpportunityResponse }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03] p-0 overflow-hidden">
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{item.kind}</Badge>
              <Badge variant="outline" className="capitalize">{item.chain}</Badge>
              {item.tags.slice(0, 2).map((tag) => (
                <Badge key={tag} variant="secondary" className="bg-white/5 text-muted-foreground border-white/10">
                  {tag}
                </Badge>
              ))}
            </div>
            <h3 className="mt-3 text-xl font-semibold leading-tight">{item.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{item.subtitle}</p>
          </div>
          <Badge variant={scoreVariant(item.summary.opportunity_score)}>
            Score {item.summary.opportunity_score}
          </Badge>
        </div>

        <p className="mt-4 text-sm text-foreground/90">{item.summary.headline}</p>
        <p className="mt-2 text-sm text-muted-foreground">{item.summary.thesis}</p>

        <div className="mt-5 grid gap-3 sm:grid-cols-4">
          <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">APY</div>
            <div className="mt-2 text-lg font-semibold text-emerald-400">{item.apy.toFixed(2)}%</div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Safety</div>
            <div className="mt-2 text-lg font-semibold">{item.summary.safety_score}</div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Yield Quality</div>
            <div className="mt-2 text-lg font-semibold">{item.summary.yield_quality_score}</div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/20 p-3">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Confidence</div>
            <div className="mt-2 text-lg font-semibold">{item.summary.confidence_score}</div>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2 text-xs text-muted-foreground">
          {item.evidence.slice(0, 3).map((evidence) => (
            <span key={evidence.key} className="rounded-full border border-white/10 bg-white/5 px-2 py-1">
              {evidence.title}
            </span>
          ))}
        </div>
      </div>

      <div className="border-t border-white/10 bg-black/20 px-5 py-3 flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          Best for <span className="capitalize text-foreground">{item.summary.strategy_fit}</span> capital
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href={`/defi/opportunity/${item.id}`}>
            Open Analysis <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </div>
    </GlassCard>
  );
}

function ProtocolSpotlight({ protocol }: { protocol: DefiProtocolMatch }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{protocol.name}</div>
          <div className="mt-1 text-sm text-muted-foreground">{protocol.category || "DeFi protocol"}</div>
        </div>
        <Badge variant="outline">{formatCompact(protocol.tvl)}</Badge>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        {(protocol.chains || []).slice(0, 4).map((chain) => (
          <span key={chain} className="rounded-full border border-white/10 px-2 py-1">{chain}</span>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between text-sm">
        <div className="text-muted-foreground">
          Best opportunity {protocol.best_opportunity_score ?? 0}
        </div>
        <Button asChild size="sm" variant="ghost">
          <Link href={`/defi/protocol/${protocol.slug}`}>
            Protocol view <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </div>
    </GlassCard>
  );
}

function CompactPoolCard({ pool }: { pool: PoolResponse | YieldOpportunityResponse }) {
  const sustainability = "sustainability_ratio" in pool ? pool.sustainability_ratio : null;
  return (
    <GlassCard className="border-white/10 bg-white/[0.03]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold">{pool.symbol}</span>
            <Badge variant="outline" className="capitalize">{pool.chain}</Badge>
          </div>
          <div className="mt-2 text-sm text-muted-foreground">{pool.project}</div>
        </div>
        <RiskBadge level={pool.risk_level} />
      </div>
      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        <span>TVL <span className="font-semibold">{formatCompact(pool.tvlUsd)}</span></span>
        <span>APY <span className="font-semibold text-emerald-400">{pool.apy.toFixed(2)}%</span></span>
        {sustainability != null && (
          <span>Fees-backed <span className="font-semibold">{(sustainability * 100).toFixed(0)}%</span></span>
        )}
      </div>
    </GlassCard>
  );
}

function CompactLendingCard({ market }: { market: LendingMarketResponse }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{market.protocol_display}</div>
          <div className="mt-1 text-sm text-muted-foreground">{market.symbol} on {market.chain}</div>
        </div>
        <Badge variant={scoreVariant(100 - market.combined_risk_score)}>
          Risk {market.combined_risk_score.toFixed(0)}
        </Badge>
      </div>
      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        <span>Supply <span className="font-semibold text-emerald-400">{market.apy_supply.toFixed(2)}%</span></span>
        <span>Borrow <span className="font-semibold">{market.apy_borrow.toFixed(2)}%</span></span>
        <span>Util <span className="font-semibold">{market.utilization_pct.toFixed(0)}%</span></span>
      </div>
    </GlassCard>
  );
}

export default function DefiPage() {
  const [chain, setChain] = useState("all");
  const [query, setQuery] = useState("");
  const [minApy, setMinApy] = useState("3");
  const [minTvl, setMinTvl] = useState("100000");

  const params = useMemo(() => ({
    chain: chain !== "all" ? chain : undefined,
    query: query.trim() || undefined,
    minApy: minApy ? parseFloat(minApy) : undefined,
    minTvl: minTvl ? parseFloat(minTvl) : undefined,
    limit: 10,
    includeAi: true,
    rankingProfile: "balanced",
  }), [chain, query, minApy, minTvl]);

  const analyzerQuery = useQuery({
    queryKey: ["defi-analyzer-v2", params],
    queryFn: () => api.analyzeDefi(params),
    staleTime: 60_000,
  });

  const data: DefiAnalyzerResponse | undefined = analyzerQuery.data;

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 overflow-hidden rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_38%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.14),transparent_34%),rgba(7,10,18,0.92)] p-6 md:p-8">
        <div className="max-w-4xl">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs uppercase tracking-[0.18em] text-emerald-300">
            <ShieldCheck className="h-3.5 w-3.5" /> Advanced DeFi Intelligence
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Rank deployable capital paths, inspect protocol quality, and see what can break before you enter.
          </h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-300 md:text-base">
            This view now prioritizes opportunity intelligence over raw tables: risk-adjusted rankings, evidence, scenario stress, protocol spotlights, and an AI market brief.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button asChild className="bg-emerald-500 text-black hover:bg-emerald-400">
              <Link href="/defi/compare">Compare protocols</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/defi/lending">Run simulations</Link>
            </Button>
          </div>
        </div>
      </div>

      <GlassCard className="mb-6 border-white/10 bg-white/[0.03]">
        <div className="mb-4 flex items-center gap-2 text-sm font-medium">
          <Filter className="h-4 w-4 text-muted-foreground" /> Discovery Filters
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Search protocol or asset</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" placeholder="aave, curve, usdc, eth..." />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Chain</label>
            <select value={chain} onChange={(e) => setChain(e.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm capitalize">
              {CHAINS.map((item) => (
                <option key={item} value={item}>{item === "all" ? "All Chains" : item}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Min APY (%)</label>
            <Input value={minApy} onChange={(e) => setMinApy(e.target.value)} type="number" min="0" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">Min TVL (USD)</label>
            <Input value={minTvl} onChange={(e) => setMinTvl(e.target.value)} type="number" min="0" />
          </div>
        </div>
      </GlassCard>

      {analyzerQuery.isLoading && (
        <div className="flex items-center justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-emerald-400" /></div>
      )}

      {!analyzerQuery.isLoading && analyzerQuery.error && (
        <GlassCard className="border-red-500/30 text-red-300">
          {analyzerQuery.error instanceof Error ? analyzerQuery.error.message : "Failed to load DeFi intelligence."}
        </GlassCard>
      )}

      {!analyzerQuery.isLoading && !analyzerQuery.error && data && (
        <>
          <div className="mb-6 grid gap-4 md:grid-cols-4">
            <MetricCard label="Deployable Opportunities" value={String(data.count.opportunities ?? data.top_opportunities.length)} hint={`${data.count.protocols} protocol surfaces`} />
            <MetricCard label="Average Opportunity" value={`${(data.summary.avg_opportunity_score ?? 0).toFixed(0)}/100`} hint={`${(data.summary.avg_safety_score ?? 0).toFixed(0)}/100 avg safety`} />
            <MetricCard label="Average Confidence" value={`${(data.summary.avg_confidence_score ?? 0).toFixed(0)}/100`} hint={`${data.summary.stressed_lending_market_count} stressed lending markets`} />
            <MetricCard label="Pools TVL" value={formatCompact(data.summary.total_pool_tvl)} hint={`${data.summary.high_risk_pool_count} high-risk pools`} />
          </div>

          {data.ai_market_brief && (
            <GlassCard className="mb-6 border-emerald-500/20 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.16),transparent_35%),rgba(10,15,24,0.88)]">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-emerald-300">
                  <Brain className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-medium text-emerald-300">AI Market Brief</div>
                    <Badge variant={data.ai_market_brief.available ? "safe" : "outline"}>
                      {data.ai_market_brief.market_regime}
                    </Badge>
                  </div>
                  <h2 className="mt-2 text-xl font-semibold">{data.ai_market_brief.headline}</h2>
                  <p className="mt-2 text-sm text-slate-300">{data.ai_market_brief.summary}</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Best Area</div>
                      <div className="mt-2 text-sm font-medium">{data.ai_market_brief.best_area}</div>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Avoid Zone</div>
                      <div className="mt-2 text-sm font-medium">{data.ai_market_brief.avoid_zone}</div>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {data.ai_market_brief.monitor_triggers.map((trigger) => (
                      <span key={trigger} className="rounded-full border border-white/10 bg-white/5 px-2 py-1">{trigger}</span>
                    ))}
                  </div>
                </div>
              </div>
            </GlassCard>
          )}

          <div className="mb-8 grid gap-4 lg:grid-cols-3">
            {[data.highlights.best_conservative, data.highlights.best_balanced, data.highlights.best_aggressive].map((item, index) => {
              const label = index === 0 ? "Conservative Capital" : index === 1 ? "Balanced Risk-Adjusted" : "Aggressive Rotation";
              const icon = index === 0 ? ShieldCheck : index === 1 ? Sparkles : TrendingUp;
              const Icon = icon;
              return (
                <GlassCard key={label} className="border-white/10 bg-white/[0.03]">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Icon className="h-4 w-4 text-emerald-400" /> {label}
                  </div>
                  {item ? (
                    <>
                      <div className="mt-3 text-lg font-semibold">{item.title}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{item.summary.headline}</div>
                      <div className="mt-4 flex gap-2 text-sm">
                        <Badge variant={scoreVariant(item.summary.opportunity_score)}>Score {item.summary.opportunity_score}</Badge>
                        <Badge variant="outline">{item.summary.strategy_fit}</Badge>
                      </div>
                      <Button asChild variant="ghost" className="mt-4 px-0 hover:bg-transparent">
                        <Link href={`/defi/opportunity/${item.id}`}>
                          Open setup <ArrowRight className="ml-2 h-4 w-4" />
                        </Link>
                      </Button>
                    </>
                  ) : (
                    <div className="mt-3 text-sm text-muted-foreground">No setup matched the current filters.</div>
                  )}
                </GlassCard>
              );
            })}
          </div>

          <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold">Top Opportunities</h2>
                  <p className="text-sm text-muted-foreground">Ranked by safety, yield quality, exit quality, and confidence.</p>
                </div>
                <Badge variant="outline">{data.top_opportunities.length} ranked</Badge>
              </div>
              {data.top_opportunities.map((item) => (
                <OpportunityCard key={item.id} item={item} />
              ))}
              {!data.top_opportunities.length && (
                <GlassCard className="text-sm text-muted-foreground">No opportunities matched the current filters.</GlassCard>
              )}
            </div>

            <div className="space-y-6">
              <GlassCard className="border-white/10 bg-white/[0.03]">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Radar className="h-4 w-4 text-emerald-400" /> Protocol Spotlights
                </div>
                <div className="mt-4 space-y-3">
                  {data.protocol_spotlights.slice(0, 5).map((protocol) => (
                    <ProtocolSpotlight key={protocol.slug} protocol={protocol} />
                  ))}
                  {!data.protocol_spotlights.length && (
                    <div className="text-sm text-muted-foreground">No protocol spotlights for the active query yet.</div>
                  )}
                </div>
              </GlassCard>

              <GlassCard className="border-white/10 bg-white/[0.03]">
                <div className="flex items-center gap-2 text-sm font-medium">
                  <Sparkles className="h-4 w-4 text-emerald-400" /> Methodology
                </div>
                <div className="mt-4 space-y-3 text-sm text-muted-foreground">
                  <p>{data.methodology?.opportunity_score}</p>
                  <p>{data.methodology?.safety_score}</p>
                  <p>{data.methodology?.confidence_score}</p>
                </div>
              </GlassCard>
            </div>
          </div>

          <div className="mt-10 grid gap-6 xl:grid-cols-3">
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium"><Waves className="h-4 w-4 text-emerald-400" /> Pools</div>
              {data.top_pools.slice(0, 4).map((pool) => <CompactPoolCard key={pool.pool} pool={pool} />)}
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium"><TrendingUp className="h-4 w-4 text-emerald-400" /> Farms</div>
              {data.top_yields.slice(0, 4).map((pool) => <CompactPoolCard key={pool.pool} pool={pool} />)}
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Lending</div>
              {data.top_lending_markets.slice(0, 4).map((market) => <CompactLendingCard key={`${market.pool_id}-${market.symbol}`} market={market} />)}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
