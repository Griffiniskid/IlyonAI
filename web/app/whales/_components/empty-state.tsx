"use client";

import { Button } from "@/components/ui/button";
import { GlassCard } from "@/components/ui/card";
import { Fish } from "lucide-react";
import type { WhaleWindow } from "@/types";

export function EmptyState({
  onJumpToWide,
}: {
  onJumpToWide: (w: WhaleWindow) => void;
}) {
  return (
    <GlassCard className="text-center py-12">
      <Fish className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
      <h3 className="text-lg font-semibold mb-2">Quiet hour</h3>
      <p className="text-muted-foreground mb-4">
        No whale activity in this window. Try a wider lookback.
      </p>
      <Button onClick={() => onJumpToWide("24h")}>Show last 24h</Button>
    </GlassCard>
  );
}
