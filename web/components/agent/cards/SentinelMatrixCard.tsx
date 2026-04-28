"use client";

import type { SentinelMatrixPayload } from "@/types/agent";
import { Shield, Activity } from "lucide-react";

interface Props {
  payload: SentinelMatrixPayload;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const color = value >= 80 ? "bg-emerald-500" : value >= 60 ? "bg-yellow-500" : value >= 40 ? "bg-orange-500" : "bg-red-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px]">
        <span className="text-purple-300/60">{label}</span>
        <span className="text-white font-medium">{value}</span>
      </div>
      <div className="h-1 bg-purple-500/10 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function MatrixRow({ position }: { position: SentinelMatrixPayload["positions"][0] }) {
  const fitColor = position.fit === "conservative" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" :
                   position.fit === "balanced" ? "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" :
                   "text-red-400 bg-red-500/10 border-red-500/20";

  const riskColor = position.risk === "low" ? "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" :
                    position.risk === "medium" ? "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" :
                    "text-red-400 bg-red-500/10 border-red-500/20";

  return (
    <div data-testid="sentinel-matrix-row" className="py-3 border-b border-purple-500/10 last:border-0">
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold">
          {position.rank}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white truncate">{position.protocol}</span>
            <span className="text-xs text-purple-300/60">·</span>
            <span className="text-xs text-purple-300/80 truncate">{position.asset}</span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300/70 border border-purple-500/20">
              {position.chain}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${fitColor}`}>
              {position.fit}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${riskColor}`}>
              {position.risk} risk
            </span>
          </div>
        </div>
        <div className="flex-shrink-0 text-right">
          <div className="text-lg font-bold text-white">{position.sentinel}</div>
          <div className="text-[10px] text-purple-300/50">/100</div>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-3 mt-2 ml-9">
        <ScoreBar label="Safety" value={position.safety} />
        <ScoreBar label="Yield dur." value={position.durability} />
        <ScoreBar label="Exit liq." value={position.exit} />
        <ScoreBar label="Confidence" value={position.confidence} />
      </div>
      {position.flags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2 ml-9">
          {position.flags.map((flag) => (
            <span key={flag} className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
              {flag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function SentinelMatrixCard({ payload }: Props) {
  return (
    <div data-testid="sentinel-matrix-card" className="rounded-xl border border-purple-500/30 bg-purple-500/5 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-purple-500/20">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-purple-400" />
          <span className="text-sm font-semibold text-white">Sentinel Pool Scores</span>
        </div>
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-purple-500/10 border border-purple-500/20">
          <Shield className="h-3 w-3 text-purple-400" />
          <span className="text-[10px] text-purple-300">Ilyon safety lens</span>
        </div>
      </div>

      <div className="p-4">
        <div className="space-y-1">
          {payload.positions.map((pos) => (
            <MatrixRow key={pos.rank} position={pos} />
          ))}
        </div>

        <div className="mt-4 pt-3 border-t border-purple-500/10 flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs">
            <span className="text-emerald-400">{payload.low_count} Low</span>
            <span className="text-yellow-400">{payload.medium_count} Medium</span>
            <span className="text-red-400">{payload.high_count} High</span>
          </div>
          <div className="text-sm font-bold text-white">
            Weighted: {payload.weighted_sentinel}/100
          </div>
        </div>
      </div>
    </div>
  );
}
