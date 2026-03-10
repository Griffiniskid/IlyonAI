"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Brain,
  ExternalLink,
  Loader2,
  Radar,
  ShieldCheck,
  TrendingUp,
  TriangleAlert,
} from "lucide-react";

import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, formatCompact } from "@/lib/utils";
import * as api from "@/lib/api";
import type { DefiOpportunityResponse } from "@/types";

function scoreVariant(score: number) {
  if (score >= 80) return "safe" as const;
  if (score >= 60) return "caution" as const;
  if (score >= 40) return "risky" as const;
  return "danger" as const;
}

function ScoreCard({ label, score, hint }: { label: string; score: number; hint: string }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03] py-5">
      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="mt-2 flex items-center gap-3">
        <div className="text-3xl font-semibold">{score}</div>
        <Badge variant={scoreVariant(score)}>{hint}</Badge>
      </div>
    </GlassCard>
  );
}

function DimensionRow({ label, score, summary }: { label: string; score: number; summary: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="font-medium">{label}</div>
        <Badge variant={scoreVariant(score)}>{score}</Badge>
      </div>
      <div className="mt-3 h-2 rounded-full bg-white/10 overflow-hidden">
        <div className={cn("h-full rounded-full", score >= 80 ? "bg-emerald-500" : score >= 60 ? "bg-yellow-500" : score >= 40 ? "bg-orange-500" : "bg-red-500")} style={{ width: `${score}%` }} />
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{summary}</p>
    </div>
  );
}

function RelatedCard({ item }: { item: DefiOpportunityResponse }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{item.title}</div>
          <div className="mt-1 text-sm text-muted-foreground">{item.subtitle}</div>
        </div>
        <Badge variant={scoreVariant(item.summary.opportunity_score)}>{item.summary.opportunity_score}</Badge>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{item.summary.headline}</p>
      <Button asChild variant="ghost" className="mt-3 px-0 hover:bg-transparent">
        <Link href={`/defi/opportunity/${item.id}`}>
          Open setup <ArrowRight className="ml-2 h-4 w-4" />
        </Link>
      </Button>
    </GlassCard>
  );
}

