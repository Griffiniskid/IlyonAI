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
  ShieldCheck,
  Siren,
  Sparkles,
  Wrench,
} from "lucide-react";

import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, formatCompact } from "@/lib/utils";
import * as api from "@/lib/api";

function scoreVariant(score: number) {
  if (score >= 80) return "safe" as const;
  if (score >= 60) return "caution" as const;
  if (score >= 40) return "risky" as const;
  return "danger" as const;
}

function SummaryCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <GlassCard className="border-white/10 bg-white/[0.03] py-5">
      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-3xl font-semibold">{value}</div>
      <div className="mt-1 text-sm text-muted-foreground">{hint}</div>
    </GlassCard>
  );
}

export default function DefiProtocolPage() {
  const params = useParams();
  const rawSlug = params?.slug;
  const slug = typeof rawSlug === "string" ? rawSlug : rawSlug?.[0] ?? "";

  const query = useQuery({
    queryKey: ["defi-protocol-profile", slug],
    queryFn: () => api.getDefiProtocolProfile(slug, { includeAi: true, rankingProfile: "balanced" }),
    enabled: Boolean(slug),
    staleTime: 60_000,
  });

  const protocol = query.data;

  if (!slug) return null;

  if (query.isLoading) {
    return <div className="container mx-auto px-4 py-24 flex justify-center"><Loader2 className="h-8 w-8 animate-spin text-emerald-400" /></div>;
  }

  if (query.error || !protocol) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-12">
        <GlassCard className="border-red-500/30 text-red-300">Failed to load this protocol profile.</GlassCard>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <Button asChild variant="ghost" className="mb-6 px-0 hover:bg-transparent">
        <Link href="/defi"><ArrowLeft className="mr-2 h-4 w-4" /> Back to DeFi</Link>
      </Button>

      <div className="mb-8 overflow-hidden rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.16),transparent_35%),rgba(8,12,20,0.92)] p-6 md:p-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{protocol.category || "DeFi"}</Badge>
              {protocol.ranking_profile && <Badge variant="secondary" className="bg-white/5 border-white/10 text-muted-foreground">{protocol.ranking_profile} ranking</Badge>}
              {protocol.chains.slice(0, 4).map((chain) => (
                <Badge key={chain} variant="secondary" className="bg-white/5 border-white/10 text-muted-foreground">{chain}</Badge>
              ))}
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight md:text-4xl">{protocol.display_name}</h1>
            <p className="mt-3 text-sm text-slate-300 md:text-base">
              Safety {protocol.summary.safety_score}/100 · Opportunity {protocol.summary.opportunity_score}/100 · Confidence {protocol.summary.confidence_score}/100
            </p>
          </div>
          {protocol.url && (
            <Button asChild variant="outline">
              <a href={protocol.url} target="_blank" rel="noopener noreferrer">
                Protocol site <ExternalLink className="ml-2 h-4 w-4" />
              </a>
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4 mb-8">
        <SummaryCard label="TVL" value={formatCompact(protocol.summary.tvl_usd)} hint={`${protocol.summary.deployment_count} deployments`} />
        <SummaryCard label="Safety" value={String(protocol.summary.safety_score)} hint={protocol.summary.risk_level.toLowerCase()} />
        <SummaryCard label="Opportunity" value={String(protocol.summary.opportunity_score)} hint={`${protocol.top_opportunities.length} top setups`} />
        <SummaryCard label="Confidence" value={String(protocol.summary.confidence_score)} hint={`${protocol.summary.audit_count} audits · ${protocol.summary.incident_count} incidents`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="space-y-6">
          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Dimension Scores</div>
            <div className="mt-4 space-y-3">
              {protocol.dimensions.map((dimension) => (
                <div key={dimension.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{dimension.label}</div>
                    <Badge variant={scoreVariant(dimension.score)}>{dimension.score}</Badge>
                  </div>
                  <div className="mt-3 h-2 rounded-full bg-white/10 overflow-hidden">
                    <div className={cn("h-full rounded-full", dimension.score >= 80 ? "bg-emerald-500" : dimension.score >= 60 ? "bg-yellow-500" : dimension.score >= 40 ? "bg-orange-500" : "bg-red-500")} style={{ width: `${dimension.score}%` }} />
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{dimension.summary}</p>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><Sparkles className="h-4 w-4 text-emerald-400" /> Top Opportunities</div>
            <div className="mt-4 space-y-3">
              {protocol.top_opportunities.map((item) => (
                <GlassCard key={item.id} className="border-white/10 bg-black/20">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold">{item.title}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{item.summary.headline}</div>
                    </div>
                    <Badge variant={scoreVariant(item.summary.opportunity_score)}>{item.summary.opportunity_score}</Badge>
                  </div>
                  <Button asChild variant="ghost" className="mt-3 px-0 hover:bg-transparent">
                    <Link href={`/defi/opportunity/${item.id}`}>
                      Open setup <ArrowRight className="ml-2 h-4 w-4" />
                    </Link>
                  </Button>
                </GlassCard>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><Wrench className="h-4 w-4 text-emerald-400" /> Evidence</div>
            <div className="mt-4 space-y-3">
              {protocol.evidence.map((item) => (
                <div key={item.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{item.title}</div>
                    <Badge variant={item.severity === "high" ? "danger" : item.severity === "medium" ? "caution" : "safe"}>{item.severity}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{item.summary}</p>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>

        <div className="space-y-6">
          {protocol.ai_analysis && (
            <GlassCard className="border-emerald-500/20 bg-[radial-gradient(circle_at_top_right,rgba(16,185,129,0.15),transparent_35%),rgba(8,12,20,0.88)]">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-emerald-300">
                  <Brain className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-medium text-emerald-300">AI Protocol Analysis</div>
                    <Badge variant={protocol.ai_analysis.available ? "safe" : "outline"}>{protocol.ai_analysis.available ? "AI-backed" : "fallback"}</Badge>
                  </div>
                  <h2 className="mt-2 text-xl font-semibold">{protocol.ai_analysis.headline}</h2>
                  <p className="mt-2 text-sm text-slate-300">{protocol.ai_analysis.summary}</p>
                  <div className="mt-4 text-xs uppercase tracking-[0.18em] text-muted-foreground">Main risks</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {protocol.ai_analysis.main_risks.map((risk) => (
                      <span key={risk} className="rounded-full border border-white/10 bg-white/5 px-2 py-1">{risk}</span>
                    ))}
                  </div>
                </div>
              </div>
            </GlassCard>
          )}

          {protocol.confidence && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Coverage & Confidence</div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Confidence</div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="text-2xl font-semibold">{protocol.confidence.score}</div>
                    <Badge variant={protocol.confidence.partial_analysis ? "caution" : "safe"}>{protocol.confidence.label}</Badge>
                  </div>
                </div>
                <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Coverage Ratio</div>
                  <div className="mt-2 text-2xl font-semibold">{(protocol.confidence.coverage_ratio * 100).toFixed(0)}%</div>
                  <div className="mt-1 text-sm text-muted-foreground">{protocol.confidence.source_count} source surfaces</div>
                </div>
              </div>
            </GlassCard>
          )}

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="text-sm font-medium">Chain Breakdown</div>
            <div className="mt-4 space-y-3">
              {protocol.chain_breakdown.map((item) => (
                <div key={item.chain} className="rounded-2xl border border-white/10 bg-black/20 p-4 flex items-center justify-between gap-3">
                  <div className="font-medium">{item.chain}</div>
                  <div className="text-sm text-muted-foreground">{item.tvl_usd != null ? formatCompact(item.tvl_usd) : "Coverage only"}</div>
                </div>
              ))}
            </div>
          </GlassCard>

          {protocol.assets && protocol.assets.length > 0 && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Core Asset Exposure</div>
              <div className="mt-4 space-y-3">
                {protocol.assets.slice(0, 6).map((asset) => (
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

          {protocol.dependencies && protocol.dependencies.length > 0 && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Dependency Graph</div>
              <div className="mt-4 space-y-3">
                {protocol.dependencies.slice(0, 6).map((item) => (
                  <div key={item.key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="font-medium">{item.name}</div>
                        <div className="mt-1 text-sm text-muted-foreground capitalize">{item.dependency_type}</div>
                      </div>
                      <Badge variant={scoreVariant(100 - item.risk_score)}>Risk {item.risk_score}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">{item.notes}</p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          {protocol.governance && Object.keys(protocol.governance).length > 0 && (
            <GlassCard className="border-white/10 bg-white/[0.03]">
              <div className="text-sm font-medium">Governance & Admin Signals</div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {Object.entries(protocol.governance).map(([key, value]) => (
                  <div key={key} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{key.replace(/_/g, " ")}</div>
                    <div className="mt-2 text-sm font-medium">{String(value)}</div>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><Wrench className="h-4 w-4 text-emerald-400" /> Audits</div>
            <div className="mt-4 space-y-3">
              {protocol.audits.length ? protocol.audits.map((audit) => (
                <div key={audit.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{audit.auditor}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{audit.protocol} · {audit.date}</div>
                    </div>
                    <Badge variant="safe">{audit.verdict}</Badge>
                  </div>
                </div>
              )) : <div className="text-sm text-muted-foreground">No audits in the current internal dataset.</div>}
            </div>
          </GlassCard>

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="flex items-center gap-2 text-sm font-medium"><Siren className="h-4 w-4 text-emerald-400" /> Incident History</div>
            <div className="mt-4 space-y-3">
              {protocol.incidents.length ? protocol.incidents.map((incident) => (
                <div key={incident.id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{incident.name}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{incident.date} · {formatCompact(incident.amount_usd)}</div>
                    </div>
                    <Badge variant={incident.severity === "CRITICAL" ? "danger" : incident.severity === "HIGH" ? "risky" : "caution"}>{incident.severity}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{incident.description}</p>
                </div>
              )) : <div className="text-sm text-muted-foreground">No incidents matched this protocol in the current intelligence layer.</div>}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
