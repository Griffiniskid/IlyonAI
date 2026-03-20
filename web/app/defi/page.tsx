import React from "react";
import DiscoverClient from "./_components/discover-client";
import { deriveSmartMoneyEntityConfidencePercent, getSmartMoneyOverview } from "@/lib/api";

export const metadata = {
  title: "DeFi Discover",
  description: "Discover new DeFi opportunities",
};

export default async function DefiDiscoverPage() {
  let entityConfidence = 0;
  try {
    const smartMoney = await getSmartMoneyOverview({ cache: "no-store" });
    entityConfidence = deriveSmartMoneyEntityConfidencePercent(smartMoney);
  } catch {
    entityConfidence = 0;
  }

  return (
    <main className="container mx-auto py-8">
      <section aria-label="smart-money-overlay" className="mb-6 rounded-xl border border-border bg-card/40 p-4">
        <h3 className="font-semibold">Smart Money</h3>
        <p className="text-sm text-muted-foreground">Entity confidence: {entityConfidence}%</p>
      </section>
      <DiscoverClient />
    </main>
  );
}
