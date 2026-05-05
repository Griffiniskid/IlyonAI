"use client";

import type { ExecutionPlanPayload } from "@/types/agent";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock, LockKeyhole, Play, Route, Wallet, Zap } from "lucide-react";

interface Props {
  payload: ExecutionPlanPayload;
  onStartSigning?: (payload: ExecutionPlanPayload) => void;
  onRerunAllocation?: () => void;
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-amber-300/15 bg-amber-300/[0.055] p-3">
      <div className="text-[10px] uppercase tracking-[0.18em] text-amber-100/55">{label}</div>
      <div className="mt-1 text-lg font-black text-white">{value}</div>
      {sub && <div className="text-[11px] text-amber-100/45">{sub}</div>}
    </div>
  );
}

function ExecutionRow({ step }: { step: ExecutionPlanPayload["steps"][0] }) {
  return (
    <div data-testid="execution-row" className="relative rounded-3xl border border-white/10 bg-slate-950/55 p-4">
      <div className="absolute left-7 top-14 h-[calc(100%-3.5rem)] w-px bg-gradient-to-b from-amber-300/40 to-transparent" />
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 gap-3">
          <div className="z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-amber-300/25 bg-amber-300/15 text-sm font-black text-amber-100">
            {step.index}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-base font-black text-white">
              <span>{step.verb}</span>
              <span className="text-amber-100">{step.amount} {step.asset}</span>
              <ArrowRight className="h-4 w-4 text-amber-200/40" />
              <span className="truncate text-slate-100">{step.target}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2.5 py-1 text-cyan-100">{step.chain}</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">via {step.router}</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">{step.wallet}</span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">Gas {step.gas}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-300/20 bg-emerald-300/10 px-3 py-2 text-xs font-bold text-emerald-100">
          <LockKeyhole className="h-4 w-4" /> Wallet gated
        </div>
      </div>
    </div>
  );
}

export function ExecutionPlanCard({ payload, onStartSigning, onRerunAllocation }: Props) {
  return (
    <div data-testid="execution-plan-card" className="relative overflow-hidden rounded-[28px] border border-amber-300/25 bg-[#1b1205]/95 shadow-[0_28px_100px_rgba(245,158,11,0.16)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(251,191,36,0.22),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(168,85,247,0.18),transparent_34%)]" />
      <div className="relative border-b border-white/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-amber-100">
              <Zap className="h-3.5 w-3.5" /> Execution strategy
            </div>
            <div className="text-2xl font-black tracking-tight text-white">Execution Plan & Transaction Build Requirement</div>
            <div className="mt-1 max-w-2xl text-sm leading-6 text-slate-300">
              Sentinel plans are strategy proposals until a route-specific unsigned transaction is built. Wallet prompts only open after real swap, bridge, stake, or deposit payloads exist.
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-3xl border border-amber-300/25 bg-amber-300/10 px-4 py-3">
            <Wallet className="h-7 w-7 text-amber-200" />
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-amber-100/60">Transactions</div>
              <div className="text-3xl font-black text-white">{payload.tx_count}</div>
            </div>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <StatTile label="Wallets" value={payload.wallets} />
          <StatTile label="Total Gas" value={payload.total_gas} />
          <StatTile label="Slippage" value={payload.slippage_cap} sub="max buffer" />
          <StatTile label="Signature Gate" value={payload.requires_signature ? "Required" : "Read only"} />
        </div>
      </div>

      <div className="relative p-5">
        <div className="mb-3 flex items-center gap-2 text-sm font-black text-white"><Route className="h-4 w-4 text-amber-200" /> Ordered route</div>
        <div className="space-y-3">
          {payload.steps.map((step) => <ExecutionRow key={step.index} step={step} />)}
        </div>

        <div className="mt-4 rounded-3xl border border-white/10 bg-white/[0.035] p-4">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
            <AlertTriangle className="h-4 w-4 text-amber-300" /> Build a protocol-specific transaction before wallet signing.
            <CheckCircle2 className="h-4 w-4 text-emerald-300" /> Follow-up steps unlock only after prior receipt confirmation.
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" disabled={!payload.requires_signature} onClick={() => onStartSigning?.(payload)} className="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-r from-amber-300 to-orange-300 px-5 py-3 text-sm font-black text-amber-950 shadow-lg shadow-amber-950/30 transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-40">
              <Play className="h-4 w-4" /> Start signing
            </button>
            <button type="button" onClick={onRerunAllocation} className="inline-flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-bold text-slate-100 transition hover:bg-white/10">
              <Clock className="h-4 w-4" /> Re-run / rebalance
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
