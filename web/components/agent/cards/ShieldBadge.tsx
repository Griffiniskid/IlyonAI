import { ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";

import type { ShieldBlock } from "@/types/agent";

export function ShieldBadge({ shield }: { shield?: ShieldBlock | null }) {
  if (!shield) return null;

  const grade = shield.grade || "C";
  const verdict = shield.verdict || "CAUTION";
  const color =
    verdict === "SAFE"
      ? "text-emerald-400 bg-emerald-500/15 border-emerald-500/30"
      : verdict === "CAUTION"
        ? "text-yellow-400 bg-yellow-500/15 border-yellow-500/30"
        : verdict === "RISKY"
          ? "text-orange-400 bg-orange-500/15 border-orange-500/30"
          : "text-red-400 bg-red-500/15 border-red-500/30";
  const icon =
    verdict === "SAFE" ? (
      <ShieldCheck className="h-3 w-3" />
    ) : verdict === "DANGEROUS" ? (
      <ShieldX className="h-3 w-3" />
    ) : (
      <ShieldAlert className="h-3 w-3" />
    );

  return (
    <div className={`inline-flex items-center gap-1 px-2 py-1 rounded-md border text-xs font-medium ${color}`}>
      {icon}
      <span>
        {grade} - {verdict}
      </span>
    </div>
  );
}
