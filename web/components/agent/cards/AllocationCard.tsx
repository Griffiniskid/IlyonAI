"use client";

import type { AllocationPayload } from "@/types/agent";
import { TrendingUp, Shield, ExternalLink } from "lucide-react";

interface Props {
  payload: AllocationPayload;
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

function PositionRow({ position }: { position: AllocationPayload["positions"][0] }) {
  const riskColor = position.risk === "low" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" :
                    position.risk === "medium" ? "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" :
                    "text-red-400 bg-red-500/10 border-red-500/20";

  return (
    <div className="flex items-center gap-3 py-2 border-b border-purple-500/10 last:border-0">
      <div className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold">
        {position.rank}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white truncate">{position.protocol}</span>
          <span className="text-xs text-purple-300/60">·</span>
          <span className="text-xs text-purple-300/80 truncate">{position.asset}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300/70 border border-purple-500/20">
            {position.chain}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-purple-300/50">via {position.router}</span>
          <span className="text-[10px] text-purple-300/50">· TVL {position.tvl}</span>
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className="text-sm font-bold text-emerald-400">{position.apy}</div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${riskColor}`}>
            Sentinel {position.sentinel}
          </span>
          <span className="text-[10px] text-purple-300/60">{position.usd} / {position.weight}%</span>
        </div>
      </div>
    </div>
  );
}

export function AllocationCard({ payload }: Props) {
  return (
    <div data-testid="allocation-card" className="rounded-xl border border-purple-500/30 bg-purple-500/5 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-purple-500/20">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-purple-400" />
          <span className="text-sm font-semibold text-white">Allocation Proposal</span>
        </div>
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-purple-500/10 border border-purple-500/20">
          <Shield className="h-3 w-3 text-purple-400" />
          <span className="text-[10px] text-purple-300">Sentinel × DefiLlama</span>
        </div>
      </div>

      <div className="p-4">
        <div className="grid grid-cols-4 gap-2 mb-4">
          <StatTile label="Deploy" value={payload.total_usd} />
          <StatTile label="Blended APY" value={payload.blended_apy} />
          <StatTile label="Chains" value={String(payload.chains)} sub="networks" />
          <StatTile label="Sentinel" value={`${payload.weighted_sentinel}/100`} sub="weighted" />
        </div>

        <div className="space-y-1">
          {payload.positions.map((pos) => (
            <PositionRow key={pos.rank} position={pos} />
          ))}
        </div>

        <div className="mt-3 pt-3 border-t border-purple-500/10 flex items-center justify-between text-xs">
          <span className="text-purple-300/50">Combined TVL: {payload.combined_tvl}</span>
          <span className="text-purple-300/50">Risk mix: {Object.entries(payload.risk_mix).map(([k, v]) => `${k}: ${v}%`).join(" · ")}</span>
        </div>
      </div>
    </div>
  );
}
