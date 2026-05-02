"use client";
import React from "react";

interface Props {
  onSelect: (prompt: string) => void;
  disabled: boolean;
}

const PRESETS: { label: string; prompt: string }[] = [
  { label: "Conservative", prompt: "low-risk only — show me the safest yield options" },
  { label: "Balanced", prompt: "balanced risk — diversified yield with moderate safety" },
  { label: "Aggressive", prompt: "aggressive — show high-yield options I should consider" },
  { label: "Maximize APY", prompt: "maximize APY — what's the highest yield I can find" },
];

export function ChipPresets({ onSelect, disabled }: Props) {
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {PRESETS.map((p) => (
        <button
          key={p.label}
          type="button"
          onClick={() => onSelect(p.prompt)}
          disabled={disabled}
          className="rounded-full border border-emerald-500/30 bg-emerald-500/5 px-3 py-1 text-xs text-emerald-300 hover:bg-emerald-500/15 disabled:opacity-40"
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
