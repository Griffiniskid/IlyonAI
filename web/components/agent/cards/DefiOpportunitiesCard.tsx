"use client";

import type { DefiOpportunitiesPayload, DefiOpportunityItem } from "@/types/agent";
import { ExternalLink, Rocket, ShieldAlert, Sparkles, Target } from "lucide-react";

interface Props {
  payload: DefiOpportunitiesPayload;
}

function fmtUsd(value?: number | null): string {
  const n = Number(value || 0);
  if (!Number.isFinite(n) || n === 0) return "-";
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function fmtApy(value?: number | null): string {
  const n = Number(value || 0);
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : "-";
}

function riskTone(level?: string | null): string {
  const norm = (level || "").toUpperCase();
  if (norm === "LOW") return "border-emerald-300/30 bg-emerald-300/10 text-emerald-100";
  if (norm === "HIGH") return "border-rose-300/30 bg-rose-300/10 text-rose-100";
  return "border-amber-300/30 bg-amber-300/10 text-amber-100";
}

function dispatchExecutePool(item: DefiOpportunityItem) {
  if (typeof window === "undefined") return;
  const poolRef = (item.pool_id as string | undefined) || `${item.protocol} ${item.symbol || ""}`.trim();
  const message = `execute_pool_position pool="${poolRef}" amount=100`;
  // Primary: structured event for MainApp to inject into chat input.
  window.dispatchEvent(new CustomEvent("ilyon:execute-pool", { detail: { pool: poolRef, item, message } }));
  // Fallback: copy to clipboard so user can paste if listener missing.
  if (navigator?.clipboard?.writeText) {
    navigator.clipboard.writeText(message).catch(() => {});
  }
}

function OpportunityRow({ item }: { item: DefiOpportunityItem }) {
  const canExecute = Boolean(item.executable);
  return (
    <div data-testid="defi-opp-row" className="rounded-3xl border border-white/10 bg-slate-950/55 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-base font-black text-white truncate">
            {item.protocol} <span className="text-amber-200">· {item.symbol || "?"}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
            {item.chain && <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2 py-0.5 text-cyan-100">{item.chain}</span>}
            {item.product_type && <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5">{item.product_type}</span>}
            {item.risk_level && (
              <span className={`rounded-full border px-2 py-0.5 ${riskTone(item.risk_level)}`}>
                {item.risk_level} risk
              </span>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xl font-black text-amber-200">{fmtApy(item.apy)}</div>
          <div className="text-xs text-slate-400">TVL {fmtUsd(item.tvl_usd)}</div>
        </div>
      </div>
      {item.links && item.links.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {item.links.map((link) => (
            <a
              key={`${item.protocol}-${link.url}`}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="defi-opp-link"
              className="inline-flex items-center gap-1 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 font-bold text-amber-100 hover:bg-amber-300/20"
            >
              <ExternalLink className="h-3 w-3" />
              {link.label}
            </a>
          ))}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => dispatchExecutePool(item)}
          data-testid="defi-opp-execute"
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] transition ${
            canExecute
              ? "border border-emerald-300/40 bg-emerald-300/15 text-emerald-50 hover:bg-emerald-300/25"
              : "border border-amber-300/40 bg-amber-300/15 text-amber-50 hover:bg-amber-300/25"
          }`}
        >
          <Rocket className="h-3 w-3" /> Execute
        </button>
        {canExecute ? (
          <span className="text-xs text-emerald-200/80">
            via {item.adapter_id || "verified adapter"}
          </span>
        ) : (
          <span className="text-xs text-amber-100/80">
            {item.unsupported_reason || "Routed via closest-executable alternative at sign-time."}
          </span>
        )}
      </div>
    </div>
  );
}

export function DefiOpportunitiesCard({ payload }: Props) {
  const items = payload.items || [];
  return (
    <div data-testid="defi-opportunities-card" className="relative overflow-hidden rounded-[28px] border border-amber-300/20 bg-[#1b1205]/95 p-5 shadow-[0_18px_70px_rgba(245,158,11,0.12)]">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-amber-100">
          <Sparkles className="h-3.5 w-3.5" /> Constraint-matched DeFi
        </div>
        {payload.target_apy != null && (
          <div className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
            <Target className="h-3 w-3" /> Target {fmtApy(payload.target_apy)}
          </div>
        )}
        {payload.risk_levels.length > 0 && (
          <div className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
            Risk: {payload.risk_levels.join(", ")}
          </div>
        )}
        {payload.chains.length > 0 && (
          <div className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200">
            Chains: {payload.chains.join(", ")}
          </div>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {items.length > 0 ? (
          items.map((item, idx) => <OpportunityRow key={`${item.protocol}-${item.symbol}-${idx}`} item={item} />)
        ) : (
          <div className="rounded-3xl border border-white/10 bg-slate-950/55 p-4 text-sm text-slate-300">
            No matches passed the requested constraints.
          </div>
        )}
      </div>

      {payload.excluded_count > 0 && (
        <div className="mt-3 text-xs text-slate-400">
          Excluded {payload.excluded_count} candidates that violated requested risk, APY, chain, or TVL constraints.
        </div>
      )}

      {payload.blockers && payload.blockers.length > 0 && (
        <div className="mt-4 rounded-2xl border border-rose-300/30 bg-rose-300/5 p-3">
          <div className="flex items-center gap-2 text-sm font-black text-rose-100">
            <ShieldAlert className="h-4 w-4" /> Execution Blocked
          </div>
          <ul className="mt-2 space-y-1 text-xs text-rose-100/80">
            {payload.blockers.map((blocker, idx) => (
              <li key={idx}>
                {(blocker as { title?: string }).title || "Blocked"}: {(blocker as { detail?: string }).detail || ""}
              </li>
            ))}
          </ul>
          <div className="mt-2 text-[11px] text-rose-100/60">
            No signing button shown until a verified adapter can build real unsigned transactions.
          </div>
        </div>
      )}
    </div>
  );
}
