"use client";

import type { SentinelSmartMoneyHubPayload } from "@/types/agent";
import { Crown, Flame, Sparkles, TrendingDown, TrendingUp } from "lucide-react";

interface Props { payload: SentinelSmartMoneyHubPayload }

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
  if (!Number.isFinite(n) || n === 0) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

export function SentinelSmartMoneyHubCard({ payload }: Props) {
  const top = payload.top_wallets || [];
  const acc = payload.recent_accumulations || [];
  const trend = payload.trending_tokens || [];
  const conv = payload.conviction || [];
  const flow = (payload.flow_direction || "").toLowerCase();
  return (
    <div data-testid="sentinel-smart-money" className="relative overflow-hidden rounded-[28px] border border-fuchsia-300/20 bg-[#1a0a26]/95 p-5 shadow-[0_18px_70px_rgba(232,121,249,0.12)]">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-fuchsia-300/25 bg-fuchsia-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-fuchsia-100">
          <Sparkles className="h-3.5 w-3.5" /> Smart Money Hub
        </div>
        <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2 py-0.5 text-[10px] text-cyan-100">{payload.chain}</span>
        {flow && (
          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${flow.includes("accumulat") ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-100" : "border-rose-300/30 bg-rose-300/10 text-rose-100"}`}>
            {flow.includes("accumulat") ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {flow}
          </span>
        )}
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {top.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-2 flex items-center gap-1.5"><Crown className="h-3 w-3"/> Top wallets</div>
            <div className="space-y-1.5">
              {top.slice(0, 5).map((w, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <code className="text-slate-300">{w.address.slice(0, 12)}…</code>
                  <div className="flex items-center gap-2 tabular-nums">
                    <span className="font-bold text-white">{fmtUsd(w.usd_value)}</span>
                    {w.pnl_24h != null && (
                      <span className={Number(w.pnl_24h) >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtPct(w.pnl_24h)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {trend.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-2 flex items-center gap-1.5"><Flame className="h-3 w-3"/> Trending</div>
            <div className="space-y-1.5">
              {trend.slice(0, 5).map((t, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white">{t.symbol}</span>
                  <div className="flex items-center gap-2 tabular-nums">
                    <span className="text-slate-300">{fmtUsd(t.usd_value)}</span>
                    {t.price_change != null && (
                      <span className={Number(t.price_change) >= 0 ? "text-emerald-300" : "text-rose-300"}>{fmtPct(t.price_change)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {acc.length > 0 && (
          <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-2">Recent accumulations</div>
            <div className="space-y-1.5">
              {acc.slice(0, 5).map((a, i) => (
                <div key={i} className="flex items-center justify-between text-xs">
                  <span className="font-bold text-white">{a.symbol}</span>
                  <span className="text-emerald-300 tabular-nums">{fmtUsd(a.usd_value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {conv.length > 0 && (
          <div className="rounded-2xl border border-fuchsia-300/20 bg-fuchsia-300/5 p-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-fuchsia-200 mb-2">Conviction picks</div>
            <div className="space-y-1.5">
              {conv.slice(0, 5).map((c, i) => (
                <div key={i} className="text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white">{c.symbol}</span>
                    {c.score != null && <span className="text-fuchsia-200 tabular-nums">{Number(c.score).toFixed(0)}</span>}
                  </div>
                  {c.reason && <div className="text-[11px] text-slate-400 mt-0.5">{c.reason}</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {top.length === 0 && acc.length === 0 && trend.length === 0 && conv.length === 0 && (
        <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/55 p-4 text-sm text-slate-300">
          No live signals returned for {payload.chain} right now. Try again in a minute — the hub refreshes on a 90s cadence.
        </div>
      )}
    </div>
  );
}
