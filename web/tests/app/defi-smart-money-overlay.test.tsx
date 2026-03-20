import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DefiDiscoverPage from "@/app/defi/page";
import DefiDetailPage from "@/app/defi/[id]/page";
import { getSmartMoneyOverview } from "@/lib/api";

vi.mock("@/app/defi/_components/discover-client", () => ({
  default: () => <div>discover-client</div>,
}));

vi.mock("@/app/defi/_components/detail-client", () => ({
  default: () => <div>detail-client</div>,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getSmartMoneyOverview: vi.fn(),
  };
});

describe("Defi smart-money overlays", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getSmartMoneyOverview).mockResolvedValue({
      net_flow_usd: 600,
      inflow_usd: 900,
      outflow_usd: 300,
      top_buyers: [],
      top_sellers: [],
      updated_at: "2026-03-19T00:00:00.000Z",
    });
  });

  it("renders smart money panel on defi discover", async () => {
    const page = await DefiDiscoverPage();
    render(page);
    expect(await screen.findByText(/smart money/i)).toBeInTheDocument();
    expect(await screen.findByText(/entity confidence:\s*50%/i)).toBeInTheDocument();
    expect(getSmartMoneyOverview).toHaveBeenCalledWith({ cache: "no-store" });
  });

  it("renders smart money panel on defi detail", async () => {
    const page = await DefiDetailPage({ params: Promise.resolve({ id: "opp_1" }) });
    render(page);
    expect(await screen.findByText(/smart money/i)).toBeInTheDocument();
    expect(await screen.findByText(/entity confidence:\s*50%/i)).toBeInTheDocument();
    expect(getSmartMoneyOverview).toHaveBeenCalledWith({ cache: "no-store" });
  });

  it("falls back to zero confidence for non-finite overview values", async () => {
    vi.mocked(getSmartMoneyOverview).mockResolvedValueOnce({
      net_flow_usd: Number.NaN,
      inflow_usd: Number.POSITIVE_INFINITY,
      outflow_usd: -100,
      top_buyers: [],
      top_sellers: [],
      updated_at: "2026-03-19T00:00:00.000Z",
    });

    const page = await DefiDiscoverPage();
    render(page);

    expect(await screen.findByText(/entity confidence:\s*0%/i)).toBeInTheDocument();
  });
});
