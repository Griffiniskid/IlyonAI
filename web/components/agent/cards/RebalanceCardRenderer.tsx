"use client";

import { Repeat, TrendingUp, AlertTriangle } from "lucide-react";
import { V3RangeBlock } from "./V3RangeBlock";
import type { V3RangeBlock as V3RangeBlockPayload } from "@/types/agent";

/* Backend payload shape for card_type="rebalance_card" */
export interface RebalanceCardPayload {
  card_type?: "rebalance_card";
  position_id: string;
  protocol: string;
  pair: string;
  current_range: [number, number];
  suggested_range: [number, number];
  current_value_usd: number;
  time_out_of_range_pct: number;
  estimated_fee_apr_uplift_pct: number;
  cta_label: string;
  /** Optional interactive V3 picker payload — present only for concentrated-liquidity protocols. */
  range_block?: V3RangeBlockPayload | null;
}

/** V3-style concentrated-liquidity protocol slugs that should render the interactive picker. */
function isV3Protocol(slug: string | undefined): boolean {
  if (!slug) return false;
  const s = slug.toLowerCase();
  return (
    s.includes("v3") ||
    s.includes("v4") ||
    s.includes("concentrated") ||
    s === "uniswap-v3" ||
    s === "pancakeswap-v3" ||
    s === "sushiswap-v3"
  );
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

function fmtRange(r: [number, number] | null | undefined): string {
  if (!r || r.length !== 2) return "—";
  const [lo, hi] = r;
  const f = (x: number) => (Math.abs(x) >= 1 ? x.toFixed(2) : x.toFixed(6));
  return `${f(lo)} – ${f(hi)}`;
}

function prettyProtocol(slug: string | undefined): string {
  if (!slug) return "Protocol";
  return slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function RebalanceCardRenderer({ payload }: { payload: RebalanceCardPayload }) {
  const proto = prettyProtocol(payload.protocol);
  const outOfRange = (payload.time_out_of_range_pct ?? 0) >= 25;

  return (
    <div
      data-testid="rebalance-card"
      className="rounded-xl border border-violet-500/30 bg-gradient-to-br from-slate-900 via-slate-900/95 to-violet-950/40 p-4 shadow-lg"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Repeat className="h-4 w-4 text-violet-300" />
            <span className="text-base font-semibold text-slate-100">{proto}</span>
            <span className="rounded-md border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-violet-300">
              Rebalance
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
        {outOfRange && (
          <div className="flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-300">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>{fmtPct(payload.time_out_of_range_pct)} OOR</span>
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Current Range</div>
          <div className="mt-0.5 text-sm font-semibold text-slate-200">
            {fmtRange(payload.current_range)}
          </div>
        </div>
        <div className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-violet-400">Suggested Range</div>
          <div className="mt-0.5 text-sm font-semibold text-violet-200">
            {fmtRange(payload.suggested_range)}
          </div>
        </div>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Position Value</div>
          <div className="mt-0.5 text-sm font-semibold text-slate-200">
            {fmtUsd(payload.current_value_usd)}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Fee APR Uplift</div>
          <div className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-emerald-300">
            <TrendingUp className="h-3.5 w-3.5" />
            +{fmtPct(payload.estimated_fee_apr_uplift_pct)}
          </div>
        </div>
      </div>

      {payload.range_block && isV3Protocol(payload.protocol) && (
        <div className="mt-3">
          <V3RangeBlock block={payload.range_block} />
        </div>
      )}

      <button
        type="button"
        className="mt-3 flex w-full items-center justify-center rounded-lg border border-violet-500/40 bg-violet-500/15 px-4 py-3 text-sm font-semibold text-violet-200 transition hover:bg-violet-500/25"
      >
        {payload.cta_label}
      </button>
    </div>
  );
}
