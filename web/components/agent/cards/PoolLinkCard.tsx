"use client";

import { ExternalLink, AlertTriangle, TrendingUp, Shield } from "lucide-react";

/* Backend payload shape for card_type="pool_link" */
export interface PoolLinkPayload {
  card_type?: "pool_link";
  title?: string;
  protocol?: string;
  chain?: string;
  pool_symbol?: string;
  pool_id?: string | null;
  pool_address?: string | null;
  apy_pct?: number | null;
  apy_base_pct?: number | null;
  apy_reward_pct?: number | null;
  tvl_usd?: number | null;
  underlying_tokens?: string[] | null;
  sentinel?: Record<string, unknown> | null;
  url: string;
  amount?: string | null;
  asset_in?: string | null;
  amount_is_usd?: boolean;
  research_thesis?: string | null;
  exec_status?: "link_only" | string;
  notice?: string;
}

function fmtTvl(usd: number | null | undefined): string {
  if (usd == null || !Number.isFinite(usd)) return "—";
  if (usd >= 1e9) return `$${(usd / 1e9).toFixed(1)}B`;
  if (usd >= 1e6) return `$${(usd / 1e6).toFixed(0)}M`;
  if (usd >= 1e3) return `$${(usd / 1e3).toFixed(0)}K`;
  return `$${Math.round(usd).toLocaleString()}`;
}

function fmtPct(pct: number | null | undefined): string {
  if (pct == null || !Number.isFinite(pct)) return "—";
  return `${pct.toFixed(2)}%`;
}

function prettyProtocol(slug: string | undefined): string {
  if (!slug) return "Protocol";
  return slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function shortHost(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url.slice(0, 40);
  }
}

export function PoolLinkCard({ payload }: { payload: PoolLinkPayload }) {
  const proto = prettyProtocol(payload.protocol);
  const sentinelScore =
    payload.sentinel && typeof payload.sentinel === "object"
      ? (payload.sentinel as Record<string, number>).opportunity_score ??
        (payload.sentinel as Record<string, number>).overall_score ??
        null
      : null;

  return (
    <div className="rounded-xl border border-amber-500/30 bg-gradient-to-br from-slate-900 via-slate-900/95 to-amber-950/40 p-4 shadow-lg">
      {/* Notice banner */}
      <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span>
          {payload.notice ||
            "Direct pool execution is temporarily unavailable. Open this pool on the protocol app to deposit."}
        </span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-slate-100">
              {proto}
            </span>
            {payload.chain && (
              <span className="rounded-md border border-slate-700 bg-slate-800/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                {payload.chain}
              </span>
            )}
          </div>
          <div className="mt-0.5 truncate text-sm font-medium text-slate-200">
            {payload.pool_symbol || payload.title || "Pool"}
          </div>
        </div>
        {sentinelScore != null && (
          <div className="flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-300">
            <Shield className="h-3.5 w-3.5" />
            <span>{Math.round(Number(sentinelScore))}</span>
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            APY
          </div>
          <div className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-emerald-300">
            <TrendingUp className="h-3.5 w-3.5" />
            {fmtPct(payload.apy_pct)}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            TVL
          </div>
          <div className="mt-0.5 text-sm font-semibold text-slate-200">
            {fmtTvl(payload.tvl_usd ?? null)}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            Plan
          </div>
          <div className="mt-0.5 truncate text-sm font-semibold text-slate-200">
            {payload.amount && payload.asset_in
              ? `${payload.amount} ${payload.asset_in}`
              : "—"}
          </div>
        </div>
      </div>

      {/* Underlying tokens chips */}
      {payload.underlying_tokens && payload.underlying_tokens.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {payload.underlying_tokens.slice(0, 6).map((tok, i) => (
            <span
              key={`${tok}-${i}`}
              className="rounded border border-slate-700/60 bg-slate-800/60 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
            >
              {tok.length > 12 ? `${tok.slice(0, 6)}…${tok.slice(-4)}` : tok}
            </span>
          ))}
        </div>
      )}

      {/* Optional thesis */}
      {payload.research_thesis && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs text-slate-400">
          {payload.research_thesis}
        </div>
      )}

      {/* Big CTA */}
      <a
        href={payload.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 flex items-center justify-between rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-4 py-3 transition hover:bg-emerald-500/25"
      >
        <div>
          <div className="text-sm font-semibold text-emerald-300">
            Open on {proto}
          </div>
          <div className="text-[11px] text-emerald-400/70">
            {shortHost(payload.url)} — finalise deposit on the protocol app
          </div>
        </div>
        <ExternalLink className="h-4 w-4 text-emerald-300" />
      </a>
    </div>
  );
}
