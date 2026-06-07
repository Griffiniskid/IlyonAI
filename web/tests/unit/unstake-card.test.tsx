import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { parseSwapPreview, SimulationPreview } from "@/components/agent-app/MainApp";

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

const solUnstakeJson = JSON.stringify({
  status: "ok",
  action: "unstake",
  is_unstake: true,
  liquid: true,
  staking_protocol: "Jito",
  swapTransaction: "AQ==",
  in_symbol: "JitoSOL",
  out_symbol: "SOL",
  from_token_symbol: "JitoSOL",
  to_token_symbol: "SOL",
  ui_in_amount: 0.05,
  ui_out_amount: 0.0557,
  out_amount: "55700000",
  route_summary: "Unstake JitoSOL → SOL",
  unstake_note: "Liquid unstake — your JitoSOL is swapped back to SOL instantly via Jupiter.",
});

describe("SimulationPreview — unstake card", () => {
  it("renders a dedicated UNSTAKE card (not stake/swap) with an Unstake CTA", () => {
    const preview = parseSwapPreview(solUnstakeJson);
    expect(preview?.isUnstake).toBe(true);
    render(
      <SimulationPreview
        preview={preview!}
        fromAddress=""
        solanaAddress="So11111111111111111111111111111111111111112"
        walletType="phantom"
      />,
    );
    expect(screen.getByText(/Unstake Preview/i)).toBeInTheDocument();
    expect(screen.queryByText(/Liquid Stake Preview/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Swap Preview/i)).not.toBeInTheDocument();
    expect(screen.getByText(/You Unstake/i)).toBeInTheDocument();
    expect(screen.getAllByText(/JitoSOL/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/instantly/i).length).toBeGreaterThan(0);
    // CTA must say Unstake, not Stake/Swap.
    expect(screen.getByRole("button", { name: /Unstake in Phantom/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /(?<!Un)Stake in Phantom/i })).not.toBeInTheDocument();
  });

  it("renders an EVM unstake (stETH -> ETH) as an unstake card", () => {
    const evmUnstakeJson = JSON.stringify({
      status: "ok",
      type: "evm_action_proposal",
      action: "unstake",
      is_unstake: true,
      liquid: true,
      staking_protocol: "Lido",
      tx: { to: "0x1111111111111111111111111111111111111111", data: "0xabcdef", value: "0", chain_id: 1 },
      from_token_symbol: "stETH",
      to_token_symbol: "ETH",
      amount_in_display: "0.01",
      dst_amount_display: "0.0099",
      route_summary: "Unstake stETH → ETH",
      unstake_note: "Liquid unstake — your stETH is swapped back to ETH via Enso routing.",
    });
    const preview = parseSwapPreview(evmUnstakeJson);
    expect(preview?.isUnstake).toBe(true);
    render(
      <SimulationPreview preview={preview!} fromAddress="0xabc" solanaAddress="" walletType="metamask" />,
    );
    expect(screen.getByText(/Unstake Preview/i)).toBeInTheDocument();
    expect(screen.getByText(/You Unstake/i)).toBeInTheDocument();
    expect(screen.getAllByText(/stETH/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Unstake in MetaMask/i })).toBeInTheDocument();
  });
});
