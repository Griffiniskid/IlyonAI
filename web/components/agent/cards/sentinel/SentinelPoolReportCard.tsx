"use client";

import type { SentinelPoolReportPayload } from "@/types/agent";
import { Droplet, ExternalLink, Rocket, Target, TrendingUp } from "lucide-react";

interface Props { payload: SentinelPoolReportPayload }

function fmtUsd(v?: number | null): string {
  const n = Number(v || 0);
  if (!Number.isFinite(n) || n === 0) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}
function fmtPct(v?: number | null): string {
  const n = Number(v || 0);
  return Number.isFinite(n) ? `${n.toFixed(2)}%` : "—";
}
function ilTone(s?: string | null): string {
  const v = (s || "").toLowerCase();
  if (v === "no" || v === "low") return "border-emerald-300/30 bg-emerald-300/10 text-emerald-100";
  if (v === "high") return "border-rose-300/30 bg-rose-300/10 text-rose-100";
  return "border-amber-300/30 bg-amber-300/10 text-amber-100";
}

function dispatchExecute(payload: SentinelPoolReportPayload) {
  if (typeof window === "undefined") return;
  const ref = payload.pool_id || `${payload.protocol || ""} ${payload.symbol || ""}`.trim();
  const message = `execute_pool_position pool="${ref}" amount=100`;
  window.dispatchEvent(new CustomEvent("ilyon:execute-pool", { detail: { pool: ref, message } }));
}

export function SentinelPoolReportCard({ payload }: Props) {
  return (
    <div data-testid="sentinel-pool-report" className="relative overflow-hidden rounded-[28px] border border-cyan-300/20 bg-[#062029]/95 p-5 shadow-[0_18px_70px_rgba(34,211,238,0.12)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-cyan-100">
            <Droplet className="h-3.5 w-3.5" /> Sentinel Pool Report
          </div>
          <div className="mt-3 text-base font-black text-white truncate">
            {payload.protocol} <span className="text-amber-200">· {payload.symbol || "?"}</span>
            {payload.chain && <span className="ml-2 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-slate-300">{payload.chain}</span>}
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-black text-amber-200 tabular-nums">{fmtPct(payload.apy)}</div>
          <div className="text-xs text-slate-400">TVL {fmtUsd(payload.tvl_usd)}</div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Base APY</div>
          <div className="text-sm font-black text-white">{fmtPct(payload.apy_base)}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Reward APY</div>
          <div className="text-sm font-black text-white">{fmtPct(payload.apy_reward)}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Vol 24h</div>
          <div className="text-sm font-black text-white">{fmtUsd(payload.volume_24h_usd)}</div>
        </div>
        <div className={`rounded-2xl border p-3 ${ilTone(payload.il_risk)}`}>
          <div className="text-[10px] uppercase tracking-[0.18em] opacity-80">IL risk</div>
          <div className="text-sm font-black uppercase">{payload.il_risk || "—"}</div>
        </div>
      </div>

      {payload.predicted_class && (
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
          <TrendingUp className="h-3 w-3" /> DefiLlama outlook: <span className="font-bold">{payload.predicted_class}</span>
        </div>
      )}

      {payload.underlying_tokens && payload.underlying_tokens.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1.5 flex items-center gap-1.5"><Target className="h-3 w-3"/> Underlying tokens</div>
          <div className="flex flex-wrap gap-1.5">
            {payload.underlying_tokens.slice(0, 6).map((t, i) => (
              <code key={i} className="rounded-full border border-white/10 bg-slate-950/60 px-2 py-1 text-[10px] text-slate-200">{t.slice(0, 14)}…</code>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => dispatchExecute(payload)}
          className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/40 bg-emerald-300/15 px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] text-emerald-50 hover:bg-emerald-300/25"
        >
          <Rocket className="h-3 w-3" /> Execute deposit
        </button>
        {payload.links && payload.links.map((l, i) => (
          <a key={i} href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/10">
            <ExternalLink className="h-3 w-3" /> {l.label}
          </a>
        ))}
      </div>
    </div>
  );
}
