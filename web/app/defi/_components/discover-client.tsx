"use client";

import React, { useEffect } from "react";
import { useCreateOpportunityAnalysis, useOpportunityAnalysis } from "@/lib/hooks";

export default function DiscoverClient() {
  const { mutate, data: createData, isPending: isCreating } = useCreateOpportunityAnalysis();
  
  const opportunityId = createData?.opportunityId || null;
  const pollInterval = opportunityId ? 3000 : undefined; // Poll every 3 seconds if we have an ID

  const { data: analysisData, isLoading: isAnalyzing } = useOpportunityAnalysis(opportunityId, {
    pollInterval,
  });

  // Start analysis on mount
  useEffect(() => {
    mutate({ query: "discover" });
  }, [mutate]);

  return (
    <div className="p-4 space-y-6">
      <h1 className="text-2xl font-bold">DeFi Discover</h1>
      
      {isCreating && <p>Triggering analysis...</p>}

      {createData?.provisional_shortlist && (
        <div className="bg-gray-100 p-4 rounded">
          <h2 className="text-xl font-semibold mb-2">Provisional Shortlist</h2>
          <ul>
            {createData.provisional_shortlist.map((item) => (
              <li key={item.id} className="mb-2 p-2 bg-white rounded shadow-sm">
                <strong>{item.title}</strong> - {item.protocol} on {item.chain} (APY: {item.apy}%)
              </li>
            ))}
          </ul>
        </div>
      )}

      {isAnalyzing && opportunityId && <p>Analysis is still running... (Job ID: {opportunityId})</p>}
      
      {analysisData && (
        <div className="bg-blue-50 p-4 rounded mt-4">
          <h2 className="text-xl font-semibold mb-2">Final Analysis Result</h2>
          <pre className="text-sm overflow-auto max-h-64">
            {JSON.stringify(analysisData, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
