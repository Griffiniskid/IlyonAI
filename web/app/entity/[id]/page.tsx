"use client";

import { COMING_SOON } from "@/lib/feature-flags";
import { ComingSoon } from "@/components/coming-soon";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Loader2,
  AlertCircle,
  Users,
  ArrowRight,
  Copy,
  Globe,
  Tag,
  BarChart3,
  AlertTriangle,
  Plus,
  ExternalLink,
} from "lucide-react";
import { useState } from "react";
import * as api from "@/lib/api";

async function fetchEntity(id: string) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/entities/${id}`);
  const json = await res.json();
  if (json.status !== "ok") throw new Error(json.errors?.[0]?.message ?? "Entity not found");
  return json.data;
}

function truncateAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

function walletExplorerUrl(wallet: string) {
  if (wallet.startsWith("0x") && wallet.length === 42) {
    return `https://etherscan.io/address/${wallet}`;
  }
  return `https://solscan.io/account/${wallet}`;
}

export default function EntityPage() {
  if (COMING_SOON) {
    return <ComingSoon title="Entity Explorer" description="Wallet cluster analysis and entity profiling — coming soon." icon="users" />;
  }
  return <EntityPageContent />;
}

function EntityPageContent() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : params.id ?? "";
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id],
    queryFn: () => fetchEntity(id),
    enabled: !!id,
  });
  const [copied, setCopied] = useState<string | null>(null);
  const [newWallet, setNewWallet] = useState("");
  const [showAddWallet, setShowAddWallet] = useState(false);

  const addWalletMutation = useMutation({
    mutationFn: (wallet: string) => api.addWalletToEntity(id, wallet, "Added via UI"),
    onSuccess: () => {
      setNewWallet("");
      setShowAddWallet(false);
      queryClient.invalidateQueries({ queryKey: ["entity", id] });
    },
  });

  const handleCopy = async (addr: string) => {
    await navigator.clipboard.writeText(addr);
    setCopied(addr);
    setTimeout(() => setCopied(null), 2000);
  };

  const handleAddWallet = () => {
    const value = newWallet.trim();
    if (!value) return;
    addWalletMutation.mutate(value);
  };

  return (
    <section className="container mx-auto max-w-4xl px-4 py-8">
      <Link href="/entity" className="text-sm text-muted-foreground hover:text-foreground mb-2 inline-block">
        &larr; Back to Entities
      </Link>
      <div className="flex items-center gap-3 mt-2 mb-6">
        <Users className="h-8 w-8 text-emerald-500" />
        <h1 className="text-3xl font-bold">Entity Profile</h1>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
        </div>
      ) : error ? (
        <GlassCard className="text-center py-12">
          <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-sm text-muted-foreground">Entity not found or unavailable.</p>
        </GlassCard>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Entity ID</p>
              <code className="text-xs font-mono break-all">{data.id}</code>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Linked Wallets</p>
              <p className="text-2xl font-semibold">{data.wallet_count}</p>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Label</p>
              {data.label ? (
                <Badge variant="secondary">{data.label}</Badge>
              ) : (
                <span className="text-sm text-muted-foreground">Unlabeled</span>
              )}
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Risk Level</p>
              {data.risk_level ? (
                <Badge variant={data.risk_level === "HIGH" || data.risk_level === "CRITICAL" ? "destructive" : "outline"}>
                  {data.risk_level}
                </Badge>
              ) : (
                <span className="text-sm text-muted-foreground">Unknown</span>
              )}
            </GlassCard>
          </div>

          {/* Metadata row */}
          <div className="flex flex-wrap gap-3 mb-6">
            {data.reason && (
              <Badge variant="outline">{data.reason}</Badge>
            )}
            {data.chains?.length > 0 && (
              <Badge variant="outline" className="capitalize">
                <Globe className="h-3 w-3 mr-1" />
                {data.chains.join(", ")}
              </Badge>
            )}
            {data.total_volume_usd > 0 && (
              <Badge variant="outline">
                <BarChart3 className="h-3 w-3 mr-1" />
                ${data.total_volume_usd >= 1_000_000
                  ? `${(data.total_volume_usd / 1_000_000).toFixed(1)}M`
                  : data.total_volume_usd >= 1_000
                  ? `${(data.total_volume_usd / 1_000).toFixed(0)}K`
                  : data.total_volume_usd.toFixed(0)}
              </Badge>
            )}
            {data.tags?.length > 0 && data.tags.map((t: string) => (
              <Badge key={t} variant="secondary">
                <Tag className="h-3 w-3 mr-1" />
                {t}
              </Badge>
            ))}
          </div>

          {/* Wallets */}
          <GlassCard className="p-4 mb-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Associated Wallets</h2>
              <Button variant="ghost" size="sm" onClick={() => setShowAddWallet(!showAddWallet)}>
                <Plus className="h-4 w-4 mr-1" />
                Add Wallet
              </Button>
            </div>

            {showAddWallet && (
              <div className="flex flex-col gap-2 sm:flex-row mb-4 p-3 rounded-lg border border-border/40 bg-black/10">
                <Input
                  placeholder="Wallet address to link"
                  value={newWallet}
                  onChange={(e) => setNewWallet(e.target.value)}
                  className="font-mono text-sm"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); handleAddWallet(); }
                  }}
                />
                <Button
                  size="sm"
                  onClick={handleAddWallet}
                  disabled={addWalletMutation.isPending}
                  className="shrink-0"
                >
                  {addWalletMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Link"}
                </Button>
              </div>
            )}
            {addWalletMutation.isError && (
              <div className="flex items-center gap-2 text-red-400 text-sm mb-3">
                <AlertTriangle className="h-4 w-4" />
                <span>{addWalletMutation.error instanceof Error ? addWalletMutation.error.message : "Failed to add wallet"}</span>
              </div>
            )}

            <div className="space-y-2">
              {(data.wallets ?? []).map((wallet: string) => (
                <div key={wallet} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <a
                      href={walletExplorerUrl(wallet)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-primary hover:underline truncate"
                    >
                      {truncateAddress(wallet)}
                    </a>
                    <a
                      href={walletExplorerUrl(wallet)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => handleCopy(wallet)}>
                    <Copy className="h-3 w-3 mr-1" />
                    {copied === wallet ? "Copied" : "Copy"}
                  </Button>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="flex gap-3">
            <Button asChild variant="outline" size="sm">
              <Link href="/smart-money">
                Smart Money Hub
                <ArrowRight className="h-4 w-4 ml-2" />
              </Link>
            </Button>
          </div>
        </>
      ) : null}
    </section>
  );
}
