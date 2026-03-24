"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Coins, Search } from "lucide-react";
import { GlassCard } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function TokenDiscoverPage() {
  const router = useRouter();
  const [address, setAddress] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = address.trim();
    if (!trimmed) {
      setError("Enter a token address to analyze.");
      return;
    }

    setError(null);
    router.push(`/token/${encodeURIComponent(trimmed)}`);
  };

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <div className="mb-8">
        <div className="mb-2 flex items-center gap-3">
          <Coins className="h-8 w-8 text-emerald-400" />
          <h1 className="text-3xl font-bold">Token Analysis</h1>
        </div>
        <p className="text-muted-foreground">
          Enter a token address to open the full analysis page.
        </p>
      </div>

      <GlassCard>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="token-address" className="mb-1 block text-xs text-muted-foreground">
              Token Address
            </label>
            <Input
              id="token-address"
              placeholder="So11111111111111111111111111111111111111112"
              value={address}
              onChange={(event) => {
                setAddress(event.target.value);
                setError(null);
              }}
              className="font-mono"
            />
          </div>

          {error ? <p className="text-sm text-red-400">{error}</p> : null}

          <Button type="submit" className="w-full">
            <Search className="mr-2 h-4 w-4" />
            Open Token Analysis
          </Button>
        </form>
      </GlassCard>
    </div>
  );
}
