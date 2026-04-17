"use client";

import Link from "next/link";
import { GlassCard } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatUSD, truncateAddress } from "@/lib/utils";
import type { TopWhaleRow } from "@/types";

export function TopWhalesPanel({
  rows,
  isError,
  isLoading,
}: {
  rows: TopWhaleRow[];
  isError?: boolean;
  isLoading?: boolean;
}) {
  return (
    <GlassCard>
      <h3 className="font-semibold mb-4 flex items-center gap-2">Top Whales</h3>
      {isError && (
        <p className="text-sm text-red-400">Failed to load whales</p>
      )}
      {isLoading && !isError && (
        <p className="text-sm text-muted-foreground">Loading...</p>
      )}
      {!isLoading && !isError && rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No active whales in this window.
        </p>
      )}
      <ul className="space-y-3">
        {rows.map((w) => (
          <li
            key={w.address}
            className="border-b border-white/5 pb-3 last:border-0"
          >
            <Link
              href={`/whales/wallet/${w.address}`}
              className="hover:text-emerald-400 transition block"
            >
              <div className="flex items-center justify-between">
                <div className="font-mono text-sm">
                  {w.label ?? truncateAddress(w.address, 6)}
                </div>
                <Badge
                  variant="outline"
                  className={cn(
                    "text-xs",
                    w.dominant_side === "buy" && "border-emerald-500/50 text-emerald-400",
                    w.dominant_side === "sell" && "border-red-500/50 text-red-400",
                  )}
                >
                  {w.dominant_side}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {formatUSD(w.total_volume_usd)} · {w.tx_count} tx · {w.tokens_touched} tokens
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </GlassCard>
  );
}
