"use client";

import { useState } from "react";
import type { PortfolioChainMatrixResponse } from "@/types";
import { Badge } from "@/components/ui/badge";

interface RiskBreakdownProps {
  matrix: PortfolioChainMatrixResponse | null | undefined;
}

export function RiskBreakdown({ matrix }: RiskBreakdownProps) {
  const [expanded, setExpanded] = useState(false);

  const available = Object.entries(matrix?.chains ?? {}).flatMap(([chain, capabilityMap]) =>
    (matrix?.capabilities ?? [])
      .filter((capability) => capabilityMap[capability]?.state === "available")
      .map((capability) => ({ chain, capability }))
  );

  const degraded = Object.entries(matrix?.chains ?? {}).flatMap(([chain, capabilityMap]) =>
    (matrix?.capabilities ?? [])
      .map((capability) => {
        const cell = capabilityMap[capability];
        if (!cell || cell.state !== "degraded") return null;
        return { chain, capability, reason: cell.reason ?? "unknown" };
      })
      .filter((item): item is { chain: string; capability: string; reason: string } => item !== null)
  );

  // Deduplicate degraded reasons
  const uniqueReasons = Array.from(new Set(degraded.map((d) => d.reason)));

  return (
    <div className="space-y-3">
      {available.length > 0 && (
        <div>
          <p className="text-sm font-medium text-emerald-400 mb-1">
            {available.length} capabilities available
          </p>
          <div className="flex flex-wrap gap-1">
            {available.map((item) => (
              <Badge key={`${item.chain}-${item.capability}`} variant="outline" className="text-xs text-emerald-400 border-emerald-500/40">
                {item.chain}: {item.capability.replaceAll("_", " ")}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {degraded.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm font-medium text-yellow-400 hover:text-yellow-300 transition cursor-pointer"
          >
            {degraded.length} capabilities degraded {expanded ? "\u25be" : "\u25b8"}
          </button>
          {expanded && (
            <div className="mt-2 space-y-1 pl-2 border-l-2 border-yellow-500/30">
              {uniqueReasons.map((reason) => (
                <p key={reason} className="text-xs text-muted-foreground">
                  &bull; {reason}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {available.length === 0 && degraded.length === 0 && (
        <p className="text-sm text-muted-foreground">No capability data available.</p>
      )}
    </div>
  );
}
