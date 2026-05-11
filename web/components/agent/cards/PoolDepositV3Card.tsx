"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, ExternalLink, Layers3, Sparkles, TrendingUp, Target, Activity, Calculator } from "lucide-react";

/* Frontend math — no backend round-trip on slider drag. */

function capitalEfficiency(pLower: number, pCurrent: number, pUpper: number): number {
  if (pCurrent <= pLower || pCurrent >= pUpper) return 1;
  // Symmetric range Uniswap-V3 closed-form approximation: lower handle dominates.
  const eff = 1 / (1 - Math.sqrt(pLower / pUpper));
  return Math.max(1, eff);
}

function inRangeProbability(lowerPct: number, upperPct: number, cdf30d: number[]): number {
  if (!cdf30d || cdf30d.length === 0) {
    // Fallback: assume normal-ish dist, ±10% covers ~78%.
    const total = Math.abs(upperPct - lowerPct);
    if (total >= 50) return 0.99;
    if (total >= 25) return 0.94;
    if (total >= 15) return 0.85;
    if (total >= 10) return 0.78;
    if (total >= 5) return 0.52;
    return 0.25;
  }
  // CDF is 100 buckets over [0.5x, 2x] ratio of current price.
  // lowerPct=-10 → ratio=0.9; upperPct=+10 → ratio=1.1.
  const lowerRatio = 1 + lowerPct / 100;
  const upperRatio = 1 + upperPct / 100;
  const ratioToIdx = (r: number) => {
    const t = Math.max(0, Math.min(1, (r - 0.5) / (2.0 - 0.5)));
    return Math.floor(t * (cdf30d.length - 1));
  };
  const pLo = cdf30d[ratioToIdx(lowerRatio)] ?? 0;
  const pHi = cdf30d[ratioToIdx(upperRatio)] ?? 1;
  return Math.max(0, Math.min(1, pHi - pLo));
}

function aprAtRange(baseApr: number, capEff: number, prob: number, rewards: number): number {
  return baseApr * capEff * prob + rewards;
}

function fmtPct(x: number, dp = 2): string {
  if (!Number.isFinite(x)) return "—";
  return `${x.toFixed(dp)}%`;
}
function fmtX(x: number, dp = 1): string {
  if (!Number.isFinite(x)) return "—";
  return `${x.toFixed(dp)}×`;
}
function fmtTvl(usd?: number | null): string {
  if (usd == null) return "—";
  if (usd >= 1e9) return `$${(usd / 1e9).toFixed(1)}B`;
  if (usd >= 1e6) return `$${(usd / 1e6).toFixed(0)}M`;
  if (usd >= 1e3) return `$${(usd / 1e3).toFixed(0)}K`;
  return `$${Math.round(usd).toLocaleString()}`;
}

interface TokenRef {
  address?: string | null;
  symbol: string;
  decimals: number;
}
interface PoolDepositV3Payload {
  card_id?: string;
  chain: string;
  protocol: string;
  pool_address: string;
  pair: { token0: TokenRef; token1: TokenRef };
  current: {
    price_human: string;
    current_price: number;
    sqrt_price_x96?: string;
    tick?: number;
    tvl_usd?: number | null;
    vol_24h_usd?: number | null;
    fee_tier_bps?: number;
    tick_spacing?: number;
  };
  market: {
    base_apr_pct: number;
    reward_apr_pct: number;
    cdf_30d: number[];
  };
  input_token: TokenRef;
  input_amount_human: string;
  input_amount_usd: number;
  initial_range: { preset: string; lower_pct: number; upper_pct: number };
  initial_steps?: unknown[];
  protocol_url?: string;
  notice?: string;
  finalize_externally?: boolean;
}

const PRESETS = [
  { id: "narrow",   label: "Narrow ±5%",  lower: -5,  upper: 5 },
  { id: "balanced", label: "Balanced ±10%", lower: -10, upper: 10 },
  { id: "wide",     label: "Wide ±25%",   lower: -25, upper: 25 },
  { id: "full",     label: "Full range",  lower: -50, upper: 100 },
];

