"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useAnalyzePool } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Brain,
  Check,
  Copy,
  Database,
  ExternalLink,
  Loader2,
  RefreshCw,
  Shield,
  TrendingUp,
} from "lucide-react";
import { cn, copyToClipboard, formatPercentage, formatUSD, truncateAddress } from "@/lib/utils";

function scoreVariant(score: number): "safe" | "caution" | "risky" | "danger" {
  if (score >= 80) return "safe";
  if (score >= 65) return "caution";
  if (score >= 45) return "risky";
  return "danger";
}

function scoreGrade(score: number): string {
  if (score >= 85) return "A";
  if (score >= 72) return "B";
  if (score >= 60) return "C";
  if (score >= 45) return "D";
  return "F";
}

function ScoreRing({ score, label }: { score: number; label: string }) {
  const circumference = 2 * Math.PI * 72;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 80 ? "#10b981" : score >= 65 ? "#eab308" : score >= 45 ? "#f97316" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative h-40 w-40">
        <svg className="-rotate-90" width="160" height="160">
          <circle cx="80" cy="80" r="72" fill="none" stroke="hsl(var(--muted))" strokeWidth="10" />
          <circle
            cx="80"
            cy="80"
            r="72"
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ filter: `drop-shadow(0 0 10px ${color}55)` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-4xl font-bold font-mono">{score}</div>
          <div className="text-sm text-muted-foreground">{scoreGrade(score)}</div>
        </div>
      </div>
      <Badge variant={scoreVariant(score)}>{label}</Badge>
    </div>
  );
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <GlassCard className="space-y-2">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold font-mono">{value}</div>
      {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
    </GlassCard>
  );
}

