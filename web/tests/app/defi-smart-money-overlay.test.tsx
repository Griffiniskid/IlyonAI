import { beforeEach, describe, expect, it, vi } from "vitest";
import DefiDiscoverPage from "@/app/defi/page";
import DefiDetailPage from "@/app/defi/[id]/page";
import { getSmartMoneyOverview } from "@/lib/api";

const redirectMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

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
      flow_direction: "inflow",
      sell_volume_percent: 25,
      top_buyers: [],
      top_sellers: [],
      recent_transactions: [],
      updated_at: "2026-03-19T00:00:00.000Z",
    });
  });

  it("redirects legacy defi discover to dashboard", () => {
    DefiDiscoverPage();

    expect(redirectMock).toHaveBeenCalledWith("/dashboard");
    expect(getSmartMoneyOverview).not.toHaveBeenCalled();
  });

  it("redirects legacy defi detail to dashboard", () => {
    DefiDetailPage();

    expect(redirectMock).toHaveBeenCalledWith("/dashboard");
    expect(getSmartMoneyOverview).not.toHaveBeenCalled();
  });

  it("does not fetch smart money overview from legacy redirect page", () => {
    vi.mocked(getSmartMoneyOverview).mockResolvedValueOnce({
      net_flow_usd: Number.NaN,
      inflow_usd: Number.POSITIVE_INFINITY,
      outflow_usd: -100,
      flow_direction: "neutral",
      sell_volume_percent: 0,
      top_buyers: [],
      top_sellers: [],
      recent_transactions: [],
      updated_at: "2026-03-19T00:00:00.000Z",
    });

    DefiDiscoverPage();

    expect(redirectMock).toHaveBeenCalledWith("/dashboard");
    expect(getSmartMoneyOverview).not.toHaveBeenCalled();
  });
});
