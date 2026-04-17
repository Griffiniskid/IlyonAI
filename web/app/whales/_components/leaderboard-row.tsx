"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { GlassCard } from "@/components/ui/card";
import { Zap, Sparkles } from "lucide-react";
import { formatUSD, truncateAddress } from "@/lib/utils";
import type { WhaleLeaderboardRow } from "@/types";

export function LeaderboardRow({
  row,
  rank,
}: {
  row: WhaleLeaderboardRow;
  rank: number;
}) {
  const accelerating = row.acceleration >= 2.0;
  return (
    <GlassCard className="hover:border-emerald-500/30 transition">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="text-xl font-bold text-muted-foreground w-8 text-center">
            #{rank}
          </div>
          <div>
            <Link
              href={`/token/${row.token_address}`}
              className="font-semibold hover:text-emerald-400 transition"
            >
              {row.token_symbol}
              <span className="text-muted-foreground font-normal ml-2">
                {row.token_name}
              </span>
            </Link>
            <div className="flex flex-wrap gap-2 mt-2 text-xs">
              {row.is_new_on_radar && (
                <Badge
                  variant="outline"
                  className="border-emerald-500/50 text-emerald-400 gap-1"
                >
                  <Sparkles className="h-3 w-3" /> New on radar
                </Badge>
              )}
              {accelerating && (
                <Badge
                  variant="outline"
                  className="border-yellow-500/50 text-yellow-400 gap-1"
                >
                  <Zap className="h-3 w-3" /> Accelerating
                </Badge>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="font-mono font-bold text-emerald-400">
              {row.net_flow_usd >= 0 ? "+" : ""}
              {formatUSD(row.net_flow_usd)}
            </div>
            <div className="text-xs text-muted-foreground">net flow</div>
          </div>
          <div className="text-right">
            <div className="font-mono font-bold">{row.distinct_buyers}</div>
            <div className="text-xs text-muted-foreground">buyers</div>
          </div>
          <div className="text-right">
            <div className="font-mono font-bold text-lg">
              {row.composite_score.toFixed(0)}
            </div>
            <div className="text-xs text-muted-foreground">score</div>
          </div>
        </div>
      </div>

      {row.top_whales.length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/5 flex flex-wrap gap-2 items-center text-xs">
          <span className="text-muted-foreground">Top whales:</span>
          {row.top_whales.map((w) => (
            <Badge key={w.address} variant="secondary" className="font-mono">
              {w.label ?? truncateAddress(w.address, 4)} · {formatUSD(w.amount_usd)}
            </Badge>
          ))}
        </div>
      )}
    </GlassCard>
  );
}
