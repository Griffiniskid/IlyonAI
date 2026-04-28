"use client";

import { useEffect, useState } from "react";

export function SidebarStatusBadges() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    let stop = false;
    const probe = async () => {
      try {
        const r = await fetch("/api/v1/agent-health", { signal: AbortSignal.timeout(3000) });
        if (!stop) setOk(r.ok);
      } catch {
        if (!stop) setOk(false);
      }
    };
    probe();
    const id = window.setInterval(probe, 30_000);
    return () => {
      stop = true;
      window.clearInterval(id);
    };
  }, []);

  const dot = ok === null ? "bg-muted-foreground/50" : ok ? "bg-emerald-400" : "bg-rose-400";
  const text = ok === null ? "Checking…" : ok ? "Backend online" : "Backend offline";

  return (
    <div className="mt-auto flex flex-col gap-2 border-t border-border/40 pt-3 text-xs">
      <div className="flex items-center gap-2 px-2">
        <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />
        <span className="text-muted-foreground">{text}</span>
      </div>
      <div className="px-2 text-[10px] text-muted-foreground/70">v0.1</div>
    </div>
  );
}
