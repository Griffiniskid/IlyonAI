import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WhalesPage from "@/app/whales/page";

const useWhaleActivityMock = vi.fn();
const queryClientMock = {
  invalidateQueries: vi.fn(),
  setQueryData: vi.fn(),
};

vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQueryClient: () => queryClientMock,
  };
});

vi.mock("@/lib/hooks", () => ({
  useWhaleActivity: () => useWhaleActivityMock(),
}));

describe("WhalesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWhaleActivityMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isFetching: false,
    });
  });

  it("renders multi-chain whale feed controls", async () => {
    render(<WhalesPage />);
    expect(await screen.findByText(/all chains/i)).toBeInTheDocument();
    expect(await screen.findByText(/entity confidence/i)).toBeInTheDocument();
  });

  it("normalizes whale confidence when API returns 0-100 scale", async () => {
    useWhaleActivityMock.mockReturnValue({
      data: {
        transactions: [],
        updated_at: "2026-03-19T00:00:00.000Z",
        filter_token: null,
        min_amount_usd: 1000,
        entity_confidence: 73,
      },
      isLoading: false,
      isFetching: false,
    });

    render(<WhalesPage />);
    expect(await screen.findByText(/entity confidence:\s*73%/i)).toBeInTheDocument();
  });
});