function DimensionRow({ label, score, summary }: { label: string; score: number; summary: string }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium">{label}</div>
        <Badge variant={scoreVariant(score)}>{score}</Badge>
      </div>
      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full",
            score >= 80 ? "bg-emerald-500" : score >= 65 ? "bg-yellow-500" : score >= 45 ? "bg-orange-500" : "bg-red-500"
          )}
          style={{ width: `${Math.max(6, score)}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">{summary}</p>
    </div>
  );
}

export default function PoolAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawId = params?.id;
  const poolId = useMemo(() => {
    const value = typeof rawId === "string" ? rawId : rawId?.[0] ?? "";
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }, [rawId]);
  const pairAddress = searchParams?.get("pair") ?? "";
  const searchChain = searchParams?.get("chain") ?? "";
  const source = searchParams?.get("source") ?? "";

  const [copied, setCopied] = useState(false);
  const [analysisStage, setAnalysisStage] = useState(0);
  const {
    mutate: analyzePool,
    data: analysis,
    isPending,
    error,
  } = useAnalyzePool();

  useEffect(() => {
    if (poolId) {
      analyzePool({
        poolId,
        includeAi: true,
        rankingProfile: "balanced",
        pairAddress: pairAddress || undefined,
        chain: searchChain || undefined,
        source: source || undefined,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- analyzePool ref changes on re-render, causing duplicate calls
  }, [poolId, pairAddress, searchChain, source]);

  useEffect(() => {
    if (!isPending) return;
    const stages = [1, 2, 3, 4];
    let index = 0;
    const timer = setInterval(() => {
      setAnalysisStage(stages[index]);
      index += 1;
      if (index >= stages.length) clearInterval(timer);
    }, 1600);
    return () => clearInterval(timer);
  }, [isPending]);

  const handleCopy = async () => {
    await copyToClipboard(pairAddress || poolId);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const historyData = useMemo(() => {
    const points = analysis?.history?.points;
    if (!Array.isArray(points)) return [];
    return points
      .map((point: any) => {
        const rawTs = Number(point.timestamp ?? point.ts ?? 0);
        const timestamp = rawTs > 10_000_000_000 ? rawTs : rawTs * 1000;
        return {
          label: timestamp ? new Date(timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "-",
          apy: Number(point.apy ?? 0),
          tvl: Number(point.tvlUsd ?? point.tvl_usd ?? 0),
        };
      })
      .filter((point) => Number.isFinite(point.apy) || Number.isFinite(point.tvl));
  }, [analysis]);

  if (!poolId) return null;

  if (isPending && !analysis) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-2xl mx-auto">
          <GlassCard className="text-center py-12">
            <Loader2 className="h-12 w-12 text-emerald-500 animate-spin mx-auto mb-6" />
            <h2 className="text-xl font-semibold mb-4">Analyzing Pool...</h2>
            <p className="text-muted-foreground mb-6 font-mono text-sm">{truncateAddress(poolId, 8)}</p>
            <div className="max-w-md mx-auto space-y-3 text-left">
              {[
                { stage: 1, label: "Fetching live pool data..." },
                { stage: 2, label: "Measuring sustainability and exit quality..." },
                { stage: 3, label: "Scoring safety and historical stress..." },
                { stage: 4, label: "Generating AI summary and report..." },
              ].map((item) => (
                <div
                  key={item.stage}
                  className={cn(
                    "flex items-center gap-3 text-sm transition-opacity",
                    analysisStage >= item.stage ? "opacity-100" : "opacity-30"
                  )}
                >
                  {analysisStage > item.stage ? (
                    <Check className="h-4 w-4 text-emerald-400" />
                  ) : analysisStage === item.stage ? (
                    <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
                  ) : (
                    <div className="h-4 w-4 rounded-full border border-muted" />
                  )}
                  {item.label}
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>
    );
  }

  if (error && !analysis) {
    return (
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-2xl mx-auto">
          <GlassCard className="text-center py-12">
            <AlertTriangle className="h-12 w-12 text-red-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">Pool Analysis Failed</h2>
            <p className="text-muted-foreground mb-6">{(error as Error).message || "Failed to analyze pool"}</p>
            <div className="flex gap-4 justify-center">
              <Button variant="outline" onClick={() => router.back()}>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Go Back
              </Button>
              <Button onClick={() => analyzePool({ poolId, includeAi: true, rankingProfile: "balanced" })}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Try Again
              </Button>
            </div>
          </GlassCard>
        </div>
      </div>
    );
  }

  if (!analysis) return null;

  const overallScore = analysis.summary.overall_score ?? analysis.summary.opportunity_score;
  const qualityScore = analysis.summary.quality_score ?? overallScore;
  const riskBurden = analysis.summary.risk_burden_score ?? Math.max(0, 100 - analysis.summary.safety_score);
  const yieldDurability = analysis.summary.yield_durability_score ?? analysis.summary.yield_quality_score;
  const exitLiquidity = analysis.summary.exit_liquidity_score ?? analysis.summary.exit_quality_score;
  const aprEfficiency = analysis.summary.apr_efficiency_score ?? analysis.summary.return_potential_score ?? overallScore;
  const effectiveApr = analysis.summary.effective_apr ?? analysis.apy;
  const requiredApr = analysis.summary.required_apr ?? analysis.apy;
  const detailedDimensions = analysis.dimensions.filter(
    (dimension) => !["overall_score", "quality_score", "yield_durability", "exit_liquidity", "apr_efficiency"].includes(dimension.key)
  );

  return (
    <div className="container mx-auto px-4 py-8 space-y-8">
      <Button variant="ghost" size="sm" onClick={() => router.back()}>
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back
      </Button>

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{analysis.kind.toUpperCase()}</Badge>
            {analysis.product_type ? <Badge variant="outline">{analysis.product_type.replace(/_/g, " ")}</Badge> : null}
            <Badge variant="outline">{analysis.chain.toUpperCase()}</Badge>
            <Badge variant={scoreVariant(analysis.summary.safety_score)}>{analysis.summary.risk_level} risk</Badge>
            <Badge variant="outline">{analysis.summary.strategy_fit}</Badge>
          </div>

          <div>
            <h1 className="text-3xl md:text-4xl font-bold">{analysis.title}</h1>
            <p className="text-lg text-muted-foreground mt-2">{analysis.subtitle}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            {pairAddress ? (
              <span className="inline-flex items-center gap-2">
                <Database className="h-4 w-4 text-emerald-400" />
                Pool Address {truncateAddress(pairAddress, 10)}
              </span>
            ) : null}
            {(!pairAddress || pairAddress.toLowerCase() !== poolId.toLowerCase()) ? (
              <span className="inline-flex items-center gap-2">
                <Database className="h-4 w-4 text-emerald-400" />
                Internal ID {truncateAddress(poolId, 10)}
              </span>
            ) : null}
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCopy}>
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
            {analysis.raw?.url ? (
              <a
                href={String(analysis.raw.url)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 hover:text-emerald-400 transition-colors"
              >
                Source
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            ) : null}
          </div>

          <p className="max-w-3xl text-muted-foreground">{analysis.summary.thesis}</p>
        </div>

        <GlassCard className="min-w-[280px] flex items-center justify-center">
          <ScoreRing score={overallScore} label={analysis.summary.headline} />
        </GlassCard>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <MetricCard
          label={source === "dexpair" ? "Estimated APR" : "Displayed APR"}
          value={formatPercentage(analysis.apy)}
          hint={source === "dexpair" ? "Estimated from 24h volume, liquidity, and the on-chain fee tier" : "Current headline annualized yield"}
        />
        <MetricCard label="Effective APR" value={formatPercentage(effectiveApr)} hint="Yield after durability, liquidity, incentive, and evidence haircuts" />
        <MetricCard label="Required APR" value={formatPercentage(requiredApr)} hint="Minimum hurdle APR for this pool's risk burden" />
        <MetricCard label="APR Efficiency" value={`${aprEfficiency}/100`} hint="How attractive the effective APR is relative to the required hurdle" />
        <MetricCard label="Pool Quality" value={`${qualityScore}/100`} hint="Structural pool quality independent from pure deployment attractiveness" />
        <MetricCard label="Risk Burden" value={`${riskBurden}/100`} hint="Weighted protocol, asset, structure, exit, governance, and history risk load" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_1fr] gap-6">
        <GlassCard className="space-y-6">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-emerald-400" />
            <h2 className="text-xl font-semibold">Score Breakdown</h2>
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <DimensionRow label="Overall Score" score={overallScore} summary="Primary deployment score blending APR efficiency, pool quality, safety, exit liquidity, durability, and confidence." />
            <DimensionRow label="Pool Quality" score={qualityScore} summary="Structural pool quality after combining safety, durability, exit liquidity, and evidence confidence." />
            <DimensionRow label="Safety" score={analysis.summary.safety_score} summary="Protocol quality, asset quality, structure risk, governance posture, and historical stress behavior." />
            <DimensionRow label="APR Efficiency" score={aprEfficiency} summary="Effective APR compared with the hurdle APR required for this pool's risk burden." />
            <DimensionRow label="Yield Durability" score={yieldDurability} summary="Fee-backed yield share, persistence, reward quality, emissions dilution, and capital efficiency." />
            <DimensionRow label="Exit Liquidity" score={exitLiquidity} summary="Depth, estimated slippage, fragmentation, and withdrawal constraints under stress." />
          </div>
          <div className="space-y-5 border-t border-white/10 pt-5">
            {detailedDimensions.map((dimension) => (
              <DimensionRow
                key={dimension.key}
                label={dimension.label}
                score={dimension.score}
                summary={dimension.summary}
              />
            ))}
          </div>
        </GlassCard>

        <div className="space-y-6">
          <GlassCard className="space-y-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-emerald-400" />
              <h2 className="text-xl font-semibold">Evidence</h2>
            </div>
            <div className="space-y-3">
              {analysis.evidence.map((item) => (
                <div key={item.key} className="rounded-xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="font-medium">{item.title}</div>
                    <Badge variant={item.severity === "high" ? "danger" : item.severity === "medium" ? "caution" : "safe"}>{item.severity}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{item.summary}</p>
                </div>
              ))}
            </div>
          </GlassCard>

          <GlassCard className="space-y-4">
            <div className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-emerald-400" />
              <h2 className="text-xl font-semibold">Stress Scenarios</h2>
            </div>
            <div className="space-y-3">
              {analysis.scenarios.map((item) => (
                <div key={item.key} className="rounded-xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="font-medium">{item.title}</div>
                    <Badge variant={item.severity === "high" ? "danger" : item.severity === "medium" ? "caution" : "safe"}>{item.severity}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{item.impact}</p>
                  <p className="mt-2 text-xs text-muted-foreground">Trigger: {item.trigger}</p>
                </div>
              ))}
            </div>
          </GlassCard>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_1fr] gap-6">
        <GlassCard className="space-y-4">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-emerald-400" />
            <h2 className="text-xl font-semibold">History</h2>
          </div>
          {historyData.length ? (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <div>
                <div className="mb-3 text-sm text-muted-foreground">APY trend</div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={historyData}>
                      <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 12 }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} tickLine={false} axisLine={false} />
                      <Tooltip
                        contentStyle={{
                          background: "rgba(15, 23, 42, 0.95)",
                          border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: 16,
                        }}
                      />
                      <Area type="monotone" dataKey="apy" stroke="#10b981" fill="rgba(16,185,129,0.18)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div>
                <div className="mb-3 text-sm text-muted-foreground">TVL trend</div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={historyData}>
                      <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 12 }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fill: "#94a3b8", fontSize: 12 }} tickLine={false} axisLine={false} tickFormatter={(value) => formatUSD(Number(value)).replace(/\.00$/, "")} />
                      <Tooltip
                        formatter={(value: number) => formatUSD(Number(value))}
                        contentStyle={{
                          background: "rgba(15, 23, 42, 0.95)",
                          border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: 16,
                        }}
                      />
                      <Area type="monotone" dataKey="tvl" stroke="#38bdf8" fill="rgba(56,189,248,0.18)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No historical pool chart was available for this opportunity.</p>
          )}
        </GlassCard>

        <div className="space-y-6">
          <GlassCard className="space-y-4">
            <div className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-emerald-400" />
              <h2 className="text-xl font-semibold">AI Summary</h2>
            </div>
            {analysis.ai_analysis?.available ? (
              <div className="space-y-4">
                <div>
                  <div className="font-medium mb-1">{analysis.ai_analysis.headline}</div>
                  <p className="text-sm text-muted-foreground">{analysis.ai_analysis.summary}</p>
                </div>
                {analysis.ai_analysis.best_for ? (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">Best For</div>
                    <p className="text-sm">{analysis.ai_analysis.best_for}</p>
                  </div>
                ) : null}
                {analysis.ai_analysis.main_risks?.length ? (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">Main Risks</div>
                    <div className="space-y-2">
                      {analysis.ai_analysis.main_risks.map((risk) => (
                        <div key={risk} className="text-sm text-muted-foreground">- {risk}</div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">AI commentary was not available for this pool report.</p>
            )}
          </GlassCard>

          <GlassCard className="space-y-4">
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-emerald-400" />
              <h2 className="text-xl font-semibold">Dependencies and Caps</h2>
            </div>
            <div className="space-y-3">
              {(analysis.score_caps || []).map((cap) => (
                <div key={`${cap.dimension}-${cap.reason}`} className="rounded-xl border border-orange-500/20 bg-orange-500/5 p-4">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="font-medium">{cap.dimension}</div>
                    <Badge variant="risky">cap {cap.cap}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{cap.reason}</p>
                </div>
              ))}
              {(analysis.dependencies || []).slice(0, 6).map((dependency) => (
                <div key={dependency.key} className="rounded-xl border border-white/10 bg-black/20 p-4">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="font-medium">{dependency.name}</div>
                    <Badge variant={scoreVariant(100 - dependency.risk_score)}>{dependency.risk_score} risk</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{dependency.notes}</p>
                </div>
              ))}
              {!analysis.score_caps?.length && !analysis.dependencies?.length ? (
                <p className="text-sm text-muted-foreground">No special caps or dependency notes were attached to this report.</p>
              ) : null}
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
