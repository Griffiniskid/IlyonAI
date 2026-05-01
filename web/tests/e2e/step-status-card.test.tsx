import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SentinelBadge } from "@/components/agent/cards/SentinelBadge";
import { ShieldBadge } from "@/components/agent/cards/ShieldBadge";
import { StepStatusCard } from "@/components/agent/cards/StepStatusCard";
import { MessageList } from "@/components/agent/MessageList";

describe("Step status and score badges", () => {
  it("renders standalone Sentinel and Shield badges", () => {
    render(
      <div>
        <SentinelBadge sentinel={{ sentinel: 88, safety: 90, durability: 86, exit: 91, confidence: 82, risk_level: "LOW", strategy_fit: "balanced", flags: [] }} />
        <ShieldBadge shield={{ verdict: "RISKY", grade: "D", reasons: ["High slippage"] }} />
      </div>,
    );

    expect(screen.getByText("Sentinel 88")).toBeInTheDocument();
    expect(screen.getByText(/D - RISKY/)).toBeInTheDocument();
  });

  it("renders step status transitions", () => {
    render(<StepStatusCard frame={{ kind: "step_status", plan_id: "p1", step_id: "bridge", order: 2, status: "confirmed", tx_hash: "0xabc" }} />);

    expect(screen.getByTestId("step-status-card")).toHaveTextContent("Step 2");
    expect(screen.getByText(/confirmed/)).toBeInTheDocument();
    expect(screen.getByText(/0xabc/)).toBeInTheDocument();
  });

  it("renders streaming step status frames in the message list", () => {
    render(
      <MessageList
        messages={[]}
        currentSteps={{
          thoughts: [],
          tools: [],
          cards: [],
          stepStatuses: [{ kind: "step_status", plan_id: "p1", step_id: "bridge", order: 2, status: "broadcast", tx_hash: "0xdef" }],
        }}
        isStreaming
      />,
    );

    expect(screen.getByTestId("step-status-card")).toHaveTextContent("Step 2");
    expect(screen.getByText(/broadcast/)).toBeInTheDocument();
  });
});
