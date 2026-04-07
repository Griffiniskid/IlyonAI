"use client";

import { COMING_SOON } from "@/lib/feature-flags";
import { ComingSoon } from "@/components/coming-soon";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Briefcase, Search, Users, Loader2, AlertCircle, ArrowRight } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

async function fetchEntities() {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/entities`);
  const json = await res.json();
  if (json.status !== "ok") throw new Error("Failed to load entities");
  return json.data.entities ?? [];
}

function truncateAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

export default function EntityListPage() {
  if (COMING_SOON) {
    return <ComingSoon title="Entity Explorer" description="Wallet cluster analysis and entity profiling — coming soon." icon="users" />;
  }
  return <EntityListPageContent />;
}

function EntityListPageContent() {
  const router = useRouter();
  const [entityId, setEntityId] = useState("");
  const { data: entities, isLoading, error } = useQuery({
    queryKey: ["entities"],
    queryFn: fetchEntities,
  });

  const handleSubmit = () => {
    const value = entityId.trim();
    if (!value) return;
    router.push(`/entity/${encodeURIComponent(value)}`);
  };

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Users className="h-8 w-8 text-emerald-500" />
        <h1 className="text-3xl font-bold">Entity Explorer</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Wallet clusters identified through flow analysis and behavioral correlation.
      </p>

      <GlassCard className="mb-8">
        <div className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
          <Briefcase className="h-4 w-4" />
          Look up by wallet or entity ID
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            placeholder="Enter wallet address or entity id"
            value={entityId}
            onChange={(event) => setEntityId(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleSubmit();
              }
            }}
          />
          <Button onClick={handleSubmit}>
            <Search className="mr-2 h-4 w-4" />
            Open Profile
          </Button>
        </div>
      </GlassCard>

      <h2 className="text-lg font-semibold mb-4">Known Entities</h2>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : error ? (
        <GlassCard className="text-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Unable to load entity data.</p>
        </GlassCard>
      ) : !entities || entities.length === 0 ? (
        <GlassCard className="text-center py-12">
          <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">No entities discovered yet.</p>
          <p className="text-xs text-muted-foreground mt-2">
            Entities are built from smart money flow data. As flows are processed, wallet clusters will appear here.
          </p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {entities.map((entity: { id: string; wallet_count: number; reason: string }) => (
            <Link
              key={entity.id}
              href={`/entity/${entity.id}`}
              className="block rounded-xl border border-border/60 bg-card/40 p-4 hover:bg-card/60 transition"
            >
              <div className="flex items-center justify-between">
                <div>
                  <code className="text-sm font-mono">{entity.id}</code>
                  <div className="flex gap-2 mt-2">
                    <Badge variant="outline">{entity.wallet_count} wallets</Badge>
                    <Badge variant="secondary">{entity.reason || "Unknown"}</Badge>
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
