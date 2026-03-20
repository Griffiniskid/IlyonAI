import Link from "next/link";

import { getRektIncidents } from "@/lib/api";

export default async function RektPage() {
  let incidents: Awaited<ReturnType<typeof getRektIncidents>>["incidents"] = [];
  try {
    const data = await getRektIncidents({ limit: 25 });
    incidents = data.incidents;
  } catch {
    incidents = [];
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-2">REKT Database</h1>
      <p className="text-muted-foreground mb-6">Recent hacks and exploits across DeFi protocols.</p>

      <div className="space-y-3">
        {incidents.map((incident) => (
          <Link
            key={incident.id}
            href={`/rekt/${incident.id}`}
            className="block rounded-xl border border-border bg-card/40 p-4 hover:bg-card/60"
          >
            <div className="font-semibold">{incident.name}</div>
            <div className="text-sm text-muted-foreground">{incident.protocol}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
