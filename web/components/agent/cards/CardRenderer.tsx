"use client";
import type { CardFrame } from "@/types/agent";

interface Props { card: CardFrame; }

export function CardRenderer({ card }: Props) {
  const { card_type, payload } = card;
  return (
    <div className="rounded-lg border border-slate-600 p-3 bg-slate-850">
      <div className="text-xs font-mono text-slate-400 mb-2">{card_type}</div>
      <pre className="text-xs text-slate-300 overflow-auto max-h-48">{JSON.stringify(payload, null, 2)}</pre>
    </div>
  );
}
