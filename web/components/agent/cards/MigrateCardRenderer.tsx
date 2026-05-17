"use client";

import { ArrowRight, TrendingUp, Fuel } from "lucide-react";

/* Backend payload shape for card_type="migrate_card" */
export interface MigrateCardPayload {
  card_type?: "migrate_card";
  position_id: string;
  from_protocol: string;
  to_protocol: string;
  pair: string;
  current_apr: number;
  target_apr: number;
  estimated_gas_usd: number;
  cta_label: string;
}

function fmtUsd(usd: number | null | undefined): string {
  if (usd == null || !Number.isFinite(usd)) return "—";
  if (usd >= 1e6) return `$${(usd / 1e6).toFixed(2)}M`;
  if (usd >= 1e3) return `$${(usd / 1e3).toFixed(2)}K`;
  return `$${usd.toFixed(2)}`;
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

export function MigrateCardRenderer({ payload }: { payload: MigrateCardPayload }) {
  const fromProto = prettyProtocol(payload.from_protocol);
  const toProto = prettyProtocol(payload.to_protocol);
  const uplift =
    Number.isFinite(payload.target_apr) && Number.isFinite(payload.current_apr)
      ? payload.target_apr - payload.current_apr
      : null;

  return (
    <div
      data-testid="migrate-card"
      className="rounded-xl border border-cyan-500/30 bg-gradient-to-br from-slate-900 via-slate-900/95 to-cyan-950/40 p-4 shadow-lg"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-base font-semibold text-slate-100">
            <span>{fromProto}</span>
            <ArrowRight className="h-4 w-4 text-cyan-300" />
            <span>{toProto}</span>
            <span className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-cyan-300">
              Migrate
            </span>
          </div>
          <div className="mt-0.5 truncate text-sm font-medium text-slate-200">{payload.pair}</div>
          <div
            className="mt-0.5 truncate font-mono text-xs text-slate-400"
            title={payload.position_id}
          >
            {payload.position_id}
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Current APR</div>
          <div className="mt-0.5 text-sm font-semibold text-slate-300">
            {fmtPct(payload.current_apr)}
          </div>
        </div>
        <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-cyan-400">Target APR</div>
          <div className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-cyan-200">
            <TrendingUp className="h-3.5 w-3.5" />
            {fmtPct(payload.target_apr)}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Gas Est.</div>
          <div className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-slate-200">
            <Fuel className="h-3.5 w-3.5" />
            {fmtUsd(payload.estimated_gas_usd)}
          </div>
        </div>
      </div>

      {uplift != null && (
        <div className="mt-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          Net APR uplift: <span className="font-semibold">+{fmtPct(uplift)}</span>
        </div>
      )}

      <button
        type="button"
        className="mt-3 flex w-full items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-4 py-3 text-sm font-semibold text-cyan-200 transition hover:bg-cyan-500/25"
      >
        {payload.cta_label}
      </button>
    </div>
  );
}
