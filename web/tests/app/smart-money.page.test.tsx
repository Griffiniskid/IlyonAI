import { render, screen } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import SmartMoneyPage from "@/app/smart-money/page";

const useSmartMoneyOverviewMock = vi.fn();

vi.mock("@/lib/hooks", () => ({
  useSmartMoneyOverview: () => useSmartMoneyOverviewMock(),
}));

describe("SmartMoneyPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders a loading state", async () => {
    useSmartMoneyOverviewMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    render(<SmartMoneyPage />);

    expect(await screen.findByText(/loading smart money/i)).toBeInTheDocument();
  });

  it("renders an error state", async () => {
    useSmartMoneyOverviewMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("boom"),
    });

    render(<SmartMoneyPage />);

    expect(await screen.findByText(/unable to load smart money overview/i)).toBeInTheDocument();
  });

  it("renders smart money overview cards", async () => {
    useSmartMoneyOverviewMock.mockReturnValue({
      data: {
        net_flow_usd: 12345,
        inflow_usd: 67890,
        outflow_usd: 55545,
        top_buyers: [],
        top_sellers: [],
        updated_at: "not-a-date",
      },
      isLoading: false,
      error: null,
    });

    render(<SmartMoneyPage />);

    expect(await screen.findByText(/net flow/i)).toBeInTheDocument();
    expect(screen.getByText(/inflow/i)).toBeInTheDocument();
    expect(screen.getByText(/outflow/i)).toBeInTheDocument();

    expect(screen.getByText("$12,345")).toBeInTheDocument();
    expect(screen.getByText("$67,890")).toBeInTheDocument();
    expect(screen.getByText("$55,545")).toBeInTheDocument();
    expect(screen.queryByText(/invalid date/i)).not.toBeInTheDocument();
  });
});
