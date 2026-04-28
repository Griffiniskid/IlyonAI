"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/card";
import { AlertTriangle, ArrowRight, Clock } from "lucide-react";
import { formatUSD, formatCompact } from "@/lib/utils";
import type { RektIncident } from "@/types";

type SortMode = "amount" | "date" | "severity";

const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
};

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-500/20 text-red-400 border-red-500/40",
  HIGH: "bg-orange-500/20 text-orange-400 border-orange-500/40",
  MEDIUM: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40",
  LOW: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
};

const SORT_LABELS: Record<SortMode, string> = {
  amount: "Largest First",
  date: "Newest First",
  severity: "Severity",
};

interface RektIncidentListProps {
  incidents: RektIncident[];
  fetchedAt: string;
}

export default function RektIncidentList({ incidents, fetchedAt }: RektIncidentListProps) {
  const [sortMode, setSortMode] = useState<SortMode>("amount");

  const totalCount = incidents.length;
  const totalStolen = incidents.reduce((sum, i) => sum + i.amount_usd, 0);

  const sorted = [...incidents].sort((a, b) => {
    if (sortMode === "amount") {
      return b.amount_usd - a.amount_usd;
    }
    if (sortMode === "date") {
      return new Date(b.date).getTime() - new Date(a.date).getTime();
    }
    // severity
    return (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4);
  });

  return (
    <>
      {/* Stats header */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 mb-6">
        <GlassCard className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Total Incidents</p>
          <p className="text-2xl font-mono font-bold">{totalCount}</p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Total Stolen</p>
          <p className="text-2xl font-mono font-bold text-red-400">{formatCompact(totalStolen)}</p>
        </GlassCard>
        <GlassCard className="p-4 sm:col-span-2 lg:col-span-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Last Refreshed</p>
          <p className="text-sm font-semibold">{fetchedAt}</p>
        </GlassCard>
      </div>

      {/* Sort controls */}
      <div className="flex flex-wrap items-center gap-2 mb-6">
        <span className="text-sm text-muted-foreground mr-1">Sort by:</span>
        {(Object.keys(SORT_LABELS) as SortMode[]).map((mode) => (
          <Button
            key={mode}
            variant={sortMode === mode ? "default" : "outline"}
            size="sm"
            onClick={() => setSortMode(mode)}
          >
            {SORT_LABELS[mode]}
          </Button>
        ))}
      </div>

      {/* Incident list */}
      {sorted.length === 0 ? (
        <GlassCard className="text-center py-12">
          <AlertTriangle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">No incidents found.</p>
        </GlassCard>
      ) : (
        <div className="space-y-4">
          {sorted.map((incident) => (
            <Link
              key={incident.id}
              href={`/rekt/${incident.id}`}
              className="block rounded-xl border border-border/60 bg-card/40 p-4 hover:bg-card/60 transition"
            >
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <Badge className={SEVERITY_COLORS[incident.severity] ?? ""}>{incident.severity}</Badge>
                    <Badge variant="outline">{incident.attack_type}</Badge>
                    {incident.funds_recovered ? (
                      <Badge variant="outline" className="text-emerald-400">
                        Recovered
                      </Badge>
                    ) : null}
                  </div>
                  <div className="font-semibold">{incident.name}</div>
                  <div className="text-sm text-muted-foreground">{incident.protocol}</div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {incident.chains.slice(0, 3).map((chain) => (
                      <Badge key={chain} variant="secondary" className="text-xs">
                        {chain}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <div className="text-right">
                    <div className="text-lg font-mono font-bold text-red-400">
                      {formatUSD(incident.amount_usd)}
                    </div>
                    <div className="text-xs text-muted-foreground flex items-center gap-1 justify-end">
                      <Clock className="h-3 w-3" />
                      {new Date(incident.date).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">View details</span>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
