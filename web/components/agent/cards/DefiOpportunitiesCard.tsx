"use client";

import { useState } from "react";
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

// Split a pool symbol ("SOL-USDC", "WETH/USDC") into its deposit-token legs.
function poolTokens(symbol?: string | null): string[] {
  if (!symbol) return [];
  const legs = symbol
    .split(/[-/_·]/)
    .map((s) => s.trim().toUpperCase())
    .filter((s) => /^[A-Z][A-Z0-9.]{0,9}$/.test(s));
  return Array.from(new Set(legs));
}

function dispatchExecutePool(item: DefiOpportunityItem, amount?: string, token?: string) {
  if (typeof window === "undefined") return;
  const poolRef = (item.pool_id as string | undefined) || `${item.protocol} ${item.symbol || ""}`.trim();
  const amt = (amount || "").trim() || "100";
  const suffix = token ? `with ${amt} ${token}` : `with $${amt}`;
  const message = `Execute deposit into pool ${poolRef} ${suffix}`;
  // Primary: structured event for MainApp to inject into chat input.
  window.dispatchEvent(new CustomEvent("ilyon:execute-pool", { detail: { pool: poolRef, item, message } }));
  // Fallback: copy to clipboard so user can paste if listener missing.
  if (navigator?.clipboard?.writeText) {
    navigator.clipboard.writeText(message).catch(() => {});
  }
}

function SentinelAxisBar({ label, score }: { label: string; score: number }) {
  // 0-100 → tint: red (low) → amber (mid) → emerald (high)
  const pct = Math.max(0, Math.min(100, score));
  const tone =
    pct >= 70 ? "bg-emerald-400/70" : pct >= 45 ? "bg-amber-400/70" : "bg-rose-400/70";
  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-slate-400">
      <span className="w-20 text-right">{label}</span>
      <div className="relative h-1.5 w-24 overflow-hidden rounded-full bg-white/10">
        <div className={`absolute left-0 top-0 h-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-6 text-right tabular-nums text-slate-300">{pct}</span>
    </div>
  );
}

function OpportunityRow({ item }: { item: DefiOpportunityItem }) {
  const canExecute = Boolean(item.executable);
  const sentinel = item.sentinel;
  const tokens = poolTokens(item.symbol);
  const [showForm, setShowForm] = useState(false);
  const [amount, setAmount] = useState("100");
  const [token, setToken] = useState(tokens[0] || "");
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

      {/* BUG-RC-011: 4-axis sentinel scoring bar. Backend computes block
          when scoring is available; fall back to a 'scoring unavailable'
          badge rather than silently omitting (so testers can tell the
          difference between 'low score' and 'no signal'). */}
      {sentinel ? (
        <div data-testid="defi-opp-sentinel" className="mt-3 grid gap-1 rounded-2xl border border-white/5 bg-white/[0.02] p-2">
          <SentinelAxisBar label="Safety" score={sentinel.safety} />
          <SentinelAxisBar label="Durability" score={sentinel.durability} />
          <SentinelAxisBar label="Exit" score={sentinel.exit} />
          <SentinelAxisBar label="Confidence" score={sentinel.confidence} />
        </div>
      ) : (
        <div data-testid="defi-opp-sentinel-unavailable" className="mt-3 rounded-2xl border border-white/5 bg-white/[0.02] p-2 text-[10px] uppercase tracking-[0.18em] text-slate-500">
          Sentinel scoring unavailable
        </div>
      )}
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
        {canExecute ? (
          <>
            <button
              type="button"
              onClick={() => setShowForm((v) => !v)}
              data-testid="defi-opp-execute"
              className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/40 bg-emerald-300/15 px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] text-emerald-50 transition hover:bg-emerald-300/25"
            >
              <Rocket className="h-3 w-3" /> Execute
            </button>
            <span className="text-xs text-emerald-200/80">
              via {item.adapter_id || "verified adapter"}
            </span>
          </>
        ) : (
          <>
            {item.pool_deeplink && (
              <a
                href={item.pool_deeplink}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="defi-opp-open-pool"
                className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/40 bg-amber-300/15 px-3 py-1.5 text-xs font-black uppercase tracking-[0.18em] text-amber-50 transition hover:bg-amber-300/25"
              >
                <ExternalLink className="h-3 w-3" /> Open pool
              </a>
            )}
            <span data-testid="defi-opp-not-executable" className="text-xs text-amber-100/80">
              {item.unsupported_reason || "Not one-click executable — open the pool on its protocol to deposit."}
            </span>
          </>
        )}
      </div>
      {canExecute && showForm && (
        <div
          data-testid="defi-opp-deposit-form"
          className="mt-3 flex flex-wrap items-end gap-3 rounded-2xl border border-emerald-300/20 bg-emerald-300/5 p-3"
        >
          <label className="flex flex-col gap-1 text-[10px] uppercase tracking-[0.14em] text-emerald-100/70">
            Amount
            <input
              type="number"
              min="0"
              step="any"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              data-testid="defi-opp-amount"
              className="w-28 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-1.5 text-sm font-bold text-white outline-none focus:border-emerald-300/50"
            />
          </label>
          {tokens.length > 0 && (
            <label className="flex flex-col gap-1 text-[10px] uppercase tracking-[0.14em] text-emerald-100/70">
              Token
              <select
                value={token}
                onChange={(e) => setToken(e.target.value)}
                data-testid="defi-opp-token"
                className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-1.5 text-sm font-bold text-white outline-none focus:border-emerald-300/50"
              >
                {tokens.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            onClick={() => {
              dispatchExecutePool(item, amount, tokens.length > 0 ? token : undefined);
              setShowForm(false);
            }}
            disabled={!(Number(amount) > 0)}
            data-testid="defi-opp-build-deposit"
            className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/40 bg-emerald-300/20 px-4 py-2 text-xs font-black uppercase tracking-[0.18em] text-emerald-50 transition hover:bg-emerald-300/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Rocket className="h-3 w-3" /> Build deposit
          </button>
        </div>
      )}
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

      {/* BUG-RC-007 / BUG-RC-021: footer removed. The natural-language
          chat response from src/agent/simple_runtime.py::_format_opportunity_search_response
          already includes 'Excluded N candidates that violated the requested
          risk, APY, chain, or TVL constraints.' as the canonical sentence.
          Rendering it again here produced a verbatim duplicate paragraph
          in every search response (AI Bug Convo.md lines 29+163,
          249+385, 593+713) and a wording drift ('violated requested' vs
          'violated the requested') across the two sites. */}

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
