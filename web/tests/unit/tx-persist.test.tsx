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

const stakeJson = JSON.stringify({
  status: "ok", action: "stake", is_stake: true, staking_protocol: "Jito", receipt_token_symbol: "jitoSOL",
  swapTransaction: "AQ==", ui_out_amount: 0.00078, ui_in_amount: 0.001, in_symbol: "SOL", out_symbol: "jitoSOL",
  from_token_symbol: "SOL", to_token_symbol: "Jito JitoSOL", route_summary: "Stake via Jito", liquid: true, apy: 5.18,
});

describe("signed-tx persistence on the card", () => {
  it("WITHOUT a persisted signature: shows the Sign button (can sign)", () => {
    const preview = parseSwapPreview(stakeJson)!;
    render(<SimulationPreview preview={preview} solanaAddress="So11111111111111111111111111111111111111112" walletType="phantom" />);
    expect(screen.getByRole("button", { name: /Stake in Phantom/i })).toBeInTheDocument();
    expect(screen.queryByText(/Transaction sent/i)).not.toBeInTheDocument();
  });

  it("WITH a persisted signature (re-mount after navigating away): shows ✅ sent, NO sign button (no re-signing)", () => {
    const preview = parseSwapPreview(stakeJson)!;
    render(
      <SimulationPreview
        preview={preview}
        solanaAddress="So11111111111111111111111111111111111111112"
        walletType="phantom"
        initialSignature="5jer7shkMNxtZoxu9ZjX87UBL8ZzWSmGJjKAwFUTDT6nQDzin4Z"
      />,
    );
    // success state restored from the persisted signature
    expect(screen.getByText(/Transaction sent/i)).toBeInTheDocument();
    expect(screen.getByText(/5jer7shkMNxtZoxu9ZjX/)).toBeInTheDocument();
    // the Sign button must be GONE so the user can't accidentally double-sign
    expect(screen.queryByRole("button", { name: /Stake in Phantom/i })).not.toBeInTheDocument();
  });
});
