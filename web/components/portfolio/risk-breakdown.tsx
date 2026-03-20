import type { PortfolioChainMatrixResponse } from "@/types";

interface RiskBreakdownProps {
  matrix: PortfolioChainMatrixResponse | null | undefined;
}

export function RiskBreakdown({ matrix }: RiskBreakdownProps) {
  const degraded = Object.entries(matrix?.chains ?? {}).flatMap(([chain, capabilityMap]) =>
    (matrix?.capabilities ?? [])
      .map((capability) => {
        const cell = capabilityMap[capability];
        if (!cell) {
          return {
            chain,
            capability,
            reason: "missing capability data",
          };
        }
        if (cell.state !== "degraded") {
          return null;
        }
        return {
          chain,
          capability,
          reason: cell.reason ?? "unknown",
        };
      })
      .filter((item): item is { chain: string; capability: string; reason: string } => item !== null)
  );

  if (degraded.length === 0) {
    return <p className="text-sm text-muted-foreground">No degraded capabilities reported.</p>;
  }

  return (
    <div className="space-y-2">
      {degraded.map((item) => (
        <p key={`${item.chain}-${item.capability}`} className="text-sm text-yellow-300">
          Degraded capability: {item.capability.replaceAll("_", " ")} - {item.reason}
        </p>
      ))}
    </div>
  );
}
