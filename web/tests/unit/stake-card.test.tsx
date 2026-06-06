import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { parseSwapPreview, SimulationPreview } from "@/components/agent-app/MainApp";

// SimulationPreview uses framer-motion; stub it to plain DOM (no animation).
vi.mock("framer-motion", () => {
  const R = require("react") as typeof import("react");
  const skip = new Set(["animate", "initial", "exit", "variants", "transition", "whileHover", "whileTap", "layout"]);
  const motion = new Proxy({}, {
    get: (_t, tag: string) => R.forwardRef<HTMLElement, Record<string, unknown>>((props, ref) => {
      const dom = Object.fromEntries(Object.entries(props).filter(([k]) => !skip.has(k)));
      return R.createElement(tag, { ...dom, ref });
    }),
  });
  return { AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>, motion };
});

const stakeJson = JSON.stringify({
  status: "ok",
  type: "solana_swap_proposal",
  chain_type: "solana",
  action: "stake",
  is_stake: true,
  staking_protocol: "Jito",
  receipt_token_symbol: "jitoSOL",
  swapTransaction: "AQ==",
  out_amount: "778324562",
  ui_out_amount: 0.77833,
  ui_in_amount: 1,
  in_symbol: "SOL",
  out_symbol: "jitoSOL",
  from_token_symbol: "SOL",
  to_token_symbol: "Jito JitoSOL",
  route_summary: "Stake via Jito JitoSOL",
  liquid: true,
  unstake_note: "Liquid stake — you receive jitoSOL, unstake anytime.",
  apy: 5.18,
  est_yearly_yield_sol: 0.000518,
});

describe("SimulationPreview — liquid stake card", () => {
  it("renders a dedicated STAKE card (not a swap) with a Stake CTA", () => {
    const preview = parseSwapPreview(stakeJson);
    expect(preview).not.toBeNull();
    expect(preview?.isStake).toBe(true);

    render(
      <SimulationPreview
        preview={preview!}
        fromAddress=""
        solanaAddress="So11111111111111111111111111111111111111112"
        walletType="phantom"
      />,
    );

    // Distinct stake card — never the swap layout.
    expect(screen.getByText(/Liquid Stake Preview/i)).toBeInTheDocument();
    expect(screen.queryByText(/Swap Preview/i)).not.toBeInTheDocument();
    // Stake-specific labels + the LST received.
    expect(screen.getByText(/You Stake/i)).toBeInTheDocument();
    expect(screen.getAllByText(/1 SOL/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/jitoSOL/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/unstake anytime/i).length).toBeGreaterThan(0);
    // Shows expected earnings (APY) — "how much I will earn".
    expect(screen.getByText(/Est\. APY/i)).toBeInTheDocument();
    expect(screen.getAllByText(/5\.18%/).length).toBeGreaterThan(0);
    // CTA must say Stake, not Swap.
    expect(screen.getByRole("button", { name: /Stake in Phantom/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Swap in Phantom/i })).not.toBeInTheDocument();
  });

  it("renders an EVM stake (ETH -> stETH) as a stake card with APY too", () => {
    const evmStakeJson = JSON.stringify({
      status: "ok",
      type: "evm_action_proposal",
      action: "stake",
      is_stake: true,
      staking_protocol: "Lido",
      receipt_token_symbol: "stETH",
      from_token_symbol: "ETH",
      to_token_symbol: "Lido stETH",
      amount_in_display: "0.1",
      dst_amount_display: "0.1",
      route_summary: "Stake via Lido stETH",
      apy: 3.12,
      est_yearly_yield: 0.003115,
      liquid: true,
      unstake_note: "Liquid stake — you receive stETH, unstake/swap back to ETH anytime.",
      tx: { to: "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84", data: "0x", value: "0x16345785d8a0000", chain_id: 1 },
    });
    const preview = parseSwapPreview(evmStakeJson);
    expect(preview?.isStake).toBe(true);
    render(
      <SimulationPreview preview={preview!} fromAddress="0xabc" solanaAddress="" walletType="metamask" />,
    );
    expect(screen.getByText(/Liquid Stake Preview/i)).toBeInTheDocument();
    expect(screen.queryByText(/Swap Preview/i)).not.toBeInTheDocument();
    expect(screen.getByText(/You Stake/i)).toBeInTheDocument();
    expect(screen.getAllByText(/stETH/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Est\. APY/i)).toBeInTheDocument();
    expect(screen.getAllByText(/3\.12%/).length).toBeGreaterThan(0);
    // EVM stake CTA goes through MetaMask, labelled Stake (not Swap).
    expect(screen.getByRole("button", { name: /Stake in MetaMask/i })).toBeInTheDocument();
  });
});
