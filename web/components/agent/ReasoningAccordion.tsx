"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

interface Props {
  steps: string[];
  time: number;
  lines: number;
}

export function ReasoningAccordion({ steps, time, lines }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 p-3 text-xs text-slate-400 hover:bg-slate-800/50">
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span>Reasoning ({lines} steps)</span>
      </button>
      {open && (
        <div className="p-3 space-y-1 text-xs text-slate-500 font-mono bg-slate-900">
          {steps.map((s, i) => <div key={i}>{s}</div>)}
        </div>
      )}
    </div>
  );
}
