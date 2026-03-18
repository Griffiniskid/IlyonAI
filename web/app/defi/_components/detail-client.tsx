"use client";

import React from "react";
import { useOpportunityAnalysis } from "@/lib/hooks";

export default function DetailClient({ opportunityId }: { opportunityId: string }) {
  const { data, isLoading } = useOpportunityAnalysis(opportunityId);

  if (isLoading) return <div>Loading...</div>;
  if (!data) return <div>Not found</div>;

  return (
    <div>
      <h1>{data.title}</h1>
      <section>
        <h2>Behavior</h2>
        {typeof data.behavior === "string" ? (
          <p>{data.behavior}</p>
        ) : data.behavior ? (
          <pre>{JSON.stringify(data.behavior, null, 2)}</pre>
        ) : (
          <p>No behavior data available</p>
        )}
      </section>
      <section>
        <h2>Evidence</h2>
        <ul>
          {data.evidence?.map((item: any, i: number) => (
            <li key={i}>{item.title}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Scenarios</h2>
        <ul>
          {data.scenarios?.map((item: any, i: number) => (
            <li key={i}>{item.title}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>AI Analyst</h2>
        <div>
          <p>{data.ai_analysis?.headline}</p>
          <p>{data.ai_analysis?.summary}</p>
        </div>
      </section>
    </div>
  );
}