export default function DefiOpportunityPage() {
  const params = useParams();
  const rawId = params?.id;
  const opportunityId = typeof rawId === "string" ? rawId : rawId?.[0] ?? "";

  const query = useQuery({
    queryKey: ["defi-opportunity", opportunityId],
    queryFn: () => api.getDefiOpportunity(opportunityId, { includeAi: true, rankingProfile: "balanced" }),
    enabled: Boolean(opportunityId),
    staleTime: 60_000,
  });

  const opportunity = query.data;

  if (!opportunityId) return null;

  if (query.isLoading) {
    return <div className="container mx-auto px-4 py-24 flex justify-center"><Loader2 className="h-8 w-8 animate-spin text-emerald-400" /></div>;
  }

  if (query.error || !opportunity) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-12">
        <GlassCard className="border-red-500/30 text-red-300">
          Failed to load this DeFi opportunity.
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <Button asChild variant="ghost" className="mb-6 px-0 hover:bg-transparent">
        <Link href="/defi"><ArrowLeft className="mr-2 h-4 w-4" /> Back to DeFi</Link>
      </Button>

      <div className="mb-8 overflow-hidden rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.18),transparent_38%),rgba(9,12,21,0.92)] p-6 md:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{opportunity.kind}</Badge>
              <Badge variant="outline" className="capitalize">{opportunity.chain}</Badge>
              {opportunity.ranking_profile && (
                <Badge variant="secondary" className="bg-white/5 border-white/10 text-muted-foreground">
                  {opportunity.ranking_profile} ranking
                </Badge>
              )}
              {opportunity.tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="bg-white/5 border-white/10 text-muted-foreground">{tag}</Badge>
              ))}
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight md:text-4xl">{opportunity.title}</h1>
            <p className="mt-2 text-sm text-slate-300 md:text-base">{opportunity.subtitle}</p>
            <p className="mt-4 max-w-2xl text-sm text-slate-300">{opportunity.summary.thesis}</p>
          </div>
          <div className="flex flex-col gap-3">
            <Badge variant={scoreVariant(opportunity.summary.opportunity_score)} className="text-sm justify-center">
              Opportunity {opportunity.summary.opportunity_score}
            </Badge>
            <Button asChild variant="outline">
              <Link href={`/defi/protocol/${opportunity.protocol_slug}`}>
                Protocol view <ExternalLink className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4 mb-8">
        <ScoreCard label="Opportunity" score={opportunity.summary.opportunity_score} hint={opportunity.summary.strategy_fit} />
        <ScoreCard label="Safety" score={opportunity.summary.safety_score} hint={opportunity.summary.risk_level.toLowerCase()} />
        <ScoreCard label="Yield Quality" score={opportunity.summary.yield_quality_score} hint={`${opportunity.apy.toFixed(2)}% APY`} />
        <ScoreCard label="Confidence" score={opportunity.summary.confidence_score} hint={formatCompact(opportunity.tvl_usd)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><Radar className="h-4 w-4 text-emerald-400" /> Score Breakdown</div>
            <div className="mt-4 space-y-3">
              {opportunity.dimensions.map((dimension) => (
                <DimensionRow key={dimension.key} label={dimension.label} score={dimension.score} summary={dimension.summary} />
              ))}
            </div>
          </GlassCard>

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Evidence</div>
            <div className="mt-4 space-y-3">
              {opportunity.evidence.map((evidence) => (
                <div key={evidence.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{evidence.title}</div>
                    <Badge variant={evidence.severity === "high" ? "danger" : evidence.severity === "medium" ? "caution" : "safe"}>{evidence.severity}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{evidence.summary}</p>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><TriangleAlert className="h-4 w-4 text-emerald-400" /> Stress Scenarios</div>
            <div className="mt-4 space-y-3">
              {opportunity.scenarios.map((scenario) => (
                <div key={scenario.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{scenario.title}</div>
                    <Badge variant={scenario.severity === "high" ? "danger" : "caution"}>{scenario.severity}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{scenario.impact}</p>
                  <div className="mt-3 text-xs uppercase tracking-[0.18em] text-muted-foreground">Trigger</div>
                  <p className="mt-1 text-sm text-foreground/90">{scenario.trigger}</p>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>

        <div className="space-y-6">
          {opportunity.ai_analysis && (
            <GlassCard className="border-emerald-500/20 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.15),transparent_35%),rgba(8,12,20,0.88)]">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-emerald-300">
                  <Brain className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-medium text-emerald-300">AI Opportunity Analysis</div>
                    <Badge variant={opportunity.ai_analysis.available ? "safe" : "outline"}>
                      {opportunity.ai_analysis.available ? "AI-backed" : "fallback"}
                    </Badge>
                  </div>
                  <h2 className="mt-2 text-xl font-semibold">{opportunity.ai_analysis.headline}</h2>
                  <p className="mt-2 text-sm text-slate-300">{opportunity.ai_analysis.summary}</p>
                  <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Why this yield exists</div>
                    <p className="mt-2 text-sm text-foreground/90">{opportunity.ai_analysis.why_it_exists}</p>
                  </div>
                  <div className="mt-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Main risks</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {opportunity.ai_analysis.main_risks.map((risk) => (
                      <span key={risk} className="rounded-full border border-white/10 bg-white/5 px-2 py-1">{risk}</span>
                    ))}
                  </div>
                  <div className="mt-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Monitor triggers</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {opportunity.ai_analysis.monitor_triggers.map((trigger) => (
                      <span key={trigger} className="rounded-full border border-white/10 bg-white/5 px-2 py-1">{trigger}</span>
                    ))}
                  </div>
                </div>
              </div>
            </GlassCard>
          )}

          {opportunity.confidence && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Coverage & Confidence</div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Confidence</div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="text-2xl font-semibold">{opportunity.confidence.score}</div>
                    <Badge variant={opportunity.confidence.partial_analysis ? "caution" : "safe"}>{opportunity.confidence.label}</Badge>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Coverage Ratio</div>
                  <div className="mt-2 text-2xl font-semibold">{(opportunity.confidence.coverage_ratio * 100).toFixed(0)}%</div>
                  <div className="mt-1 text-sm text-muted-foreground">{opportunity.confidence.source_count} source surfaces</div>
                </div>
              </div>
              {opportunity.confidence.missing_critical_fields.length > 0 && (
                <div className="mt-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Missing Critical Fields</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {opportunity.confidence.missing_critical_fields.map((field) => (
                      <span key={field} className="rounded-full border border-white/10 bg-white/5 px-2 py-1">{field}</span>
                    ))}
                  </div>
                </div>
              )}
            </GlassCard>
          )}

          {opportunity.assets && opportunity.assets.length > 0 && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Underlying Assets</div>
              <div className="mt-4 space-y-3">
                {opportunity.assets.slice(0, 5).map((asset) => (
                  <div key={`${asset.role}-${asset.symbol}`} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium">{asset.symbol}</div>
                        <div className="mt-1 text-sm text-muted-foreground capitalize">{asset.role} on {asset.chain}</div>
                      </div>
                      <Badge variant={scoreVariant(asset.quality_score)}>{asset.quality_score}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">{asset.thesis}</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {opportunity.dependencies && opportunity.dependencies.length > 0 && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Dependency Graph</div>
              <div className="mt-4 space-y-3">
                {opportunity.dependencies.slice(0, 5).map((dependency) => (
                  <div key={dependency.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium">{dependency.name}</div>
                        <div className="mt-1 text-sm text-muted-foreground capitalize">{dependency.dependency_type}</div>
                      </div>
                      <Badge variant={scoreVariant(100 - dependency.risk_score)}>Risk {dependency.risk_score}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">{dependency.notes}</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {opportunity.history?.available && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="flex items-center gap-2 text-sm font-medium"><TrendingUp className="h-4 w-4 text-emerald-400" /> Trend Summary</div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">APY change</div>
                  <div className="mt-2 text-2xl font-semibold">{(opportunity.history.apy_change_pct ?? 0).toFixed(1)}%</div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">TVL change</div>
                  <div className="mt-2 text-2xl font-semibold">{(opportunity.history.tvl_change_pct ?? 0).toFixed(1)}%</div>
                </div>
              </div>
            </GlassCard>
          )}

          {opportunity.protocol_profile && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Protocol Snapshot</div>
              <div className="mt-3 text-xl font-semibold">{opportunity.protocol_profile.display_name}</div>
              <p className="mt-2 text-sm text-muted-foreground">
                Safety {opportunity.protocol_profile.summary.safety_score}/100 · Confidence {opportunity.protocol_profile.summary.confidence_score}/100 · {opportunity.protocol_profile.summary.audit_count} audits · {opportunity.protocol_profile.summary.incident_count} incidents
              </p>
              <Button asChild variant="outline" className="mt-4">
                <Link href={`/defi/protocol/${opportunity.protocol_profile.slug}`}>
                  Open protocol intelligence <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </GlassCard>
          )}

          {opportunity.rate_comparison && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Cross-Protocol Rate Check</div>
              <div className="mt-3 text-sm text-muted-foreground">
                {opportunity.rate_comparison.markets_found} markets found for {opportunity.rate_comparison.asset} on this chain surface.
              </div>
              <div className="mt-4 space-y-3">
                {opportunity.rate_comparison.best_supply.slice(0, 3).map((market) => (
                  <div key={`${market.pool_id}-${market.symbol}`} className="rounded-2xl border border-white/10 bg-black/20 p-4 flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">{market.protocol_display}</div>
                      <div className="text-sm text-muted-foreground">{market.symbol} on {market.chain}</div>
                    </div>
                    <Badge variant="safe">Supply {market.apy_supply.toFixed(2)}%</Badge>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {opportunity.related_opportunities && opportunity.related_opportunities.length > 0 && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Related Setups</div>
              <div className="mt-4 space-y-3">
                {opportunity.related_opportunities.slice(0, 4).map((item) => (
                  <RelatedCard key={item.id} item={item} />
                ))}
              </div>
            </GlassCard>
          )}

          {opportunity.safer_alternative && (
            <GlassCard className="border-emerald-500/20 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.10),transparent_35%),rgba(8,12,20,0.88)]">
              <div className="text-sm font-medium text-emerald-300">Safer Alternative</div>
              <div className="mt-3 text-lg font-semibold">{opportunity.safer_alternative.title}</div>
              <p className="mt-2 text-sm text-slate-300">{opportunity.safer_alternative.summary.headline}</p>
              <div className="mt-4 flex gap-2 text-sm">
                <Badge variant="safe">Safety {opportunity.safer_alternative.summary.safety_score}</Badge>
                <Badge variant="outline">Score {opportunity.safer_alternative.summary.opportunity_score}</Badge>
              </div>
              <Button asChild variant="ghost" className="mt-4 px-0 hover:bg-transparent">
                <Link href={`/defi/opportunity/${opportunity.safer_alternative.id}`}>
                  Open safer route <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </GlassCard>
          )}
        </div>
      </div>
    </div>
  );
}
