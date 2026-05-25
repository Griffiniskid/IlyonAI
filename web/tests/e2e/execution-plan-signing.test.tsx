import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExecutionPlanV3Card } from "@/components/agent/cards/ExecutionPlanV3Card";

function plan(overrides: Record<string, unknown> = {}) {
  return {
    plan_id: "plan-1",
    title: "PancakeSwap AMM Deposit LP",
    summary: "Deposit BUSD into pancakeswap-amm via Enso.",
    status: "ready",
    risk_gate: "clear",
    requires_double_confirm: false,
    blockers: [],
    steps: [
      {
        step_id: "s1",
        index: 1,
        action: "supply",
        protocol: "pancakeswap-amm",
        asset_in: "BUSD",
        amount_in: "10",
        status: "ready",
        depends_on: [],
        resolves_from: {},
        shield_flags: [],
        transaction: { chain_kind: "evm", to: "0xpool", data: "0xabc", chain_id: 56 },
      },
    ],
    totals: { signatures_required: 1, estimated_gas_usd: 4.5, chains_touched: ["bsc"], assets_required: {}, estimated_duration_s: 30 },
    ...overrides,
  } as never;
}

describe("ExecutionPlanV3Card sign-button gating", () => {
  it("shows Sign button when the plan is READY with no blockers", () => {
    render(<ExecutionPlanV3Card payload={plan()} onSignStep={vi.fn()} />);
    expect(screen.getByTestId("sign-step-s1")).toBeInTheDocument();
  });

  it("HIDES the Sign button when the plan is blocked (insufficient balance/gas)", () => {
    render(
      <ExecutionPlanV3Card
        payload={plan({
          status: "blocked",
          blockers: [
            { code: "INSUFFICIENT_BALANCE", severity: "blocker", title: "Not enough BUSD", detail: "Need 10 BUSD, wallet has 0." },
            { code: "GAS_TOPUP_REQUIRED", severity: "blocker", title: "Not enough BNB for gas", detail: "Top up BNB." },
          ],
        })}
        onSignStep={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("sign-step-s1")).toBeNull();
    // The blocker is still surfaced to the user.
    expect(screen.getByText(/Not enough BUSD/i)).toBeInTheDocument();
  });
});
