"use client";

import type { SentinelWhaleFeedPayload } from "@/types/agent";
import { Anchor, ArrowDownLeft, ArrowUpRight, ExternalLink } from "lucide-react";

interface Props { payload: SentinelWhaleFeedPayload }

function fmtUsd(v?: number | null): string {
  const n = Number(v || 0);
  if (!Number.isFinite(n) || n === 0) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function actionTone(a?: string | null): { color: string; Icon: typeof ArrowDownLeft } {
  const v = (a || "").toLowerCase();
  if (v.includes("buy") || v.includes("accumulat") || v.includes("in")) return { color: "text-emerald-300", Icon: ArrowDownLeft };
  if (v.includes("sell") || v.includes("exit") || v.includes("out")) return { color: "text-rose-300", Icon: ArrowUpRight };
  return { color: "text-slate-300", Icon: ArrowDownLeft };
}

export function SentinelWhaleFeedCard({ payload }: Props) {
  const items = payload.items || [];
  return (
    <div data-testid="sentinel-whale-feed" className="relative overflow-hidden rounded-[28px] border border-violet-300/20 bg-[#150929]/95 p-5 shadow-[0_18px_70px_rgba(167,139,250,0.12)]">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-violet-300/25 bg-violet-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-violet-100">
          <Anchor className="h-3.5 w-3.5" /> Whale Activity
        </div>
        <div className="text-xs text-slate-300">Last <span className="font-bold">{payload.hours}h</span>{payload.chain ? <> · <span className="font-bold">{payload.chain}</span></> : null}</div>
        <div className="ml-auto text-xs text-slate-400">{items.length} events</div>
      </div>

      {items.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/55 p-4 text-sm text-slate-300">
          No whale activity detected in this window. Whale events fire on transfers ≥ $100K typically; try widening the time range or switching chains.
        </div>
      ) : (
        <div className="mt-4 space-y-2">
          {items.slice(0, 12).map((it, i) => {
            const { color, Icon } = actionTone(it.action);
            const wallet = it.wallet || "";
            return (
              <div key={i} className="flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950/55 p-3">
                <Icon className={`h-4 w-4 ${color}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className={`text-xs font-black uppercase tracking-[0.16em] ${color}`}>{it.action || "tx"}</span>
                    <span className="text-sm font-bold text-white">{it.symbol || "?"}</span>
                    {it.chain && <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2 py-0.5 text-[10px] text-cyan-100">{it.chain}</span>}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-400 truncate">
                    wallet <code className="text-slate-300">{wallet ? `${wallet.slice(0, 10)}…` : "—"}</code>
                  </div>
                </div>
                <div className="text-right text-sm font-black text-amber-200 tabular-nums">{fmtUsd(it.usd_value)}</div>
                {it.tx_hash && (
                  <a href={`https://solscan.io/tx/${it.tx_hash}`} target="_blank" rel="noopener noreferrer" className="text-slate-400 hover:text-slate-200" title="View transaction">
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
