"use client";
import React from "react";

interface SentinelBlock {
  sentinel: number;
  safety: number;
  durability: number;
  exit: number;
  confidence: number;
  risk_level: string;
  strategy_fit: string;
  flags: string[];
}

interface Props {
  sentinel: SentinelBlock;
}

export function SentinelBreakdownCard({ sentinel }: Props) {
  const dims = [
    { name: "Safety", value: sentinel.safety, weight: "0.40" },
    { name: "Durability", value: sentinel.durability, weight: "0.25" },
    { name: "Exit", value: sentinel.exit, weight: "0.20" },
    { name: "Confidence", value: sentinel.confidence, weight: "0.15" },
  ];
  return (
    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
      <div className="flex items-baseline justify-between">
        <h4 className="text-sm font-semibold text-emerald-300">Sentinel breakdown</h4>
        <span className="text-2xl font-bold">{sentinel.sentinel}</span>
      </div>
      <ul className="mt-3 space-y-2 text-sm">
        {dims.map((d) => (
          <li key={d.name} className="flex justify-between">
            <span>
              <span className="text-foreground/80">{d.name}</span>
              <span className="ml-2 text-xs text-muted-foreground">×{d.weight}</span>
            </span>
            <span>{d.value}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">
        sentinel = 0.40·safety + 0.25·durability + 0.20·exit + 0.15·confidence
      </p>
      {sentinel.flags?.length > 0 && (
        <p className="mt-2 text-xs text-amber-300">Flags: {sentinel.flags.join(", ")}</p>
      )}
    </div>
  );
}
