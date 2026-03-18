"use client";

import React from "react";
import { useDefiComparison } from "@/lib/hooks";

export default function CompareClient({ asset }: { asset: string }) {
  const { data, isLoading } = useDefiComparison({ asset, mode: "supply" });

  if (isLoading) return <div>Loading...</div>;

  return (
    <div>
      <h1>Comparison Matrix for {asset}</h1>
      <table>
        <thead>
          <tr>
            <th>Protocol</th>
            <th>APY</th>
          </tr>
        </thead>
        <tbody>
          {data?.matrix?.map((item: any) => (
            <tr key={item.opportunity_id}>
              <td>{item.protocol}</td>
              <td>{item.apy}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}