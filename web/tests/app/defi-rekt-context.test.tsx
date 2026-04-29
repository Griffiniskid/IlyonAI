import { describe, expect, it, vi } from "vitest";

import DefiDetailPage from "@/app/defi/[id]/page";
import { getRektIncidents } from "@/lib/api";

const redirectMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

vi.mock("@/app/defi/_components/detail-client", () => ({
  default: () => <div>detail-client</div>,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getSmartMoneyOverview: vi.fn().mockResolvedValue({
      net_flow_usd: 600,
      inflow_usd: 900,
      outflow_usd: 300,
      flow_direction: "inflow",
      sell_volume_percent: 25,
      top_buyers: [],
      top_sellers: [],
      recent_transactions: [],
      updated_at: "2026-03-19T00:00:00.000Z",
    }),
    getRektIncidents: vi.fn(),
  };
});

describe("Defi rekt context", () => {
  it("redirects legacy detail page to dashboard", () => {
    vi.mocked(getRektIncidents).mockResolvedValue({
      incidents: [
        {
          id: "incident-1",
          name: "Defi Exploit",
          date: "2024-01-01",
          amount_usd: 1000000,
          protocol: "Defi",
          chains: ["Ethereum"],
          attack_type: "Exploit",
          description: "test",
          post_mortem_url: "",
          funds_recovered: false,
          severity: "HIGH",
        },
      ],
      count: 1,
      total_stolen_usd: 1000000,
      meta: { cursor: null, freshness: "warm" },
    });

    DefiDetailPage();

    expect(redirectMock).toHaveBeenCalledWith("/dashboard");
    expect(getRektIncidents).not.toHaveBeenCalled();
  });
});
