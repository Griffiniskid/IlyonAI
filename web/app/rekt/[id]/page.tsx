import Link from "next/link";

import { getRektIncident } from "@/lib/api";

export default async function RektIncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const incident = await getRektIncident(id);

  if (!incident) {
    return (
      <div className="container mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold">Incident Not Found</h1>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <Link href="/rekt" className="text-sm text-muted-foreground hover:text-foreground">
        Back to REKT Database
      </Link>
      <h1 className="text-3xl font-bold mt-3 mb-2">{incident.name}</h1>
      <p className="text-muted-foreground mb-4">{incident.protocol}</p>
      <p>{incident.description}</p>
    </div>
  );
}
