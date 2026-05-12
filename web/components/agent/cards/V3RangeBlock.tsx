"use client";

import { useMemo, useState } from "react";
import { Activity, Calculator, Target, TrendingUp } from "lucide-react";
import type { V3RangeBlock as V3RangeBlockPayload } from "@/types/agent";

function capitalEfficiency(pLower: number, pCurrent: number, pUpper: number): number {
  if (pCurrent <= pLower || pCurrent >= pUpper) return 1;
  const eff = 1 / (1 - Math.sqrt(pLower / pUpper));
  return Math.max(1, eff);
}

function inRangeProbability(
  lowerPct: number,
  upperPct: number,
  cdfRaw: Array<{ ratio: number; cdf: number } | number> | null | undefined,
): number {
  const points: Array<{ ratio: number; cdf: number }> = [];
  if (Array.isArray(cdfRaw)) {
    for (const entry of cdfRaw) {
      if (entry == null) continue;
      if (typeof entry === "number") {
        points.push({ ratio: NaN, cdf: entry });
      } else {
        points.push({ ratio: entry.ratio, cdf: entry.cdf });
      }
    }
  }
  if (points.length === 0) {
    const total = Math.abs(upperPct - lowerPct);
    if (total >= 50) return 0.99;
    if (total >= 25) return 0.94;
    if (total >= 15) return 0.85;
    if (total >= 10) return 0.78;
    if (total >= 5) return 0.52;
    return 0.25;
  }
  const lowerRatio = 1 + lowerPct / 100;
  const upperRatio = 1 + upperPct / 100;
  const hasRatio = points.every((p) => Number.isFinite(p.ratio));
  if (hasRatio) {
    // Backend ships [{ratio, cdf}] — linear interpolation.
    const sorted = [...points].sort((a, b) => a.ratio - b.ratio);
    const lookup = (r: number): number => {
      if (r <= sorted[0].ratio) return sorted[0].cdf;
      if (r >= sorted[sorted.length - 1].ratio) return sorted[sorted.length - 1].cdf;
      for (let i = 0; i < sorted.length - 1; i++) {
        const a = sorted[i];
        const b = sorted[i + 1];
        if (r >= a.ratio && r <= b.ratio) {
          const t = (r - a.ratio) / (b.ratio - a.ratio || 1);
          return a.cdf + (b.cdf - a.cdf) * t;
        }
      }
      return sorted[sorted.length - 1].cdf;
    };
    return Math.max(0, Math.min(1, lookup(upperRatio) - lookup(lowerRatio)));
  }
  // Fallback: flat cdf[] over [0.5x, 2x] bucket range.
  const ratioToIdx = (r: number) => {
    const t = Math.max(0, Math.min(1, (r - 0.5) / (2.0 - 0.5)));
    return Math.floor(t * (points.length - 1));
  };
  const pLo = points[ratioToIdx(lowerRatio)].cdf ?? 0;
  const pHi = points[ratioToIdx(upperRatio)].cdf ?? 1;
  return Math.max(0, Math.min(1, pHi - pLo));
}

function fmtPct(x: number, dp = 2): string {
  if (!Number.isFinite(x)) return "—";
  return `${x.toFixed(dp)}%`;
}
function fmtX(x: number, dp = 1): string {
  if (!Number.isFinite(x)) return "—";
  return `${x.toFixed(dp)}×`;
}

