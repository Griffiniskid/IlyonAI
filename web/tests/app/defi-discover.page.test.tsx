import React from "react";
import { render, screen, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DiscoverClient from "@/app/defi/_components/discover-client";
import * as hooks from "@/lib/hooks";

// Mock the hooks
vi.mock("@/lib/hooks", () => ({
  useCreateOpportunityAnalysis: vi.fn(),
  useOpportunityAnalysis: vi.fn(),
}));

describe("Defi Discover Flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the provisional shortlist while the analysis is still running", async () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
      data: {
        opportunityId: "job-123",
        provisional_shortlist: [
          { id: "1", title: "Provisional Pool 1", apy: 12.5, protocol: "Aave", chain: "ethereum", kind: "lending" }
        ]
      }
    });

    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: null,
      isLoading: true,
    });

    render(<DiscoverClient />);
    expect(await screen.findByText(/provisional shortlist/i)).toBeInTheDocument();
    expect(screen.getByText(/Provisional Pool 1/i)).toBeInTheDocument();
  });

  it("stops polling when analysisData is fully loaded", () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      data: { opportunityId: "job-123" }
    });

    // Return completed data
    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: { id: "job-123", title: "Final Analyzed Pool" },
      isLoading: false,
    });

    render(<DiscoverClient />);

    // Check what was passed to useOpportunityAnalysis
    expect(hooks.useOpportunityAnalysis).toHaveBeenCalledWith("job-123", {
      pollInterval: undefined,
    });
  });

  it("shows an error message if the creation mutation fails", async () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isError: true,
      error: new Error("Analysis creation failed with status 500"),
      data: null
    });

    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: null,
      isLoading: false,
    });

    render(<DiscoverClient />);

    expect(await screen.findByText(/Analysis creation failed with status 500/i)).toBeInTheDocument();
  });

  it("only calls mutate once on mount, even if re-rendered", () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      data: null
    });

    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: null,
      isLoading: false,
    });

    const { rerender } = render(<DiscoverClient />);
    rerender(<DiscoverClient />); // Simulate an update

    expect(mockMutate).toHaveBeenCalledTimes(1);
  });
});
