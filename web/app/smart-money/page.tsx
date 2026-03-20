"use client";

import { useSmartMoneyOverview } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";

function formatUsd(value: number) {
  return `$${value.toLocaleString()}`;
}

export default function SmartMoneyPage() {
  const { data, isLoading, error } = useSmartMoneyOverview();

  if (isLoading) {
    return (
      <section className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-2">Smart Money</h1>
        <p className="text-muted-foreground">Loading smart money...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="container mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-2">Smart Money</h1>
        <p className="text-muted-foreground">Unable to load smart money overview.</p>
      </section>
    );
  }

  const netFlow = data?.net_flow_usd ?? 0;
  const inflow = data?.inflow_usd ?? 0;
  const outflow = data?.outflow_usd ?? 0;
  const updatedAt = data?.updated_at ? new Date(data.updated_at) : null;
  const hasValidUpdatedAt = Boolean(updatedAt && !Number.isNaN(updatedAt.getTime()));

  return (
    <section className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">Smart Money</h1>
      <div className="grid gap-4 md:grid-cols-3 mt-6">
        <GlassCard>
          <p className="text-sm text-muted-foreground mb-1">Net Flow</p>
          <p className="text-2xl font-semibold">{formatUsd(netFlow)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-sm text-muted-foreground mb-1">Inflow</p>
          <p className="text-2xl font-semibold">{formatUsd(inflow)}</p>
        </GlassCard>
        <GlassCard>
          <p className="text-sm text-muted-foreground mb-1">Outflow</p>
          <p className="text-2xl font-semibold">{formatUsd(outflow)}</p>
        </GlassCard>
      </div>
      {hasValidUpdatedAt && updatedAt ? (
        <p className="text-sm text-muted-foreground mt-2">Updated {updatedAt.toLocaleTimeString()}</p>
      ) : null}
    </section>
  );
}
