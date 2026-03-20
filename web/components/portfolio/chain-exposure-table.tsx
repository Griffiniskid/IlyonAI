import type { PortfolioChainMatrixResponse } from "@/types";

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

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-2 pr-4 font-medium">Chain</th>
            <th className="py-2 pr-4 font-medium">Available</th>
            <th className="py-2 font-medium">Degraded</th>
          </tr>
        </thead>
        <tbody>
          {chains.map(([chain, chainCapabilities]) => {
            const available = capabilities.filter(
              (capability) => chainCapabilities[capability]?.state === "available"
            ).length;
            const degraded = capabilities.length - available;

            return (
              <tr key={chain} className="border-b border-border/60 last:border-b-0">
                <td className="py-3 pr-4">{toTitleCase(chain)}</td>
                <td className="py-3 pr-4 font-mono">{available}</td>
                <td className="py-3 font-mono">{degraded}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
