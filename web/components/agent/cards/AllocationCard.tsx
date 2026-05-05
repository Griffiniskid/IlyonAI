"use client";

import type { AllocationPayload } from "@/types/agent";
import { ArrowRight, BadgeCheck, Layers3, Network, Rocket, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

interface Props {
  payload: AllocationPayload;
}

function riskTone(risk: string) {
  if (risk === "low") return "border-emerald-400/30 bg-emerald-400/10 text-emerald-200";
  if (risk === "medium") return "border-amber-400/30 bg-amber-400/10 text-amber-200";
  return "border-red-400/30 bg-red-400/10 text-red-200";
}

function scoreTone(score: number) {
  if (score >= 85) return "from-emerald-300 to-cyan-300 text-emerald-950";
  if (score >= 70) return "from-lime-300 to-emerald-300 text-emerald-950";
  if (score >= 55) return "from-amber-300 to-orange-300 text-amber-950";
  return "from-red-300 to-orange-300 text-red-950";
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
      <div className="text-[10px] uppercase tracking-[0.18em] text-cyan-100/55">{label}</div>
      <div className="mt-1 text-lg font-black tracking-tight text-white">{value}</div>
      {sub && <div className="mt-0.5 text-[11px] text-slate-400">{sub}</div>}
    </div>
  );
}

function dispatchExecutePosition(position: AllocationPayload["positions"][0]) {
  if (typeof window === "undefined") return;
  const ref = `${position.protocol} ${position.asset}`.trim();
  const usd = String(position.usd || "").replace(/[^0-9.]/g, "");
  const amount = usd && Number(usd) > 0 ? Number(usd) : 100;
  const message = `execute_pool_position pool="${ref}" amount=${amount}`;
  window.dispatchEvent(new CustomEvent("ilyon:execute-pool", { detail: { pool: ref, message } }));
}

function PositionRow({ position }: { position: AllocationPayload["positions"][0] }) {
  return (
    <div className="group rounded-2xl border border-white/10 bg-slate-950/55 p-3 transition hover:border-cyan-300/30 hover:bg-slate-900/70">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br text-sm font-black shadow-lg ${scoreTone(position.sentinel)}`}>
            {position.rank}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-base font-black text-white">{position.protocol}</span>
              <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-100">{position.chain}</span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] ${riskTone(position.risk)}`}>{position.risk}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span>{position.asset}</span>
              <ArrowRight className="h-3 w-3 text-cyan-200/35" />
              <span>via {position.router}</span>
              <span>TVL {position.tvl}</span>
            </div>
          </div>
        </div>

        <div className="grid min-w-[260px] grid-cols-3 gap-2 text-right">
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Size</div>
            <div className="text-sm font-black text-white">{position.usd}</div>
            <div className="text-[11px] text-slate-400">{position.weight}% cap</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500">APY</div>
            <div className="text-sm font-black text-emerald-300">{position.apy}</div>
            <div className="text-[11px] text-slate-400">durable</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Sentinel</div>
            <div className="text-sm font-black text-cyan-200">{position.sentinel}/100</div>
            <div className="text-[11px] text-slate-400">{position.fit}</div>
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2">
        {[
          ["Safety", position.safety],
          ["Durability", position.durability],
          ["Exit", position.exit],
          ["Confidence", position.confidence],
        ].map(([label, value]) => (
          <div key={label}>
            <div className="mb-1 flex justify-between text-[10px] text-slate-400"><span>{label}</span><span>{value}</span></div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full rounded-full bg-gradient-to-r from-cyan-300 to-emerald-300" style={{ width: `${value}%` }} />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => dispatchExecutePosition(position)}
          data-testid="allocation-row-execute"
          className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/40 bg-emerald-300/15 px-3 py-1.5 text-[11px] font-black uppercase tracking-[0.18em] text-emerald-50 hover:bg-emerald-300/25"
        >
          <Rocket className="h-3 w-3" /> Execute this position
        </button>
      </div>
    </div>
  );
}

export function AllocationCard({ payload }: Props) {
  const riskMix = Object.entries(payload.risk_mix).map(([key, value]) => `${value} ${key}`).join(" · ");

  return (
    <div data-testid="allocation-card" className="relative overflow-hidden rounded-[28px] border border-cyan-300/25 bg-[#07111f]/95 shadow-[0_28px_100px_rgba(8,145,178,0.18)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(45,212,191,0.22),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(168,85,247,0.20),transparent_36%)]" />
      <div className="relative border-b border-white/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-cyan-100">
              <Sparkles className="h-3.5 w-3.5" /> Sentinel × DefiLlama · Demo-grade allocation
            </div>
            <div className="text-2xl font-black tracking-tight text-white">Allocation Proposal</div>
            <div className="mt-1 max-w-2xl text-sm leading-6 text-slate-300">
              Sentinel ranked live DefiLlama opportunities, filtered risk surfaces, sized positions, and prepared wallet-gated execution.
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-3xl border border-emerald-300/25 bg-emerald-300/10 px-4 py-3">
            <ShieldCheck className="h-7 w-7 text-emerald-200" />
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-emerald-100/60">Weighted Sentinel</div>
              <div className="text-3xl font-black text-white">{payload.weighted_sentinel}<span className="text-base text-emerald-100/50">/100</span></div>
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <StatTile label="Deploy" value={payload.total_usd} sub="requested capital" />
          <StatTile label="Blended APY" value={payload.blended_apy} sub="risk-adjusted" />
          <StatTile label="Chains" value={String(payload.chains)} sub="EVM + Solana ready" />
          <StatTile label="Combined TVL" value={payload.combined_tvl} sub="exit depth" />
        </div>
      </div>

      <div className="relative p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-black text-white"><Layers3 className="h-4 w-4 text-cyan-200" /> Position Stack</div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">Risk mix: {riskMix}</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">Position cap ≤ 35%</span>
          </div>
        </div>
        <div className="space-y-3">
          {payload.positions.map((pos) => <PositionRow key={pos.rank} position={pos} />)}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.035] p-3 text-xs text-slate-300">
          <BadgeCheck className="h-4 w-4 text-emerald-300" /> Passed: TVL depth, operating history, Sentinel score, Ilyon Shield surface, and execution sizing gates.
          <Network className="ml-auto h-4 w-4 text-cyan-200" /> Enso for EVM · Jupiter for Solana
        </div>
      </div>
    </div>
  );
}
