"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, AlertCircle, Users, ArrowRight, Copy } from "lucide-react";
import { useState } from "react";

async function fetchEntity(id: string) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/entities/${id}`);
  const json = await res.json();
  if (json.status !== "ok") throw new Error(json.errors?.[0]?.message ?? "Entity not found");
  return json.data;
}

function truncateAddress(addr: string) {
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

export default function EntityPage() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : params.id ?? "";
  const { data, isLoading, error } = useQuery({
    queryKey: ["entity", id],
    queryFn: () => fetchEntity(id),
    enabled: !!id,
  });
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = async (addr: string) => {
    await navigator.clipboard.writeText(addr);
    setCopied(addr);
    setTimeout(() => setCopied(null), 2000);
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
          <div className="grid gap-4 md:grid-cols-3 mb-8">
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Entity ID</p>
              <code className="text-sm font-mono">{data.id}</code>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Linked Wallets</p>
              <p className="text-2xl font-semibold">{data.wallet_count}</p>
            </GlassCard>
            <GlassCard className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">Link Reason</p>
              <Badge variant="outline">{data.reason || "Unknown"}</Badge>
            </GlassCard>
          </div>

          <GlassCard className="p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-3">Associated Wallets</h2>
            <div className="space-y-2">
              {(data.wallets ?? []).map((wallet: string) => (
                <div key={wallet} className="flex items-center justify-between text-sm">
                  <a href={`https://solscan.io/account/${wallet}`} target="_blank" rel="noopener noreferrer" className="font-mono text-primary hover:underline">
                    {truncateAddress(wallet)}
                  </a>
                  <Button variant="ghost" size="sm" onClick={() => handleCopy(wallet)}>
                    <Copy className="h-3 w-3 mr-1" />
                    {copied === wallet ? "Copied" : "Copy"}
                  </Button>
                </div>
              ))}
            </div>
          </GlassCard>

          <div className="flex gap-3 mt-6">
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
