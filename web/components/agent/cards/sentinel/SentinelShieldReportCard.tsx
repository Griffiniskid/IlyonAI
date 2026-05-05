"use client";

import type { SentinelShieldReportPayload } from "@/types/agent";
import { Shield, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";

interface Props { payload: SentinelShieldReportPayload }

function verdictTone(v?: string | null): { color: string; Icon: typeof Shield } {
  const s = (v || "").toLowerCase();
  if (s.includes("safe") || s.includes("clean") || s.includes("ok")) return { color: "border-emerald-300/40 bg-emerald-300/10 text-emerald-100", Icon: ShieldCheck };
  if (s.includes("danger") || s.includes("critical") || s.includes("malicious")) return { color: "border-rose-300/40 bg-rose-300/10 text-rose-100", Icon: ShieldX };
  if (s.includes("caution") || s.includes("medium") || s.includes("warn")) return { color: "border-amber-300/40 bg-amber-300/10 text-amber-100", Icon: ShieldAlert };
  return { color: "border-white/10 bg-white/5 text-slate-200", Icon: Shield };
}

function severityTone(s?: string): string {
  const v = (s || "").toLowerCase();
  if (v === "high" || v === "critical") return "border-rose-300/40 bg-rose-300/15 text-rose-100";
  if (v === "medium") return "border-amber-300/40 bg-amber-300/15 text-amber-100";
  if (v === "low") return "border-emerald-300/40 bg-emerald-300/15 text-emerald-100";
  return "border-white/10 bg-white/5 text-slate-200";
}

export function SentinelShieldReportCard({ payload }: Props) {
  const summary = payload.summary || {};
  const approvals = payload.approvals || [];
  const { color, Icon } = verdictTone(payload.verdict);
  return (
    <div data-testid="sentinel-shield-report" className="relative overflow-hidden rounded-[28px] border border-blue-300/20 bg-[#062131]/95 p-5 shadow-[0_18px_70px_rgba(59,130,246,0.12)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] ${color}`}>
            <Icon className="h-3.5 w-3.5" /> Sentinel Shield · {payload.verdict || "report"}
          </div>
          <div className="mt-3 break-all text-sm font-bold text-white">{payload.address}</div>
          {payload.chain && <div className="mt-0.5 text-[11px] text-slate-400">on {payload.chain}</div>}
        </div>
        {payload.risk_score != null && (
          <div className="text-right">
            <div className="text-3xl font-black text-white tabular-nums">{Number(payload.risk_score).toFixed(0)}</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Risk score</div>
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Total approvals</div>
          <div className="text-sm font-black text-white">{summary.total_approvals ?? 0}</div>
        </div>
        <div className="rounded-2xl border border-rose-300/20 bg-rose-300/5 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-rose-200">High risk</div>
          <div className="text-sm font-black text-rose-100">{summary.high_risk_count ?? 0}</div>
        </div>
        <div className="rounded-2xl border border-amber-300/20 bg-amber-300/5 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-amber-200">Medium</div>
          <div className="text-sm font-black text-amber-100">{summary.medium_risk_count ?? 0}</div>
        </div>
        <div className="rounded-2xl border border-emerald-300/20 bg-emerald-300/5 p-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-emerald-200">Low</div>
          <div className="text-sm font-black text-emerald-100">{summary.low_risk_count ?? 0}</div>
        </div>
      </div>

      {approvals.length > 0 ? (
        <div className="mt-4 space-y-1.5">
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">Approvals</div>
          {approvals.slice(0, 8).map((a, i) => (
            <div key={i} className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-950/55 p-2.5 text-xs">
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-black tracking-[0.16em] uppercase ${severityTone(a.severity || a.risk)}`}>{(a.severity || a.risk || "—")}</span>
              <code className="text-slate-300 truncate">{(a.spender || a.contract || "").slice(0, 14)}…</code>
              <span className="ml-auto text-slate-200">{a.token || a.symbol || ""}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-emerald-300/20 bg-emerald-300/5 p-3 text-xs text-emerald-100">
          No outstanding approvals detected. Wallet looks clean from a Shield perspective.
        </div>
      )}

      {payload.recommendation && (
        <div className="mt-3 text-[11px] text-slate-300">{payload.recommendation}</div>
      )}
      {payload.scanned_at && (
        <div className="mt-3 text-[10px] text-slate-500">Scanned {new Date(payload.scanned_at).toLocaleString()}</div>
      )}
    </div>
  );
}
