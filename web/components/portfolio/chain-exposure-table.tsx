import type { PortfolioChainMatrixResponse } from "@/types";
import { Badge } from "@/components/ui/badge";

interface ChainExposureTableProps {
  matrix: PortfolioChainMatrixResponse | null | undefined;
}

function toTitleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function ChainExposureTable({ matrix }: ChainExposureTableProps) {
  const chains = Object.entries(matrix?.chains ?? {});
  const capabilities = matrix?.capabilities ?? [];

  if (chains.length === 0) {
    return <p className="text-sm text-muted-foreground">Chain exposure is unavailable.</p>;
  }

  const totalChains = chains.length;
  const activeChains = chains.filter(([, caps]) =>
    capabilities.some((c) => caps[c]?.state === "available")
  ).length;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Badge variant="outline" className="text-emerald-400 border-emerald-500/40">
          {activeChains} of {totalChains} chains active
        </Badge>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="py-2 pr-4 font-medium">Chain</th>
              <th className="py-2 pr-4 font-medium">Status</th>
              <th className="py-2 font-medium">Capabilities</th>
            </tr>
          </thead>
          <tbody>
            {chains.map(([chain, chainCapabilities]) => {
              const available = capabilities.filter(
                (capability) => chainCapabilities[capability]?.state === "available"
              );
              const degradedCount = capabilities.length - available.length;

              return (
                <tr key={chain} className="border-b border-border/60 last:border-b-0">
                  <td className="py-3 pr-4 font-medium">{toTitleCase(chain)}</td>
                  <td className="py-3 pr-4">
                    {available.length > 0 ? (
                      <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/40">Active</Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs text-yellow-400 border-yellow-500/40">Limited</Badge>
                    )}
                  </td>
                  <td className="py-3 text-muted-foreground text-xs">
                    {available.length > 0 && (
                      <span className="text-emerald-400">{available.map((c) => c.replaceAll("_", " ")).join(", ")}</span>
                    )}
                    {degradedCount > 0 && (
                      <span className="text-yellow-400 ml-2">({degradedCount} pending)</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
