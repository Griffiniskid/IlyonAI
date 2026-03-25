"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Droplets, Search } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function PoolDiscoverPage() {
  const router = useRouter();
  const [poolId, setPoolId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = poolId.trim();
    if (!trimmed) {
      setError("Enter a pool id or address.");
      return;
    }

    setError(null);

    // Detect blockchain addresses (Solana base58 or EVM 0x) and route as DexScreener pair
    const isSolanaAddress = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(trimmed);
    const isEvmAddress = /^0x[a-fA-F0-9]{40}$/i.test(trimmed);

    if (isSolanaAddress || isEvmAddress) {
      router.push(`/pool/${encodeURIComponent(trimmed)}?source=dexpair&pair=${encodeURIComponent(trimmed)}`);
    } else {
      router.push(`/pool/${encodeURIComponent(trimmed)}`);
    }
  };

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <div className="mb-8">
        <div className="mb-2 flex items-center gap-3">
          <Droplets className="h-8 w-8 text-emerald-400" />
          <h1 className="text-3xl font-bold">Pool Analysis</h1>
        </div>
        <p className="text-muted-foreground">
          Enter a pool id or address to open the full pool analysis page.
        </p>
      </div>

      <GlassCard>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="pool-id" className="mb-1 block text-xs text-muted-foreground">
              Pool ID or Pair Address
            </label>
            <Input
              id="pool-id"
              placeholder="Paste DexScreener pair address or DeFi Llama pool ID"
              value={poolId}
              onChange={(event) => {
                setPoolId(event.target.value);
                setError(null);
              }}
              className="font-mono"
            />
          </div>

          {error ? <p className="text-sm text-red-400">{error}</p> : null}

          <Button type="submit" className="w-full">
            <Search className="mr-2 h-4 w-4" />
            Open Pool Analysis
          </Button>
        </form>
      </GlassCard>
    </div>
  );
}
