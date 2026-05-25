import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DefiOpportunitiesCard } from "@/components/agent/cards/DefiOpportunitiesCard";
import type { DefiOpportunitiesPayload } from "@/types/agent";

function payload(): DefiOpportunitiesPayload {
  return {
    target_apy: 60,
    risk_levels: ["MEDIUM"],
    chains: ["solana"],
    execution_requested: false,
    excluded_count: 0,
    blockers: [],
    items: [
      {
        protocol: "gmtrade",
        symbol: "USDJPY-USDC",
        chain: "solana",
        apy: 57,
        tvl_usd: 2_500_000,
        risk_level: "MEDIUM",
        executable: false,
        unsupported_reason: "not wired",
        pool_id: "852b494e-a92c-4e87-94c8-ea4f498d9463",
        pool_deeplink: "https://defillama.com/yields/pool/852b494e-a92c-4e87-94c8-ea4f498d9463",
        links: [],
        sentinel: { safety: 51, durability: 51, exit: 85, confidence: 55 },
      },
      {
        protocol: "orca-dex",
        symbol: "SOL-USDC",
        chain: "solana",
        apy: 20,
        tvl_usd: 35_000_000,
        risk_level: "MEDIUM",
        executable: true,
        adapter_id: "solana-yield-builder-fallback",
        pool_id: "deaaa953-89d8-4c41-ac65-b354ff9d57d1",
        links: [],
        sentinel: { safety: 60, durability: 60, exit: 85, confidence: 55 },
      },
    ],
  };
}

function captureExecuteEvent(): { messages: string[] } {
  const store = { messages: [] as string[] };
  window.addEventListener("ilyon:execute-pool", (e) => {
    store.messages.push((e as CustomEvent).detail?.message as string);
  });
  return store;
}

describe("DefiOpportunitiesCard execute form", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows EXECUTE only on executable pools; blocked pools have no Execute button", () => {
    render(<DefiOpportunitiesCard payload={payload()} />);
    // Only the executable Orca pool has an Execute button; Gmtrade (blocked) does not.
    const execButtons = screen.getAllByTestId("defi-opp-execute");
    expect(execButtons).toHaveLength(1);
    // Blocked Gmtrade row shows a non-executable notice instead.
    expect(screen.getByTestId("defi-opp-not-executable")).toBeInTheDocument();
    // ...and an "Open pool" deep-link to that exact pool.
    const openPool = screen.getByTestId("defi-opp-open-pool") as HTMLAnchorElement;
    expect(openPool.getAttribute("href")).toBe(
      "https://defillama.com/yields/pool/852b494e-a92c-4e87-94c8-ea4f498d9463",
    );
    expect(openPool.getAttribute("target")).toBe("_blank");

    // Clicking the one Execute button opens the amount/token form.
    fireEvent.click(execButtons[0]);
    expect(screen.getByTestId("defi-opp-deposit-form")).toBeInTheDocument();
    const select = screen.getByTestId("defi-opp-token") as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["SOL", "USDC"]);
  });

  it("dispatches a native-token deposit message with chosen amount + token", () => {
    const captured = captureExecuteEvent();
    render(<DefiOpportunitiesCard payload={payload()} />);
    // Executable Orca SOL-USDC is the only Execute button.
    fireEvent.click(screen.getByTestId("defi-opp-execute"));
    fireEvent.change(screen.getByTestId("defi-opp-amount"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByTestId("defi-opp-token"), { target: { value: "SOL" } });
    fireEvent.click(screen.getByTestId("defi-opp-build-deposit"));

    expect(captured.messages).toContain(
      "Execute deposit into pool deaaa953-89d8-4c41-ac65-b354ff9d57d1 with 0.5 SOL",
    );
  });

  it("Build deposit is disabled for a non-positive amount", () => {
    render(<DefiOpportunitiesCard payload={payload()} />);
    fireEvent.click(screen.getByTestId("defi-opp-execute"));
    fireEvent.change(screen.getByTestId("defi-opp-amount"), { target: { value: "0" } });
    expect(screen.getByTestId("defi-opp-build-deposit")).toBeDisabled();
  });
});
