import Link from "next/link";
import { getRektIncident } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/card";
import { formatUSD } from "@/lib/utils";
import { Flame, AlertTriangle, Clock, ExternalLink, ArrowLeft, Shield, ShieldOff, Coins } from "lucide-react";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-500/20 text-red-400 border-red-500/40",
  HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/40",
  MEDIUM: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40",
  LOW: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
};

export default async function RektIncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const incident = await getRektIncident(id);

  if (!incident) {
    return (
      <div className="container mx-auto max-w-6xl px-4 py-8">
        <GlassCard className="text-center py-12">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h1 className="text-2xl font-bold mb-2">Incident Not Found</h1>
          <p className="text-muted-foreground mb-4">The requested incident could not be found.</p>
          <Button asChild variant="outline">
            <Link href="/rekt">Back to REKT Database</Link>
          </Button>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <Link href="/rekt" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-4">
        <ArrowLeft className="h-4 w-4" />
        Back to REKT Database
      </Link>

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Flame className="h-8 w-8 text-red-500" />
        <h1 className="text-3xl font-bold">{incident.name}</h1>
      </div>

      <div className="flex flex-wrap gap-2 mb-6">
        <Badge className={SEVERITY_COLORS[incident.severity] ?? ""}>{incident.severity}</Badge>
        <Badge variant="outline">{incident.attack_type}</Badge>
        {incident.funds_recovered ? (
          <Badge variant="outline" className="text-emerald-400 border-emerald-500/40 bg-emerald-500/10">
            <Shield className="h-3 w-3 mr-1" />
            Funds Recovered
          </Badge>
        ) : (
          <Badge variant="outline" className="text-red-400 border-red-500/40 bg-red-500/10">
            <ShieldOff className="h-3 w-3 mr-1" />
            Funds Not Recovered
          </Badge>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3 mb-8">
        <GlassCard className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Amount Lost</p>
          <p className="text-2xl font-mono font-bold text-red-400">{formatUSD(incident.amount_usd)}</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Date</p>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-muted-foreground" />
            <p className="text-lg font-semibold">{new Date(incident.date).toLocaleDateString()}</p>
          </div>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Protocol</p>
          <p className="text-lg font-semibold">{incident.protocol}</p>
        </GlassCard>
      </div>

      <GlassCard className="p-4 mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Affected Chains</p>
        <div className="flex flex-wrap gap-2">
          {incident.chains.map((chain) => (
            <Badge key={chain} variant="secondary">
              {chain}
            </Badge>
          ))}
        </div>
      </GlassCard>

      <GlassCard className="p-6 mb-6">
        <h2 className="font-semibold mb-3">Description</h2>
        <p className="text-muted-foreground leading-relaxed">{incident.description}</p>
      </GlassCard>

      <div className="flex flex-wrap gap-3">
        {incident.post_mortem_url ? (
          <Button asChild>
            <a href={incident.post_mortem_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="h-4 w-4 mr-2" />
              View Post-Mortem &rarr;
            </a>
          </Button>
        ) : null}
        <Button asChild variant="outline">
          <Link href="/rekt">View All Incidents</Link>
        </Button>
      </div>
    </div>
  );
}
