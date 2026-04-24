"use client";
import {
  Activity,
  Layers,
  RefreshCcw,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

export interface QuickChip {
  label: string;
  icon: React.ReactNode;
  prompt: string;
}

export const DEFAULT_CHIPS: QuickChip[] = [
  { label: "Rebalance now", icon: <Layers className="h-3.5 w-3.5 text-emerald-400" />, prompt: "Rebalance this allocation now." },
  { label: "Low-risk only", icon: <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />, prompt: "Re-run the allocation with a conservative risk budget — only low-risk pools." },
  { label: "Maximize APY", icon: <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />, prompt: "Re-run the allocation aggressively — maximize blended APY even if Sentinel drops." },
  { label: "Explain Sentinel", icon: <Activity className="h-3.5 w-3.5 text-emerald-400" />, prompt: "Explain how Sentinel scoring works and what Safety, Yield durability, Exit liquidity, and Confidence each measure." },
  { label: "Skip Pendle", icon: <RefreshCcw className="h-3.5 w-3.5 text-emerald-400" />, prompt: "Re-run the allocation, but skip any Pendle PT positions." },
];

export function QuickChips({
  onSelect,
  disabled = false,
  chips = DEFAULT_CHIPS,
}: {
  onSelect: (prompt: string) => void;
  disabled?: boolean;
  chips?: QuickChip[];
}) {
  return (
    <div data-testid="quick-chips" className="mb-3 flex gap-2 overflow-x-auto">
      {chips.map((chip) => (
        <button
          key={chip.label}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(chip.prompt)}
          className="flex shrink-0 items-center gap-2 rounded-full border border-white/10 bg-card/50 px-4 py-2 text-sm text-foreground/80 transition enabled:hover:border-emerald-500/30 enabled:hover:bg-emerald-500/5 disabled:opacity-50"
        >
          {chip.icon}
          <span>{chip.label}</span>
        </button>
      ))}
    </div>
  );
}
