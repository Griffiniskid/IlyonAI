import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { PoolLinkCard } from "@/components/agent/cards/PoolLinkCard";

const ADDR = "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae";

describe("pool address surfacing (deep-link fallback)", () => {
  it("PoolLinkCard shows a copyable pool address when present", () => {
    render(
      <PoolLinkCard
        payload={{ card_type: "pool_link", protocol: "pancakeswap-amm", chain: "bsc", pool_symbol: "USDT-WBNB", pool_address: ADDR, url: "https://pancakeswap.finance/x" }}
      />,
    );
    expect(screen.getByTestId("pool-link-address")).toBeTruthy();
    expect(screen.getByTestId("pool-link-copy-address")).toBeTruthy();
    expect(screen.getByText(/0x16b9a8/)).toBeTruthy();
  });

  it("PoolLinkCard omits the address row when absent", () => {
    render(<PoolLinkCard payload={{ card_type: "pool_link", protocol: "wombex", chain: "bsc", url: "https://x" }} />);
    expect(screen.queryByTestId("pool-link-address")).toBeNull();
  });
});