export function PoolDepositV3Card({ payload }: { payload: PoolDepositV3Payload }) {
  const [lowerPct, setLowerPct] = useState(payload.initial_range?.lower_pct ?? -10);
  const [upperPct, setUpperPct] = useState(payload.initial_range?.upper_pct ?? 10);

  const pCurrent = payload.current.current_price || 1;
  const pLower = pCurrent * (1 + lowerPct / 100);
  const pUpper = pCurrent * (1 + upperPct / 100);

  const liveMetrics = useMemo(() => {
    const cap = capitalEfficiency(pLower, pCurrent, pUpper);
    const prob = inRangeProbability(lowerPct, upperPct, payload.market.cdf_30d || []);
    const apr = aprAtRange(payload.market.base_apr_pct, cap, prob, payload.market.reward_apr_pct);
    return { cap, prob, apr };
  }, [pLower, pCurrent, pUpper, lowerPct, upperPct, payload.market]);

  // Compare table — four canonical preset rows.
  const compareRows = useMemo(() => {
    return PRESETS.map((p) => {
      const pl = pCurrent * (1 + p.lower / 100);
      const pu = pCurrent * (1 + p.upper / 100);
      const cap = capitalEfficiency(pl, pCurrent, pu);
      const prob = inRangeProbability(p.lower, p.upper, payload.market.cdf_30d || []);
      const apr = aprAtRange(payload.market.base_apr_pct, cap, prob, payload.market.reward_apr_pct);
      return { ...p, cap, prob, apr };
    });
  }, [pCurrent, payload.market]);

  // Position preview: split input USD into token0 / token1 by Uniswap V3 ratio.
  const positionPreview = useMemo(() => {
    const inputUsd = payload.input_amount_usd || 0;
    if (pCurrent <= pLower) {
      return { token0Usd: 0, token1Usd: inputUsd, note: "limit order: price below range, all token1" };
    }
    if (pCurrent >= pUpper) {
      return { token0Usd: inputUsd, token1Usd: 0, note: "limit order: price above range, all token0" };
    }
    const sqL = Math.sqrt(pLower);
    const sqC = Math.sqrt(pCurrent);
    const sqU = Math.sqrt(pUpper);
    const ratio0 = (sqU - sqC) / (sqC * sqU);
    const ratio1 = sqC - sqL;
    const w0 = ratio0;
    const w1 = ratio1 / pCurrent;
    const tot = w0 + w1;
    const t0 = inputUsd * (w0 / tot);
    const t1 = inputUsd * (w1 / tot);
    return { token0Usd: t0, token1Usd: t1, note: "" };
  }, [payload.input_amount_usd, pCurrent, pLower, pUpper]);

  function applyPreset(p: typeof PRESETS[number]) {
    setLowerPct(p.lower);
    setUpperPct(p.upper);
  }

  const protoTitle = payload.protocol
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div data-testid="pool-deposit-v3-card" className="relative overflow-hidden rounded-[28px] border border-violet-300/25 bg-[#0c0a1a]/95 shadow-[0_28px_100px_rgba(124,58,237,0.18)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(167,139,250,0.22),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(45,212,191,0.20),transparent_36%)]" />
      <div className="relative border-b border-white/10 p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-violet-300/25 bg-violet-300/10 px-3 py-1 text-[10px] font-black uppercase tracking-[0.22em] text-violet-100">
              <Sparkles className="h-3.5 w-3.5" /> Concentrated liquidity · {payload.chain.toUpperCase()}
            </div>
            <div className="text-2xl font-black tracking-tight text-white">
              {protoTitle} · {payload.pair.token0.symbol}/{payload.pair.token1.symbol}
              {payload.current.fee_tier_bps != null && (
                <span className="ml-2 rounded-md border border-violet-300/30 bg-violet-300/10 px-2 py-0.5 text-xs">{(payload.current.fee_tier_bps / 100).toFixed(2)}%</span>
              )}
            </div>
            <div className="mt-1 text-sm leading-6 text-slate-300">{payload.current.price_human}</div>
          </div>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-[10px] uppercase tracking-[0.18em] text-violet-100/55">TVL</div>
              <div className="text-base font-black text-white">{fmtTvl(payload.current.tvl_usd ?? null)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-[10px] uppercase tracking-[0.18em] text-violet-100/55">24h Vol</div>
              <div className="text-base font-black text-white">{fmtTvl(payload.current.vol_24h_usd ?? null)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-[10px] uppercase tracking-[0.18em] text-violet-100/55">Base APR</div>
              <div className="text-base font-black text-emerald-300">{fmtPct(payload.market.base_apr_pct)}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="relative p-5">
        <div className="flex items-center gap-2 text-sm font-black text-white">
          <Target className="h-4 w-4 text-violet-300" /> Range selector
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => applyPreset(p)}
              className={`rounded-full border px-3 py-1.5 text-xs font-bold uppercase tracking-[0.12em] transition ${
                lowerPct === p.lower && upperPct === p.upper
                  ? "border-violet-300/60 bg-violet-300/20 text-violet-100"
                  : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-300">
            <label className="flex items-center gap-2">
              <span className="text-violet-200/60">Lower</span>
              <input
                type="range"
                min={-50}
                max={0}
                step={1}
                value={lowerPct}
                onChange={(e) => setLowerPct(Number(e.target.value))}
                className="w-40 accent-violet-300"
              />
              <span className="font-mono text-white">{lowerPct}%</span>
            </label>
            <label className="flex items-center gap-2">
              <span className="text-emerald-200/60">Upper</span>
              <input
                type="range"
                min={0}
                max={100}
                step={1}
                value={upperPct}
                onChange={(e) => setUpperPct(Number(e.target.value))}
                className="w-40 accent-emerald-300"
              />
              <span className="font-mono text-white">+{upperPct}%</span>
            </label>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-violet-100/55">Capital efficiency</div>
              <div className="mt-1 flex items-center gap-1 text-lg font-black text-violet-200">
                <Calculator className="h-4 w-4" /> {fmtX(liveMetrics.cap)}
              </div>
              <div className="text-[10px] text-slate-400">vs full range</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-emerald-100/55">In-range prob (30d)</div>
              <div className="mt-1 flex items-center gap-1 text-lg font-black text-emerald-200">
                <Activity className="h-4 w-4" /> {fmtPct(liveMetrics.prob * 100, 0)}
              </div>
              <div className="text-[10px] text-slate-400">empirical from CDF</div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-[10px] uppercase tracking-[0.16em] text-amber-100/55">Expected APR</div>
              <div className="mt-1 flex items-center gap-1 text-lg font-black text-amber-200">
                <TrendingUp className="h-4 w-4" /> {fmtPct(liveMetrics.apr)}
              </div>
              <div className="text-[10px] text-slate-400">@ this range</div>
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-[0.18em] text-slate-300">
              <Layers3 className="h-3.5 w-3.5" /> Range comparison
            </div>
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr><th className="py-1 text-left">Range</th><th className="py-1 text-right">APR</th><th className="py-1 text-right">Eff</th><th className="py-1 text-right">In-range</th></tr>
              </thead>
              <tbody>
                {compareRows.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => applyPreset(r)}
                    className={`cursor-pointer transition hover:bg-white/[0.04] ${lowerPct === r.lower && upperPct === r.upper ? "bg-violet-300/10" : ""}`}
                  >
                    <td className="py-1 font-mono text-slate-200">{r.label}</td>
                    <td className="py-1 text-right font-mono text-emerald-300">{fmtPct(r.apr)}</td>
                    <td className="py-1 text-right font-mono text-violet-300">{fmtX(r.cap)}</td>
                    <td className="py-1 text-right font-mono text-slate-300">{fmtPct(r.prob * 100, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <div className="mb-2 text-xs font-black uppercase tracking-[0.18em] text-slate-300">Position preview</div>
            <div className="text-sm text-slate-200">
              <div>You deposit: <span className="font-bold text-white">{payload.input_amount_human} {payload.input_token.symbol}</span> <span className="text-slate-400">(~${payload.input_amount_usd.toFixed(2)})</span></div>
              <div className="mt-2 text-slate-400">Will become:</div>
              <div className="ml-2">→ <span className="font-bold text-white">${positionPreview.token0Usd.toFixed(2)}</span> in <span className="font-mono">{payload.pair.token0.symbol}</span></div>
              <div className="ml-2">→ <span className="font-bold text-white">${positionPreview.token1Usd.toFixed(2)}</span> in <span className="font-mono">{payload.pair.token1.symbol}</span></div>
              {positionPreview.note && <div className="mt-1 text-[11px] text-amber-300">{positionPreview.note}</div>}
              <div className="mt-3 text-slate-400">Expected daily yield:</div>
              <div className="ml-2 font-bold text-emerald-300">${(payload.input_amount_usd * liveMetrics.apr / 100 / 365).toFixed(3)} / day @ current APR</div>
            </div>
          </div>
        </div>

        {payload.finalize_externally && payload.protocol_url && (
          <a
            href={payload.protocol_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 flex items-center justify-between rounded-2xl border border-emerald-300/40 bg-emerald-300/15 px-4 py-3 transition hover:bg-emerald-300/25"
          >
            <div>
              <div className="text-sm font-black text-emerald-200">Open on {protoTitle} to mint position</div>
              <div className="text-[11px] text-emerald-300/70">
                Direct in-chat mint lands in Phase 4 — for now, finalize on the protocol app with the range you chose.
              </div>
            </div>
            <ExternalLink className="h-4 w-4 text-emerald-200" />
          </a>
        )}

        {payload.notice && (
          <div className="mt-3 flex items-start gap-2 rounded-2xl border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-xs text-amber-100">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" /> <span>{payload.notice}</span>
          </div>
        )}
      </div>
    </div>
  );
}

export type { PoolDepositV3Payload };
