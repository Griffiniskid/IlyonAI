"use client";

import React, { useEffect, useRef } from "react";
import { useCreateOpportunityAnalysis, useOpportunityAnalysis } from "@/lib/hooks";

export default function DiscoverClient() {
  const { mutate, data: createData, isPending: isCreating, isError, error } = useCreateOpportunityAnalysis();
  const opportunityId = createData?.opportunityId || null;

  const hasTriggered = useRef(false);
  useEffect(() => {
    if (!hasTriggered.current) {
      hasTriggered.current = true;
      mutate({ query: "discover" });
    }
  }, [mutate]);

  const [isDone, setIsDone] = React.useState(false);

  const {
    data: analysisData,
    isLoading: isAnalyzing,
    isError: isAnalysisError,
    error: analysisError,
  } = useOpportunityAnalysis(opportunityId, {
    includeAi: false,
    pollInterval: isDone ? undefined : 5000,
  });

  useEffect(() => {
    if (analysisData && (analysisData.title || analysisData.id)) {
      setIsDone(true);
    }
  }, [analysisData]);

  return (
    <div className="p-4 space-y-6">
      <h1 className="text-2xl font-bold">DeFi Discover</h1>
      
      {isCreating && <p>Triggering analysis...</p>}

      {isError && (
        <div className="bg-red-50 p-4 rounded text-red-600">
          {error instanceof Error ? error.message : "An error occurred"}
        </div>
      )}

      {isAnalysisError && (
        <div className="bg-red-50 p-4 rounded text-red-600">
          {analysisError instanceof Error ? analysisError.message : "Failed to fetch opportunity details"}
        </div>
      )}

      {createData?.provisional_shortlist && !isDone && (
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

      {isAnalyzing && opportunityId && !isDone && (
        <p>Analysis is still running... (Job ID: {opportunityId})</p>
      )}
      
      {isDone && analysisData && (
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
