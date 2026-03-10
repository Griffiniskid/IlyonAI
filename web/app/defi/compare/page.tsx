"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Loader2, Scale, ShieldCheck } from "lucide-react";

import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import * as api from "@/lib/api";

const PROTOCOLS = ["aave-v3", "compound-v3", "morpho", "spark", "euler"];
const CHAINS = ["all", "ethereum", "base", "arbitrum", "optimism", "polygon", "avalanche", "solana"];

function scoreVariant(score: number) {
  if (score >= 80) return "safe" as const;
  if (score >= 60) return "caution" as const;
  if (score >= 40) return "risky" as const;
  return "danger" as const;
}

export default function DefiComparePage() {
  const [asset, setAsset] = useState("USDC");
  const [chain, setChain] = useState("base");
  const [selectedProtocols, setSelectedProtocols] = useState<string[]>(["aave-v3", "morpho", "compound-v3", "spark"]);

  const params = useMemo(() => ({
    asset,
    chain: chain !== "all" ? chain : undefined,
    protocols: selectedProtocols,
    mode: "supply" as const,
    rankingProfile: "balanced",
  }), [asset, chain, selectedProtocols]);

  const query = useQuery({
    queryKey: ["defi-compare", params],
    queryFn: () => api.getDefiComparison(params),
    staleTime: 60_000,
  });

  const data = query.data;

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <Button asChild variant="ghost" className="mb-6 px-0 hover:bg-transparent">
        <Link href="/defi"><ArrowLeft className="mr-2 h-4 w-4" /> Back to DeFi</Link>
      </Button>

      <div className="mb-8 overflow-hidden rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(16,185,129,0.16),transparent_35%),rgba(8,12,20,0.92)] p-6 md:p-8">
        <div className="max-w-4xl">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs uppercase tracking-[0.18em] text-emerald-300">
            <Scale className="h-3.5 w-3.5" /> DeFi Compare
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Compare the same capital path across protocols before you pick one.</h1>
          <p className="mt-3 max-w-3xl text-sm text-slate-300 md:text-base">This view keeps the asset and chain constant so protocol quality, reserve health, and exit depth become easier to compare.</p>
        </div>
      </div>

      <GlassCard className="mb-6 border-white/10 bg-white/[0.03]">
        <div className="grid gap-3 md:grid-cols-3">
          <Input value={asset} onChange={(e) => setAsset(e.target.value.toUpperCase())} placeholder="USDC" />
          <select value={chain} onChange={(e) => setChain(e.target.value)} className="h-10 rounded-md border border-input bg-background px-3 text-sm capitalize">
            {CHAINS.map((item) => <option key={item} value={item}>{item === "all" ? "All Chains" : item}</option>)}
          </select>
          <div className="flex flex-wrap gap-2">
            {PROTOCOLS.map((protocol) => {
              const active = selectedProtocols.includes(protocol);
              return (
                <button
                  key={protocol}
                  onClick={() => setSelectedProtocols((current) => active ? current.filter((item) => item !== protocol) : [...current, protocol])}
                  className={`rounded-full border px-3 py-2 text-xs capitalize ${active ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-300" : "border-white/10 bg-white/5 text-muted-foreground"}`}
                >
                  {protocol.replace(/-/g, " ")}
                </button>
              );
            })}
          </div>
        </div>
      </GlassCard>

      {query.isLoading && <div className="flex justify-center py-24"><Loader2 className="h-8 w-8 animate-spin text-emerald-400" /></div>}

      {!query.isLoading && query.error && (
        <GlassCard className="border-red-500/30 text-red-300">{query.error instanceof Error ? query.error.message : "Failed to compare DeFi opportunities."}</GlassCard>
      )}

      {!query.isLoading && data && (
        <>
          <div className="mb-6 grid gap-4 md:grid-cols-3">
            <GlassCard className="border-white/10 bg-white/[0.03] py-5">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Markets Compared</div>
              <div className="mt-2 text-2xl font-semibold">{data.summary.markets_compared}</div>
              <div className="mt-1 text-sm text-muted-foreground">{data.ranking_profile} ranking</div>
            </GlassCard>
            <GlassCard className="border-white/10 bg-white/[0.03] py-5">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Safest</div>
              <div className="mt-2 text-2xl font-semibold">{data.summary.safest?.protocol_name ?? "—"}</div>
              <div className="mt-1 text-sm text-muted-foreground">Safety {data.summary.safest?.summary.safety_score ?? 0}</div>
            </GlassCard>
            <GlassCard className="border-white/10 bg-white/[0.03] py-5">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Best Balanced</div>
              <div className="mt-2 text-2xl font-semibold">{data.summary.best_balanced?.protocol_name ?? "—"}</div>
              <div className="mt-1 text-sm text-muted-foreground">Score {data.summary.best_balanced?.summary.opportunity_score ?? 0}</div>
            </GlassCard>
          </div>

          <GlassCard className="border-white/10 bg-white/[0.03]">
            <div className="mb-4 flex items-center gap-2 text-sm font-medium"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Compare Matrix</div>
            <div className="space-y-3">
              {data.matrix.map((row) => (
                <div key={row.opportunity_id} className="rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="font-semibold">{row.protocol}</div>
                      <div className="mt-1 text-sm text-muted-foreground">{row.asset} on {row.chain}</div>
                    </div>
                    <div className="flex flex-wrap gap-2 text-sm">
                      <Badge variant={scoreVariant(row.opportunity_score)}>Score {row.opportunity_score}</Badge>
                      <Badge variant={scoreVariant(row.safety_score)}>Safety {row.safety_score}</Badge>
                      <Badge variant="outline">APY {row.apy.toFixed(2)}%</Badge>
                    </div>
                  </div>
                  <p className="mt-3 text-sm text-muted-foreground">{row.headline}</p>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="mt-8 grid gap-4 lg:grid-cols-2">
            {data.opportunities.map((item) => (
              <GlassCard key={item.id} className="border-white/10 bg-white/[0.03]">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">{item.title}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{item.summary.headline}</div>
                  </div>
                  <Badge variant={scoreVariant(item.summary.opportunity_score)}>{item.summary.opportunity_score}</Badge>
                </div>
                <div className="mt-4 flex flex-wrap gap-2 text-sm">
                  <Badge variant="outline">Safety {item.summary.safety_score}</Badge>
                  <Badge variant="outline">Yield {item.summary.yield_quality_score}</Badge>
                  <Badge variant="outline">Exit {item.summary.exit_quality_score}</Badge>
                </div>
                <Button asChild variant="ghost" className="mt-4 px-0 hover:bg-transparent">
                  <Link href={`/defi/opportunity/${item.id}`}>
                    Open analysis <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </GlassCard>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
