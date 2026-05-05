"use client";

import type { SentinelTokenReportPayload } from "@/types/agent";
import { ShieldCheck, ShieldAlert, AlertTriangle, CheckCircle2, XCircle, Activity, Flame, Lock } from "lucide-react";

interface Props { payload: SentinelTokenReportPayload }

function fmtUsd(v?: number | null): string {
  const n = Number(v || 0);
  if (!Number.isFinite(n) || n === 0) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function gradeTone(g?: string | null): string {
  const s = (g || "").toUpperCase();
  if (s === "A" || s === "A+") return "border-emerald-300/40 bg-emerald-300/15 text-emerald-100";
  if (s === "B") return "border-cyan-300/40 bg-cyan-300/15 text-cyan-100";
  if (s === "C") return "border-amber-300/40 bg-amber-300/15 text-amber-100";
  if (s === "D" || s === "F") return "border-rose-300/40 bg-rose-300/15 text-rose-100";
  return "border-white/10 bg-white/5 text-slate-200";
}

function verdictTone(v?: string | null): string {
  const s = (v || "").toLowerCase();
  if (s.includes("safe")) return "text-emerald-300";
  if (s.includes("risky") || s.includes("danger")) return "text-rose-300";
  if (s.includes("caution") || s.includes("medium")) return "text-amber-300";
  return "text-slate-300";
}

function flag(label: string, value: boolean | null | undefined, goodIfTrue: boolean) {
  if (value === null || value === undefined) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-950/60 px-3 py-2 text-xs text-slate-400">
        <AlertTriangle className="h-3.5 w-3.5" /> {label}: unknown
      </div>
    );
  }
  const ok = goodIfTrue ? value : !value;
  const Icon = ok ? CheckCircle2 : XCircle;
  return (
    <div className={`flex items-center gap-2 rounded-2xl border px-3 py-2 text-xs ${ok ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-100" : "border-rose-300/30 bg-rose-300/10 text-rose-100"}`}>
      <Icon className="h-3.5 w-3.5" /> {label}
    </div>
  );
}

