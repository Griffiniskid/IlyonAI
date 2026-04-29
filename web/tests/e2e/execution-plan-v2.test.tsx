import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CardRenderer } from "@/components/agent/cards/CardRenderer";

describe("Execution plan v2 card", () => {
  it("renders the bridge/stake execution plan as a first-class card", () => {
    render(
      <CardRenderer
        card={{
          kind: "card",
          step_index: 1,
          card_id: "plan-1",
          card_type: "execution_plan_v2",
          payload: {
            plan_id: "plan-1",
            title: "Bridge USDC to Arbitrum and stake on Aave",
            total_steps: 4,
            total_gas_usd: 18,
            total_duration_estimate_s: 240,
            blended_sentinel: null,
            requires_signature_count: 3,
            risk_warnings: ["Cross-chain execution requires receipt confirmation before follow-up steps."],
            risk_gate: "soft_warn",
            requires_double_confirm: true,
            chains_touched: ["1", "42161"],
            user_assets_required: {},
            steps: [
              { step_id: "a", order: 1, action: "approve", params: {}, depends_on: [], resolves_from: {}, shield_flags: [], status: "ready" },
              { step_id: "b", order: 2, action: "bridge", params: {}, depends_on: ["a"], resolves_from: {}, shield_flags: [], status: "pending" },
              { step_id: "c", order: 3, action: "wait_receipt", params: {}, depends_on: ["b"], resolves_from: {}, shield_flags: [], status: "pending" },
              { step_id: "d", order: 4, action: "stake", params: {}, depends_on: ["c"], resolves_from: {}, shield_flags: [], status: "pending" },
            ],
          },
        }}
      />,
    );

    expect(screen.getByTestId("execution-plan-v2-card")).toHaveTextContent(/Bridge USDC/);
    expect(screen.getAllByTestId("execution-plan-v2-row")).toHaveLength(4);
    expect(screen.getByText(/Double confirmation required/)).toBeInTheDocument();
  });
});
