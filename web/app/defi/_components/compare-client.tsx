"use client";

import React from "react";
import { useDefiComparison } from "@/lib/hooks";
import type { DefiCompareRow } from "@/types";

export default function CompareClient({ asset }: { asset: string }) {
  const { data, isLoading } = useDefiComparison({ asset, mode: "supply" });

  if (isLoading) return <div>Loading...</div>;
  if (!data) return <div>Not found</div>;

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
          {data?.matrix?.map((item: DefiCompareRow) => (
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