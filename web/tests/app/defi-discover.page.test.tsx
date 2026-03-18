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
    // Setup initial mock return values
    const mockMutate = vi.fn();
    
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: true, // mutation is in progress or completed
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

    // Mutate should be called on mount
    expect(mockMutate).toHaveBeenCalled();

    // The text should be visible
    expect(await screen.findByText(/provisional shortlist/i)).toBeInTheDocument();
    expect(screen.getByText(/Provisional Pool 1/i)).toBeInTheDocument();
  });
});
