import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import DefiDetailPage from "@/app/defi/[id]/page";
import { getRektIncidents } from "@/lib/api";

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
      top_buyers: [],
      top_sellers: [],
      updated_at: "2026-03-19T00:00:00.000Z",
    }),
    getRektIncidents: vi.fn(),
  };
});

describe("Defi rekt context", () => {
  it("renders rekt risk context on detail page without using id as search term", async () => {
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

    const page = await DefiDetailPage({ params: Promise.resolve({ id: "opp_1" }) });
    render(page);

    expect(await screen.findByText(/risk context: hacks & exploits/i)).toBeInTheDocument();
    expect(await screen.findByText(/defi exploit/i)).toBeInTheDocument();
    expect(getRektIncidents).toHaveBeenCalledWith({ limit: 3 });
  });
});
