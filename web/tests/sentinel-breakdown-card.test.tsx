import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { SentinelBreakdownCard } from "@/components/agent/cards/SentinelBreakdownCard";

describe("SentinelBreakdownCard", () => {
  it("shows the four sub-scores and the formula", () => {
    render(
      <SentinelBreakdownCard
        sentinel={{
          sentinel: 84,
          safety: 90,
          durability: 80,
          exit: 86,
          confidence: 78,
          risk_level: "LOW",
          strategy_fit: "balanced",
          flags: [],
        }}
      />
    );
    expect(screen.getByText(/84/)).toBeInTheDocument();
    expect(screen.getByText(/Safety/)).toBeInTheDocument();
    expect(screen.getByText(/Durability/)).toBeInTheDocument();
    expect(screen.getByText(/0\.40.*safety.*0\.25.*durability/)).toBeInTheDocument();
  });
});