export function V3RangeBlock({
  block,
  onRangeChange,
}: {
  block: V3RangeBlockPayload;
  onRangeChange?: (lowerPct: number, upperPct: number) => void;
}) {
  const init = block.initial_range || { preset: "balanced", lower_pct: -10, upper_pct: 10 };
  const [lowerPct, setLowerPct] = useState<number>(init.lower_pct ?? -10);
  const [upperPct, setUpperPct] = useState<number>(init.upper_pct ?? 10);

  function applyPreset(p: { lower_pct: number; upper_pct: number; label: string }) {
    setLowerPct(p.lower_pct);
    setUpperPct(p.upper_pct);
    onRangeChange?.(p.lower_pct, p.upper_pct);
  }

  const pCurrent = block.current?.current_price ?? 1;
  const pLower = pCurrent * (1 + lowerPct / 100);
  const pUpper = pCurrent * (1 + upperPct / 100);
  const baseApr = block.market?.base_apr_pct ?? 0;
  const rewardApr = block.market?.reward_apr_pct ?? 0;

  const liveMetrics = useMemo(() => {
    const cap = capitalEfficiency(pLower, pCurrent, pUpper);
    const prob = inRangeProbability(lowerPct, upperPct, block.market?.cdf_30d);
    const apr = baseApr * cap * prob + rewardApr;
    return { cap, prob, apr };
  }, [pLower, pCurrent, pUpper, lowerPct, upperPct, block.market?.cdf_30d, baseApr, rewardApr]);

  const presets = block.range_presets && block.range_presets.length > 0
    ? block.range_presets
    : [
        { label: "Narrow", lower_pct: -5, upper_pct: 5 },
        { label: "Balanced", lower_pct: -10, upper_pct: 10 },
        { label: "Wide", lower_pct: -25, upper_pct: 25 },
        { label: "Full", lower_pct: -50, upper_pct: 100 },
      ];

  const sym0 = block.pair?.token0?.symbol || "TOKEN0";
  const sym1 = block.pair?.token1?.symbol || "TOKEN1";
  const feeBps = block.current?.fee_tier_bps;

  return (
    <div data-testid="v3-range-block" className="rounded-3xl border border-violet-300/25 bg-violet-300/[0.04] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex items-center gap-2 text-sm font-black text-white">
          <Target className="h-4 w-4 text-violet-300" /> V3 Range — {sym0}/{sym1}
          {feeBps != null && (
            <span className="rounded-md border border-violet-300/30 bg-violet-300/10 px-2 py-0.5 text-xs">
              {(feeBps / 100).toFixed(2)}%
            </span>
          )}
        </div>
        {block.current?.price_human && (
          <span className="text-xs text-slate-300">{block.current.price_human}</span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {presets.map((p) => (
          <button
            key={p.label}
            type="button"
            data-testid={`v3-range-preset-${p.label.toLowerCase()}`}
            onClick={() => applyPreset(p)}
            className={`rounded-full border px-3 py-1.5 text-xs font-bold uppercase tracking-[0.12em] transition ${
              lowerPct === p.lower_pct && upperPct === p.upper_pct
                ? "border-violet-300/60 bg-violet-300/20 text-violet-100"
                : "border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
            }`}
          >
            {p.label} ({p.lower_pct >= 0 ? "+" : ""}
            {p.lower_pct}% / +{p.upper_pct}%)
          </button>
        ))}
      </div>

      <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/60 p-4">
        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-300">
          <label className="flex items-center gap-2">
            <span className="text-violet-200/70">Lower</span>
            <input
              type="range"
              min={-50}
              max={0}
              step={1}
              value={lowerPct}
              onChange={(e) => {
                const v = Number(e.target.value);
                setLowerPct(v);
                onRangeChange?.(v, upperPct);
              }}
              className="w-40 accent-violet-300"
            />
            <span className="font-mono text-white">{lowerPct}%</span>
          </label>
          <label className="flex items-center gap-2">
            <span className="text-emerald-200/70">Upper</span>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={upperPct}
              onChange={(e) => {
                const v = Number(e.target.value);
                setUpperPct(v);
                onRangeChange?.(lowerPct, v);
              }}
              className="w-40 accent-emerald-300"
            />
            <span className="font-mono text-white">+{upperPct}%</span>
          </label>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
          <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div className="text-[10px] uppercase tracking-[0.16em] text-violet-100/55">Capital eff</div>
            <div className="mt-1 flex items-center gap-1 text-lg font-black text-violet-200">
              <Calculator className="h-4 w-4" /> {fmtX(liveMetrics.cap)}
            </div>
            <div className="text-[10px] text-slate-400">vs full range</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
            <div className="text-[10px] uppercase tracking-[0.16em] text-emerald-100/55">In-range 30d</div>
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
            <div className="text-[10px] text-slate-400">base × eff × prob</div>
          </div>
        </div>
        <div className="mt-3 text-[11px] text-slate-400">
          Range: <span className="font-mono text-white">{pLower.toExponential(2)}</span> → <span className="font-mono text-white">{pUpper.toExponential(2)}</span>
        </div>
      </div>
    </div>
  );
}
