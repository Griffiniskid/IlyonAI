"use client";

import type { ExecutionPlanPayload } from "@/types/agent";
import { Play, AlertTriangle, Wallet, Clock, ArrowRight } from "lucide-react";

interface Props {
  payload: ExecutionPlanPayload;
}

function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-purple-500/5 border border-purple-500/10 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-purple-300/70">{label}</div>
      <div className="text-sm font-bold text-white">{value}</div>
      {sub && <div className="text-[10px] text-purple-300/50">{sub}</div>}
    </div>
  );
}

function ExecutionRow({ step }: { step: ExecutionPlanPayload["steps"][0] }) {
  return (
    <div data-testid="execution-row" className="flex items-center gap-3 py-2 border-b border-purple-500/10 last:border-0">
      <div className="flex-shrink-0 w-6 h-6 rounded-full bg-amber-500/20 text-amber-300 flex items-center justify-center text-xs font-bold">
        {step.index}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">{step.verb}</span>
          <span className="text-sm text-purple-300/80">{step.amount} {step.asset}</span>
          <ArrowRight className="h-3 w-3 text-purple-300/40" />
          <span className="text-sm text-purple-300/80 truncate">{step.target}</span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300/70 border border-purple-500/20">
            {step.chain}
          </span>
          <span className="text-[10px] text-purple-300/50">via {step.router}</span>
          <span className="text-[10px] text-purple-300/50">· {step.wallet}</span>
          <span className="text-[10px] text-purple-300/50">· Gas {step.gas}</span>
        </div>
      </div>
    </div>
  );
}

export function ExecutionPlanCard({ payload }: Props) {
  return (
    <div data-testid="execution-plan-card" className="rounded-xl border border-purple-500/30 bg-purple-500/5 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-purple-500/20">
        <div className="flex items-center gap-2">
          <Play className="h-4 w-4 text-purple-400" />
          <span className="text-sm font-semibold text-white">Execution Plan</span>
        </div>
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-amber-500/10 border border-amber-500/20">
          <AlertTriangle className="h-3 w-3 text-amber-400" />
          <span className="text-[10px] text-amber-300">
            Awaiting signatures · {payload.tx_count}
          </span>
        </div>
      </div>

      <div className="p-4">
        <div className="grid grid-cols-4 gap-2 mb-4">
          <StatTile label="Txs" value={String(payload.tx_count)} />
          <StatTile label="Wallets" value={payload.wallets} />
          <StatTile label="Total gas" value={payload.total_gas} />
          <StatTile label="Slippage" value={payload.slippage_cap} sub="max" />
        </div>

        <div className="space-y-1">
          {payload.steps.map((step) => (
            <ExecutionRow key={step.index} step={step} />
          ))}
        </div>

        <div className="mt-4 pt-3 border-t border-purple-500/10 space-y-3">
          <div className="flex items-center gap-2 text-xs text-purple-300/60">
            <AlertTriangle className="h-3 w-3 text-amber-400" />
            <span>Shield disclaimer: All positions have been cross-checked against known risk surfaces. High-risk protocols flagged. Review each step before signing.</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!payload.requires_signature}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-40 disabled:cursor-not-allowed transition"
            >
              <Wallet className="h-4 w-4" />
              Start Signing
            </button>
            <button
              type="button"
              className="flex items-center gap-2 px-4 py-2 rounded-lg border border-purple-500/30 text-purple-300 text-sm font-medium hover:bg-purple-500/10 transition"
            >
              <Clock className="h-4 w-4" />
              Rebalance
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
