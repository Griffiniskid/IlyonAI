import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WhalesPage from "@/app/whales/page";
import * as api from "@/lib/api";

vi.mock("@/lib/api");

const leaderboardResponse = {
  window: "6h" as const,
  sort: "composite" as const,
  rows: [
    {
      token_address: "wif-addr",
      token_symbol: "WIF",
      token_name: "dogwifhat",
      net_flow_usd: 2_400_000,
      gross_buy_usd: 2_700_000,
      gross_sell_usd: 300_000,
      distinct_buyers: 8,
      distinct_sellers: 2,
      tx_count: 14,
      buy_sell_ratio: 9,
      acceleration: 2.4,
      is_new_on_radar: true,
      composite_score: 87.0,
      top_whales: [
        { address: "w1", label: "Alameda", side: "buy" as const, amount_usd: 800_000 },
      ],
    },
  ],
  updated_at: "2026-04-17T12:00:00",
};

const topWhalesResponse = {
  window: "6h" as const,
  rows: [
    {
      address: "w1",
      label: "Alameda",
      total_volume_usd: 4_200_000,
      tx_count: 12,
      tokens_touched: 5,
      dominant_side: "buy" as const,
    },
  ],
  updated_at: "2026-04-17T12:00:00",
};

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <WhalesPage />
    </QueryClientProvider>,
  );
}

describe("WhalesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getWhaleLeaderboard).mockResolvedValue(leaderboardResponse);
    vi.mocked(api.getTopWhales).mockResolvedValue(topWhalesResponse);
  });

  it("renders the leaderboard and sidebar", async () => {
    renderPage();
    expect(await screen.findByText("WIF")).toBeInTheDocument();
    expect(await screen.findByText("Alameda")).toBeInTheDocument();
    expect(screen.getByText(/new on radar/i)).toBeInTheDocument();
    expect(screen.getByText(/accelerating/i)).toBeInTheDocument();
  });

  it("renders empty state when leaderboard is empty", async () => {
    vi.mocked(api.getWhaleLeaderboard).mockResolvedValue({
      ...leaderboardResponse,
      rows: [],
    });
    renderPage();
    expect(await screen.findByText(/quiet hour/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /show last 24h/i }),
    ).toBeInTheDocument();
  });

  it("changing window triggers refetch with new key", async () => {
    renderPage();
    await screen.findByText("WIF");
    const oneHourBtn = screen.getByRole("button", { name: "1h" });
    fireEvent.click(oneHourBtn);
    await waitFor(() => {
      expect(api.getWhaleLeaderboard).toHaveBeenCalledWith(
        expect.objectContaining({ window: "1h" }),
      );
    });
  });

  it("sidebar failure does not unmount leaderboard", async () => {
    vi.mocked(api.getTopWhales).mockRejectedValue(new Error("boom"));
    renderPage();
    expect(await screen.findByText("WIF")).toBeInTheDocument();
    expect(screen.getByText(/failed to load whales/i)).toBeInTheDocument();
  });
});
