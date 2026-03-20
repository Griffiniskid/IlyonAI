import React from "react";
import DetailClient from "../_components/detail-client";
import { deriveSmartMoneyEntityConfidencePercent, getRektIncidents, getSmartMoneyOverview } from "@/lib/api";

export default async function DefiDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let entityConfidence = 0;
  let rektIncidents: Array<{ id: string; name: string }> = [];

  try {
    const smartMoney = await getSmartMoneyOverview({ cache: "no-store" });
    entityConfidence = deriveSmartMoneyEntityConfidencePercent(smartMoney);
  } catch {
    entityConfidence = 0;
  }

  try {
    const rekt = await getRektIncidents({ limit: 3 });
    rektIncidents = rekt.incidents.map((incident) => ({ id: incident.id, name: incident.name }));
  } catch {
    rektIncidents = [];
  }
  
  return (
    <div className="container py-8">
      <section aria-label="smart-money-overlay" className="mb-6 rounded-xl border border-border bg-card/40 p-4">
        <h3 className="font-semibold">Smart Money</h3>
        <p className="text-sm text-muted-foreground">Entity confidence: {entityConfidence}%</p>
      </section>
      <section aria-label="rekt-risk-context" className="mb-6 rounded-xl border border-border bg-card/40 p-4">
        <h3 className="font-semibold">Risk Context: Hacks & Exploits</h3>
        <ul className="mt-2 text-sm text-muted-foreground space-y-1">
          {rektIncidents.length === 0 ? (
            <li>No related incidents found.</li>
          ) : (
            rektIncidents.map((incident) => <li key={incident.id}>{incident.name}</li>)
          )}
        </ul>
      </section>
      <DetailClient opportunityId={id} />
    </div>
  );
}
