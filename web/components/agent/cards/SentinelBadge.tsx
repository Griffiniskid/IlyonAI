import { Shield } from "lucide-react";

import type { SentinelBlock } from "@/types/agent";

export function SentinelBadge({ sentinel }: { sentinel?: SentinelBlock | null }) {
  if (!sentinel) return null;

  const score = sentinel.sentinel || 0;
  const color =
    score >= 80
      ? "text-emerald-400 bg-emerald-500/15 border-emerald-500/30"
      : score >= 60
        ? "text-yellow-400 bg-yellow-500/15 border-yellow-500/30"
        : score >= 40
          ? "text-orange-400 bg-orange-500/15 border-orange-500/30"
          : "text-red-400 bg-red-500/15 border-red-500/30";

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-medium ${color}`}>
      <Shield className="h-3 w-3" />
      <span>Sentinel {score.toFixed(0)}</span>
    </div>
  );
}
