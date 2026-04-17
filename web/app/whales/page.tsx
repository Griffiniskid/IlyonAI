"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWhaleLeaderboard, useTopWhales } from "@/lib/hooks";
import { GlassCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Fish, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WhaleWindow, WhaleSort } from "@/types";
import { WindowSortControls } from "./_components/window-sort-controls";
import { LeaderboardRow } from "./_components/leaderboard-row";
import { TopWhalesPanel } from "./_components/top-whales-panel";
import { EmptyState } from "./_components/empty-state";

export default function WhalesPage() {
  const [window, setWindow] = useState<WhaleWindow>("6h");
  const [sort, setSort] = useState<WhaleSort>("composite");
  const queryClient = useQueryClient();

  const leaderboard = useWhaleLeaderboard({ window, sort });
  const topWhales = useTopWhales({ window });

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["whales"] });
  };

  const rows = leaderboard.data?.rows ?? [];
  const busy = leaderboard.isFetching || topWhales.isFetching;

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
            <Fish className="h-8 w-8 text-emerald-500" /> Whale Tracker
          </h1>
          <p className="text-muted-foreground">
            What whales are buying right now — ranked by signal strength
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={busy}>
          <RefreshCw
            className={cn("h-4 w-4 mr-2", busy && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      <GlassCard className="mb-8">
        <WindowSortControls
          window={window}
          sort={sort}
          onWindowChange={setWindow}
          onSortChange={setSort}
        />
      </GlassCard>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_320px] gap-6">
        <div className="space-y-4">
          {leaderboard.isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
            </div>
          )}
          {leaderboard.isError && (
            <GlassCard className="text-center py-8 text-red-400">
              Failed to load leaderboard. Try again.
            </GlassCard>
          )}
          {!leaderboard.isLoading && !leaderboard.isError && rows.length === 0 && (
            <EmptyState onJumpToWide={setWindow} />
          )}
          {rows.map((row, i) => (
            <LeaderboardRow key={row.token_address} row={row} rank={i + 1} />
          ))}
        </div>

        <aside>
          <TopWhalesPanel
            rows={topWhales.data?.rows ?? []}
            isError={topWhales.isError}
            isLoading={topWhales.isLoading}
          />
        </aside>
      </div>

      {leaderboard.data && rows.length > 0 && (
        <div className="text-center text-sm text-muted-foreground mt-8">
          Window: {window} · Last updated:{" "}
          {new Date(leaderboard.data.updated_at).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
}