export function SentinelTokenReportCard({ payload }: Props) {
  const score = Math.max(0, Math.min(100, Number(payload.score || 0)));
  const sec = payload.security || {};
  const ai = payload.ai;
  const holders = payload.holders;
  const reds = ai?.red_flags || [];
  const greens = ai?.green_flags || [];
  return (
    <div data-testid="sentinel-token-report" className="relative overflow-hidden rounded-[28px] border border-emerald-300/20 bg-[#062119]/95 p-5 shadow-[0_18px_70px_rgba(16,185,129,0.12)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-100">
            <ShieldCheck className="h-3.5 w-3.5" /> Sentinel Token Report
          </div>
          <div className="mt-3 text-base font-black text-white truncate">
            {payload.symbol || payload.address.slice(0, 8) + "…"}
            {payload.chain && <span className="ml-2 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2 py-0.5 text-[10px] text-cyan-100">{payload.chain}</span>}
          </div>
          <div className="mt-1 break-all text-[11px] text-slate-400">{payload.address}</div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-black text-emerald-300 tabular-nums">{score}<span className="ml-1 text-base text-slate-400">/100</span></div>
          <div className="mt-1 inline-flex items-center gap-2">
            {payload.grade && <span className={`rounded-full border px-2 py-0.5 text-[10px] font-black tracking-[0.18em] ${gradeTone(payload.grade)}`}>GRADE {payload.grade}</span>}
            {payload.verdict && <span className={`text-xs font-bold ${verdictTone(payload.verdict)}`}>{payload.verdict.toUpperCase()}</span>}
          </div>
        </div>
      </div>

      {/* Score bar */}
      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div className="h-full bg-gradient-to-r from-rose-400 via-amber-300 to-emerald-300" style={{ width: `${score}%` }} />
      </div>

      {/* Market stats */}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Price</div>
          <div className="text-sm font-black text-white">{fmtUsd(payload.price_usd)}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Liquidity</div>
          <div className="text-sm font-black text-white">{fmtUsd(payload.liquidity_usd)}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Vol 24h</div>
          <div className="text-sm font-black text-white">{fmtUsd(payload.volume_24h_usd)}</div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Rug prob</div>
          <div className="text-sm font-black text-white">{payload.rug_probability_pct == null ? "—" : `${Number(payload.rug_probability_pct).toFixed(0)}%`}</div>
        </div>
      </div>

      {/* Security flags */}
      <div className="mt-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-2 flex items-center gap-1.5"><Lock className="h-3 w-3"/> Security</div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {flag("Mint disabled", !sec.mint_authority_enabled, true)}
          {flag("Freeze disabled", !sec.freeze_authority_enabled, true)}
          {flag(`LP locked${sec.lp_lock_percent != null ? ` (${Number(sec.lp_lock_percent).toFixed(0)}%)` : ""}`, sec.liquidity_locked, true)}
          {flag("Not honeypot", !sec.is_honeypot, true)}
          {flag("Renounced", sec.is_renounced, true)}
          {sec.rugcheck_score != null && (
            <div className="flex items-center gap-2 rounded-2xl border border-cyan-300/20 bg-cyan-300/10 px-3 py-2 text-xs text-cyan-100">
              <Activity className="h-3.5 w-3.5" /> RugCheck: {sec.rugcheck_score}
            </div>
          )}
        </div>
      </div>

      {/* Holder distribution */}
      {holders && (holders.top_holder_pct != null || holders.top10_pct != null) && (
        <div className="mt-4">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-2">Holder concentration</div>
          <div className="space-y-2">
            {holders.top_holder_pct != null && (
              <div>
                <div className="flex justify-between text-xs text-slate-300"><span>Top holder</span><span className="font-bold tabular-nums">{Number(holders.top_holder_pct).toFixed(1)}%</span></div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                  <div className={`h-full ${Number(holders.top_holder_pct) > 20 ? "bg-rose-400" : Number(holders.top_holder_pct) > 10 ? "bg-amber-300" : "bg-emerald-300"}`} style={{ width: `${Math.min(100, Number(holders.top_holder_pct))}%` }} />
                </div>
              </div>
            )}
            {holders.top10_pct != null && (
              <div>
                <div className="flex justify-between text-xs text-slate-300"><span>Top 10 holders</span><span className="font-bold tabular-nums">{Number(holders.top10_pct).toFixed(1)}%</span></div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                  <div className={`h-full ${Number(holders.top10_pct) > 50 ? "bg-rose-400" : Number(holders.top10_pct) > 30 ? "bg-amber-300" : "bg-emerald-300"}`} style={{ width: `${Math.min(100, Number(holders.top10_pct))}%` }} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Flags */}
      {(reds.length > 0 || greens.length > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {greens.length > 0 && (
            <div className="rounded-2xl border border-emerald-300/25 bg-emerald-300/5 p-3">
              <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-emerald-200"><CheckCircle2 className="h-3 w-3" /> Green flags</div>
              <ul className="mt-2 space-y-1 text-xs text-emerald-100/90">
                {greens.slice(0, 6).map((g, i) => <li key={i}>• {g}</li>)}
              </ul>
            </div>
          )}
          {reds.length > 0 && (
            <div className="rounded-2xl border border-rose-300/25 bg-rose-300/5 p-3">
              <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-rose-200"><Flame className="h-3 w-3" /> Red flags</div>
              <ul className="mt-2 space-y-1 text-xs text-rose-100/90">
                {reds.slice(0, 6).map((r, i) => <li key={i}>• {r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {(payload.recommendation || ai?.recommendation) && (
        <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-3 text-xs text-slate-200">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1 flex items-center gap-1.5"><ShieldAlert className="h-3 w-3"/> Recommendation</div>
          {payload.recommendation || ai?.recommendation}
        </div>
      )}
    </div>
  );
}
