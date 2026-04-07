import { COMING_SOON } from "@/lib/feature-flags";
import { ComingSoon } from "@/components/coming-soon";
import { getRektIncidents } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { GlassCard } from "@/components/ui/card";
import { Flame, AlertTriangle } from "lucide-react";
import RektIncidentList from "./_components/rekt-incident-list";

export default async function RektPage() {
  if (COMING_SOON) {
    return <ComingSoon title="REKT Database" description="Hacks, exploits, and security incidents across DeFi protocols — coming soon." icon="flame" />;
  }

  let incidents: Awaited<ReturnType<typeof getRektIncidents>>["incidents"] = [];
  let fetchedAt = "";
  let freshness = "unknown";
  try {
    const data = await getRektIncidents({ limit: 50 });
    incidents = data.incidents;
    fetchedAt = new Date().toLocaleString();
    freshness = data.meta?.freshness ?? "unknown";
  } catch {
    incidents = [];
    fetchedAt = "Failed to fetch";
  }

  const chains = Array.from(new Set(incidents.flatMap((i) => i.chains))).slice(0, 8);
  const attackTypes = Array.from(new Set(incidents.map((i) => i.attack_type))).slice(0, 8);

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <Flame className="h-8 w-8 text-red-500" />
        <h1 className="text-3xl font-bold">REKT Database</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Hacks, exploits, and security incidents across DeFi protocols. Click any incident for details.
      </p>

      {freshness === "seed_only" && (
        <div className="text-xs text-amber-400 mb-4 flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          Live data unavailable — showing cached incident database
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-6">
        {chains.map((chain) => (
          <Badge key={chain} variant="outline">
            {chain}
          </Badge>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 mb-8">
        {attackTypes.map((type) => (
          <Badge key={type} variant="secondary">
            {type}
          </Badge>
        ))}
      </div>

      {incidents.length === 0 ? (
        <GlassCard className="text-center py-12">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">No incidents found.</p>
        </GlassCard>
      ) : (
        <RektIncidentList incidents={incidents} fetchedAt={fetchedAt} />
      )}
    </div>
  );
}
