"use client";

import { COMING_SOON } from "@/lib/feature-flags";
import { ComingSoon } from "@/components/coming-soon";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Briefcase,
  Search,
  Users,
  Loader2,
  AlertCircle,
  ArrowRight,
  Globe,
  Tag,
  AlertTriangle,
  BarChart3,
  Link2,
} from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import * as api from "@/lib/api";

async function fetchEntities() {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/entities`);
  const json = await res.json();
  if (json.status !== "ok") throw new Error("Failed to load entities");
  return json.data.entities ?? [];
}

function truncateAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

const EVM_CHAINS = ["ethereum", "base", "arbitrum", "bsc", "polygon", "optimism", "avalanche"];

export default function EntityListPage() {
  if (COMING_SOON) {
    return <ComingSoon title="Entity Explorer" description="Wallet cluster analysis and entity profiling — coming soon." icon="users" />;
  }
  return <EntityListPageContent />;
}

function EntityListPageContent() {
  const router = useRouter();
  const [entityId, setEntityId] = useState("");
  const [resolveWallet, setResolveWallet] = useState("");
  const [resolveChains, setResolveChains] = useState<string[]>(["ethereum", "base", "arbitrum"]);

  const { data: entities, isLoading, error } = useQuery({
    queryKey: ["entities"],
    queryFn: fetchEntities,
  });

  const { data: stats } = useQuery({
    queryKey: ["entity-stats"],
    queryFn: api.getEntityStats,
  });

  const resolveMutation = useMutation({
    mutationFn: (params: { wallet: string; chains: string[] }) =>
      api.resolveEntity(params.wallet, params.chains),
    onSuccess: (data) => {
      router.push(`/entity/${encodeURIComponent(data.entity_id)}`);
    },
  });

  const handleSubmit = () => {
    const value = entityId.trim();
    if (!value) return;
    router.push(`/entity/${encodeURIComponent(value)}`);
  };

  const handleResolve = () => {
    const value = resolveWallet.trim();
    if (!value) return;
    resolveMutation.mutate({ wallet: value, chains: resolveChains });
  };

  const toggleChain = (chain: string) => {
    setResolveChains((prev) =>
      prev.includes(chain) ? prev.filter((c) => c !== chain) : [...prev, chain]
    );
  };

  return (
    <section className="container mx-auto max-w-6xl px-4 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Users className="h-8 w-8 text-emerald-500" />
        <h1 className="text-3xl font-bold">Entity Explorer</h1>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Cross-chain wallet clustering, entity resolution, and behavioral profiling.
      </p>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-8">
          {[
            { label: "Entities", value: stats.total_entities, icon: Users },
            { label: "Wallets", value: stats.total_wallets, icon: Briefcase },
            { label: "Labeled", value: stats.entities_with_labels, icon: Tag },
            { label: "Multi-Wallet", value: stats.entities_with_multiple_wallets, icon: Link2 },
            { label: "Multi-Chain", value: stats.multi_chain_entities, icon: Globe },
          ].map(({ label, value, icon: Icon }) => (
            <GlassCard key={label} className="text-center py-3">
              <Icon className="h-4 w-4 mx-auto mb-1 text-emerald-400" />
              <div className="text-xl font-bold">{value}</div>
              <div className="text-xs text-muted-foreground">{label}</div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* Lookup */}
      <GlassCard className="mb-6">
        <div className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
          <Search className="h-4 w-4" />
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

      {/* Cross-chain resolve */}
      <GlassCard className="mb-8">
        <div className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
          <Globe className="h-4 w-4" />
          Cross-Chain Entity Resolution
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          Paste any EVM wallet address to resolve it across multiple chains. If the same address has activity on different chains, they are linked into one entity.
        </p>
        <div className="flex flex-col gap-3 sm:flex-row mb-3">
          <Input
            placeholder="0x... EVM wallet address"
            value={resolveWallet}
            onChange={(e) => setResolveWallet(e.target.value)}
            className="font-mono"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleResolve();
              }
            }}
          />
          <Button
            onClick={handleResolve}
            disabled={resolveMutation.isPending}
            className="bg-emerald-600 hover:bg-emerald-500 text-black font-semibold shrink-0"
          >
            {resolveMutation.isPending ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Resolving...</>
            ) : (
              <><Link2 className="h-4 w-4 mr-2" /> Resolve Entity</>
            )}
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {EVM_CHAINS.map((chain) => (
            <Button
              key={chain}
              variant={resolveChains.includes(chain) ? "default" : "outline"}
              size="sm"
              className={resolveChains.includes(chain) ? "bg-emerald-600 hover:bg-emerald-500 capitalize" : "capitalize"}
              onClick={() => toggleChain(chain)}
            >
              {chain}
            </Button>
          ))}
        </div>
        {resolveMutation.isError && (
          <div className="flex items-center gap-2 text-red-400 text-sm mt-3">
            <AlertTriangle className="h-4 w-4" />
            <span>{resolveMutation.error instanceof Error ? resolveMutation.error.message : "Resolution failed"}</span>
          </div>
        )}
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
            Use the resolve tool above to start building entity clusters, or entities will be created automatically from smart money flow data.
          </p>
        </GlassCard>
      ) : (
        <div className="space-y-3">
          {entities.map((entity: any) => (
            <Link
              key={entity.id}
              href={`/entity/${entity.id}`}
              className="block rounded-xl border border-border/60 bg-card/40 p-4 hover:bg-card/60 transition"
            >
              <div className="flex items-center justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <code className="text-sm font-mono truncate">{entity.id}</code>
                    {entity.label && (
                      <Badge variant="secondary">{entity.label}</Badge>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge variant="outline">{entity.wallet_count} wallets</Badge>
                    {entity.risk_level && (
                      <Badge variant={entity.risk_level === "HIGH" || entity.risk_level === "CRITICAL" ? "destructive" : "outline"}>
                        {entity.risk_level}
                      </Badge>
                    )}
                    {entity.chains?.length > 0 && (
                      <Badge variant="outline" className="capitalize">
                        <Globe className="h-3 w-3 mr-1" />
                        {entity.chains.join(", ")}
                      </Badge>
                    )}
                    {entity.total_volume_usd > 0 && (
                      <Badge variant="outline">
                        <BarChart3 className="h-3 w-3 mr-1" />
                        ${entity.total_volume_usd >= 1_000_000
                          ? `${(entity.total_volume_usd / 1_000_000).toFixed(1)}M`
                          : entity.total_volume_usd >= 1_000
                          ? `${(entity.total_volume_usd / 1_000).toFixed(0)}K`
                          : entity.total_volume_usd.toFixed(0)}
                      </Badge>
                    )}
                    {entity.tags?.length > 0 && entity.tags.map((t: string) => (
                      <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
                    ))}
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-muted-foreground shrink-0 ml-2" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
