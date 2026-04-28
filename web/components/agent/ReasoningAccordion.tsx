"use client";
import { useState } from "react";
import { Brain, ChevronDown, ChevronUp } from "lucide-react";

interface Props {
  steps: number;
  time?: string;
  expanded?: boolean;
  lines?: string[];
}

export function ReasoningAccordion({ steps, time, expanded = false, lines }: Props) {
  const [open, setOpen] = useState(expanded);
  return (
    <div data-testid="reasoning-accordion" className="my-2 ml-11 max-w-2xl">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="block w-full rounded-xl border border-purple-500/20 bg-purple-500/5 px-4 py-2.5 text-left text-sm transition hover:bg-purple-500/10"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-purple-300">
            <Brain className="h-4 w-4" />
            <span>Agent Reasoning — {steps} step{steps === 1 ? "" : "s"}</span>
          </div>
          {open ? (
            <ChevronUp className="h-4 w-4 text-purple-400/70" />
          ) : (
            <ChevronDown className="h-4 w-4 text-purple-400/70" />
          )}
        </div>
        {open && lines && lines.length > 0 && (
          <ol className="mt-3 space-y-1.5 border-t border-purple-500/15 pt-3 text-[12px] text-foreground/80">
            {lines.map((line, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="shrink-0 font-mono text-purple-300/80">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-foreground/75">{line}</span>
              </li>
            ))}
          </ol>
        )}
      </button>
      {time && <div className="mt-1 ml-1 text-[11px] text-muted-foreground/70">{time}</div>}
    </div>
  );
}
