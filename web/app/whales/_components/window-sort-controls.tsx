"use client";

import { Button } from "@/components/ui/button";
import type { WhaleWindow, WhaleSort } from "@/types";

const WINDOWS: WhaleWindow[] = ["1h", "6h", "24h"];
const SORTS: { value: WhaleSort; label: string }[] = [
  { value: "composite", label: "Score" },
  { value: "buyers", label: "Buyers" },
  { value: "new", label: "New" },
];

export function WindowSortControls({
  window,
  sort,
  onWindowChange,
  onSortChange,
}: {
  window: WhaleWindow;
  sort: WhaleSort;
  onWindowChange: (w: WhaleWindow) => void;
  onSortChange: (s: WhaleSort) => void;
}) {
  return (
    <div className="flex flex-wrap gap-4 items-center">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Window:</span>
        {WINDOWS.map((w) => (
          <Button
            key={w}
            size="sm"
            variant={window === w ? "default" : "outline"}
            onClick={() => onWindowChange(w)}
          >
            {w}
          </Button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Sort:</span>
        {SORTS.map((s) => (
          <Button
            key={s.value}
            size="sm"
            variant={sort === s.value ? "default" : "outline"}
            onClick={() => onSortChange(s.value)}
          >
            {s.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
