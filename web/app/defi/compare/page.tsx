import React from "react";
import CompareClient from "../_components/compare-client";

export default async function DefiComparePage({ searchParams }: { searchParams: Promise<{ asset?: string }> }) {
  const params = await searchParams;
  const asset = params.asset || "USDC";

  return (
    <div className="container py-8">
      <CompareClient asset={asset} />
    </div>
  );
}