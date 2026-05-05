"use client";

import type { SentinelMatrixPayload } from "@/types/agent";
import { Activity, AlertTriangle, CheckCircle2, Gauge, ShieldCheck } from "lucide-react";

interface Props {
  payload: SentinelMatrixPayload;
}

function metricTone(value: number) {
  if (value >= 80) return "from-emerald-300 to-cyan-300";
  if (value >= 65) return "from-lime-300 to-emerald-300";
  if (value >= 50) return "from-amber-300 to-orange-300";
  return "from-red-300 to-orange-300";
}

function ScoreMeter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-3">
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="text-slate-400">{label}</span>
        <span className="font-black text-white">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full bg-gradient-to-r ${metricTone(value)}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function MatrixRow({ position }: { position: SentinelMatrixPayload["positions"][0] }) {
  return (
    <div data-testid="sentinel-matrix-row" className="rounded-3xl border border-white/10 bg-white/[0.035] p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-2xl bg-cyan-300/15 text-sm font-black text-cyan-100">{position.rank}</span>
            <span className="text-base font-black text-white">{position.protocol}</span>
            <span className="text-sm text-slate-400">{position.asset}</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-300">{position.chain}</span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2.5 py-1 text-emerald-200">{position.fit} fit</span>
            <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-2.5 py-1 text-amber-200">{position.risk} risk</span>
            {position.flags.slice(0, 3).map((flag) => (
              <span key={flag} className="rounded-full border border-red-300/20 bg-red-400/10 px-2.5 py-1 text-red-200">{flag}</span>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="relative flex h-20 w-20 items-center justify-center rounded-full border border-cyan-300/25 bg-cyan-300/10 shadow-[0_0_40px_rgba(34,211,238,0.12)]">
            <div className="text-center">
              <div className="text-2xl font-black text-white">{position.sentinel}</div>
              <div className="text-[10px] text-cyan-100/55">score</div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-4">
        <ScoreMeter label="Safety" value={position.safety} />
        <ScoreMeter label="Yield Durability" value={position.durability} />
        <ScoreMeter label="Exit Liquidity" value={position.exit} />
        <ScoreMeter label="Confidence" value={position.confidence} />
      </div>
    </div>
  );
}

export function SentinelMatrixCard({ payload }: Props) {
  return (
    <div data-testid="sentinel-matrix-card" className="relative overflow-hidden rounded-[28px] border border-emerald-300/25 bg-[#061914]/95 shadow-[0_28px_100px_rgba(16,185,129,0.14)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(52,211,153,0.22),transparent_36%),radial-gradient(circle_at_bottom_left,rgba(34,211,238,0.13),transparent_34%)]" />
      <div className="relative border-b border-white/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-100">
              <Activity className="h-3.5 w-3.5" /> Ilyon Shield cross-check
            </div>
            <div className="text-2xl font-black tracking-tight text-white">Sentinel Pool Scores</div>
            <div className="mt-1 max-w-2xl text-sm leading-6 text-slate-300">
              Every candidate is decomposed into Safety, Yield Durability, Exit Liquidity, and Confidence before it can enter execution.
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-2xl border border-emerald-300/20 bg-emerald-300/10 px-4 py-3"><div className="text-2xl font-black text-emerald-200">{payload.low_count}</div><div className="text-[10px] uppercase tracking-[0.16em] text-emerald-100/55">Low</div></div>
            <div className="rounded-2xl border border-amber-300/20 bg-amber-300/10 px-4 py-3"><div className="text-2xl font-black text-amber-200">{payload.medium_count}</div><div className="text-[10px] uppercase tracking-[0.16em] text-amber-100/55">Medium</div></div>
            <div className="rounded-2xl border border-red-300/20 bg-red-300/10 px-4 py-3"><div className="text-2xl font-black text-red-200">{payload.high_count}</div><div className="text-[10px] uppercase tracking-[0.16em] text-red-100/55">High</div></div>
          </div>
        </div>
      </div>

      <div className="relative space-y-3 p-5">
        {payload.positions.map((pos) => <MatrixRow key={pos.rank} position={pos} />)}
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.035] p-3 text-xs text-slate-300">
          <ShieldCheck className="h-4 w-4 text-emerald-300" /> Weighted Sentinel: <strong className="text-white">{payload.weighted_sentinel}/100</strong>
          <Gauge className="ml-auto h-4 w-4 text-cyan-200" /> Safety × Durability × Exit × Confidence
          <AlertTriangle className="h-4 w-4 text-amber-300" /> Any red flag caps deployment size.
          <CheckCircle2 className="h-4 w-4 text-emerald-300" /> No high-risk pool selected.
        </div>
      </div>
    </div>
  );
}
