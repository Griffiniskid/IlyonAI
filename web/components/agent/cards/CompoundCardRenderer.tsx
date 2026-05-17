"use client";

import { Coins, TrendingUp } from "lucide-react";

/* Backend payload shape for card_type="compound_card" */
export interface CompoundCardPayload {
  card_type?: "compound_card";
  position_id: string;
  protocol: string;
  pending_rewards_usd: number;
  reward_token: string;
  reward_amount: number;
  can_compound: boolean;
  cta_label: string;
}

function fmtUsd(usd: number | null | undefined): string {
  if (usd == null || !Number.isFinite(usd)) return "—";
  if (usd >= 1e6) return `$${(usd / 1e6).toFixed(2)}M`;
  if (usd >= 1e3) return `$${(usd / 1e3).toFixed(2)}K`;
  return `$${usd.toFixed(2)}`;
}

function fmtNum(n: number | null | undefined, max = 6): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1) return n.toFixed(Math.min(4, max));
  return n.toFixed(max);
}

function prettyProtocol(slug: string | undefined): string {
  if (!slug) return "Protocol";
  return slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function CompoundCardRenderer({ payload }: { payload: CompoundCardPayload }) {
  const proto = prettyProtocol(payload.protocol);
  const disabled = !payload.can_compound;

  return (
    <div
      data-testid="compound-card"
      className="rounded-xl border border-emerald-500/30 bg-gradient-to-br from-slate-900 via-slate-900/95 to-emerald-950/40 p-4 shadow-lg"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Coins className="h-4 w-4 text-emerald-300" />
            <span className="text-base font-semibold text-slate-100">{proto}</span>
            <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-emerald-300">
              Compound
            </span>
          </div>
          <div
            className="mt-0.5 truncate font-mono text-xs text-slate-400"
            title={payload.position_id}
          >
            {payload.position_id}
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">Pending Rewards</div>
          <div className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-emerald-300">
            <TrendingUp className="h-3.5 w-3.5" />
            {fmtUsd(payload.pending_rewards_usd)}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">
            {payload.reward_token}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-slate-200">
            {fmtNum(payload.reward_amount)} {payload.reward_token}
          </div>
        </div>
      </div>

      <button
        type="button"
        disabled={disabled}
        className={`mt-3 flex w-full items-center justify-center rounded-lg border px-4 py-3 text-sm font-semibold transition ${
          disabled
            ? "cursor-not-allowed border-slate-700 bg-slate-800/40 text-slate-500"
            : "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
        }`}
      >
        {payload.cta_label}
      </button>
    </div>
  );
}
