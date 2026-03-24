import React from "react";
import Link from "next/link";
import DetailClient from "../_components/detail-client";
import { deriveSmartMoneyEntityConfidencePercent, getRektIncidents, getSmartMoneyOverview } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default async function DefiDetailPage({ params }: { params: Promise<{ id: string }> }) {
 const { id } = await params;
 let entityConfidence = 0;
 let rektIncidents: Array<{ id: string; name: string; protocol: string; severity: string }> = [];

 try {
   const smartMoney = await getSmartMoneyOverview({ cache: "no-store" });
   entityConfidence = deriveSmartMoneyEntityConfidencePercent(smartMoney);
 } catch {
   entityConfidence = 0;
 }

 try {
   const rekt = await getRektIncidents({ limit: 5 });
   rektIncidents = rekt.incidents.map((incident) => ({
     id: incident.id,
     name: incident.name,
     protocol: incident.protocol,
     severity: incident.severity,
   }));
 } catch {
   rektIncidents = [];
 }

 return (
   <div className="container py-8">
     <section aria-label="smart-money-overlay" className="mb-6 rounded-xl border border-border bg-card/40 p-4">
       <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
         <h3 className="font-semibold">Smart Money</h3>
         <Badge variant="outline">Entity confidence: {entityConfidence}%</Badge>
       </div>
       <p className="text-sm text-muted-foreground mb-3">
         Capital-flow clustering and entity-aware whale detection for this market.
       </p>
       <div className="flex flex-wrap gap-2">
         <Button asChild size="sm" variant="outline">
           <Link href="/smart-money">Open Smart Money Hub</Link>
         </Button>
         <Button asChild size="sm" variant="outline">
           <Link href="/whales">View Whale Feed</Link>
         </Button>
       </div>
     </section>

     <section aria-label="rekt-risk-context" className="mb-6 rounded-xl border border-border bg-card/40 p-4">
       <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
         <h3 className="font-semibold">Risk Context: Hacks & Exploits</h3>
         <Button asChild size="sm" variant="outline">
           <Link href="/rekt">View REKT Database</Link>
         </Button>
       </div>
       <ul className="mt-2 text-sm text-muted-foreground space-y-1">
         {rektIncidents.length === 0 ? (
           <li>No related incidents found.</li>
         ) : (
           rektIncidents.map((incident) => (
             <li key={incident.id}>
               <Link href={`/rekt/${incident.id}`} className="hover:text-primary transition">
                 {incident.name} ({incident.protocol})
               </Link>
             </li>
           ))
         )}
       </ul>
     </section>

     <DetailClient opportunityId={id} />
   </div>
 );
}
