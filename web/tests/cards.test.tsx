import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { CompoundCardRenderer } from "@/components/agent/cards/CompoundCardRenderer";
import { RebalanceCardRenderer } from "@/components/agent/cards/RebalanceCardRenderer";
import { MigrateCardRenderer } from "@/components/agent/cards/MigrateCardRenderer";
import type {
  CompoundCard,
  RebalanceCard,
  MigrateCard,
  LifecycleActionCard,
  AgentCard,
} from "@/types/agent";

describe("V7-025 lifecycle action cards", () => {
  it("CompoundCardRenderer renders pending rewards + CTA", () => {
    const payload: CompoundCard = {
      kind: "compound_card",
      position_id: "uni-v3-0xabc",
      protocol: "uniswap-v3",
      pending_rewards_usd: 123.45,
      reward_token: "UNI",
      reward_amount: 12.5,
      can_compound: true,
      cta_label: "Compound rewards",
    };

    const { asFragment } = render(<CompoundCardRenderer payload={payload} />);

    expect(screen.getByTestId("compound-card")).toBeInTheDocument();
    expect(screen.getByText(/Uniswap V3/)).toBeInTheDocument();
    expect(screen.getByText(/\$123\.45/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Compound rewards/ })).not.toBeDisabled();
    expect(asFragment()).toMatchSnapshot();
  });

  it("CompoundCardRenderer disables CTA when can_compound=false", () => {
    const payload: CompoundCard = {
      kind: "compound_card",
      position_id: "aave-0xdef",
      protocol: "aave",
      pending_rewards_usd: 0,
      reward_token: "AAVE",
      reward_amount: 0,
      can_compound: false,
      cta_label: "Compound rewards",
    };

    render(<CompoundCardRenderer payload={payload} />);
    expect(screen.getByRole("button", { name: /Compound rewards/ })).toBeDisabled();
  });

  it("RebalanceCardRenderer renders ranges + uplift", () => {
    const payload: RebalanceCard = {
      kind: "rebalance_card",
      position_id: "uni-v3-token-12345",
      protocol: "uniswap-v3",
      pair: "WETH/USDC",
      current_range: [1800, 2200],
      suggested_range: [2000, 2400],
      current_value_usd: 5432.1,
      time_out_of_range_pct: 42.5,
      estimated_fee_apr_uplift_pct: 3.21,
      cta_label: "Rebalance position",
    };

    const { asFragment } = render(<RebalanceCardRenderer payload={payload} />);

    expect(screen.getByTestId("rebalance-card")).toBeInTheDocument();
    expect(screen.getByText(/WETH\/USDC/)).toBeInTheDocument();
    expect(screen.getByText(/1800\.00 – 2200\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2000\.00 – 2400\.00/)).toBeInTheDocument();
    expect(screen.getByText(/\+3\.21%/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rebalance position/ })).toBeInTheDocument();
    expect(asFragment()).toMatchSnapshot();
  });

  it("MigrateCardRenderer renders from/to protocols + APR delta", () => {
    const payload: MigrateCard = {
      kind: "migrate_card",
      position_id: "comp-v2-0x123",
      from_protocol: "compound-v2",
      to_protocol: "aave-v3",
      pair: "USDC supply",
      current_apr: 2.5,
      target_apr: 5.75,
      estimated_gas_usd: 12.4,
      cta_label: "Migrate position",
    };

    const { asFragment } = render(<MigrateCardRenderer payload={payload} />);

    expect(screen.getByTestId("migrate-card")).toBeInTheDocument();
    expect(screen.getByText(/Compound V2/)).toBeInTheDocument();
    expect(screen.getByText(/Aave V3/)).toBeInTheDocument();
    expect(screen.getByText(/USDC supply/)).toBeInTheDocument();
    expect(screen.getByText(/2\.50%/)).toBeInTheDocument();
    expect(screen.getByText(/5\.75%/)).toBeInTheDocument();
    expect(screen.getByText(/\$12\.40/)).toBeInTheDocument();
    expect(screen.getByText(/\+3\.25%/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Migrate position/ })).toBeInTheDocument();
    expect(asFragment()).toMatchSnapshot();
  });

  it("LifecycleActionCard discriminated union accepts all 3 kinds (compile-time)", () => {
    // TypeScript compile-time check — if any of these fail the union, `tsc` will error.
    const compound = {
      kind: "compound_card",
      position_id: "p1",
      protocol: "x",
      pending_rewards_usd: 1,
      reward_token: "t",
      reward_amount: 1,
      can_compound: true,
      cta_label: "x",
    } as const satisfies LifecycleActionCard;

    const rebalance = {
      kind: "rebalance_card",
      position_id: "p1",
      protocol: "x",
      pair: "A/B",
      current_range: [1, 2],
      suggested_range: [2, 3],
      current_value_usd: 1,
      time_out_of_range_pct: 1,
      estimated_fee_apr_uplift_pct: 1,
      cta_label: "x",
    } as const satisfies LifecycleActionCard;

    const migrate = {
      kind: "migrate_card",
      position_id: "p1",
      from_protocol: "a",
      to_protocol: "b",
      pair: "A/B",
      current_apr: 1,
      target_apr: 2,
      estimated_gas_usd: 1,
      cta_label: "x",
    } as const satisfies LifecycleActionCard;

    const all: LifecycleActionCard[] = [compound, rebalance, migrate];
    expect(all.map((c) => c.kind).sort()).toEqual(
      ["compound_card", "migrate_card", "rebalance_card"],
    );

    // Also verify the AgentCard CardFrame discriminated union accepts new card_types.
    const frames: Array<Pick<AgentCard, "card_type">> = [
      { card_type: "compound_card" },
      { card_type: "rebalance_card" },
      { card_type: "migrate_card" },
    ];
    expect(frames).toHaveLength(3);
  });
});
