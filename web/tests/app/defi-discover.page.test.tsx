import React from "react";
import { render, screen, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DiscoverClient from "@/app/defi/_components/discover-client";
import * as hooks from "@/lib/hooks";
import { useQuery } from "@tanstack/react-query";

import { CHAIN_MATRIX, SOLANA_FIXTURE, EVM_FIXTURE } from '../fixtures/defi';

// Mock react-query
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as any),
    useQuery: vi.fn(),
    useQueryClient: vi.fn(() => ({
      getQueryData: vi.fn(),
      setQueryData: vi.fn(),
    })),
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      isPending: false,
    })),
  };
});

// Mock the hooks
vi.mock("@/lib/hooks", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as any),
    useCreateOpportunityAnalysis: vi.fn(),
    useOpportunityAnalysis: vi.fn(),
  };
});

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

  it("does not stop polling if analysisData is only partially populated from cache (missing title)", () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      data: { opportunityId: "job-123" }
    });

    // Return partial cached data with no id or title — not enough to mark done
    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: { status: "running" },
      isLoading: false,
    });

    render(<DiscoverClient />);

    // Should continue polling because analysisData has neither title nor id
    expect(hooks.useOpportunityAnalysis).toHaveBeenLastCalledWith("job-123", {
      includeAi: false,
      pollInterval: 5000,
    });
  });

  it("stops polling when analysisData is fully loaded", () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      data: { opportunityId: "job-123" }
    });

    // Return completed data (has title)
    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: { id: "job-123", title: "Final Analyzed Pool" },
      isLoading: false,
    });

    render(<DiscoverClient />);

    // Check what was passed to useOpportunityAnalysis
    expect(hooks.useOpportunityAnalysis).toHaveBeenLastCalledWith("job-123", {
      includeAi: false,
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

describe("useOpportunityAnalysis Hook", () => {
  it("disables retries when polling is active to avoid exponential backoff on 404s", async () => {
    // Import the actual hook instead of the mocked one
    const actualHooks = await vi.importActual<typeof import("@/lib/hooks")>("@/lib/hooks");
    
    actualHooks.useOpportunityAnalysis("job-123", { pollInterval: 3000 });
    
    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        retry: false, // Should disable retries to prevent pausing during polling
      })
    );
  });

  it("renders solana fixture properties in the provisional shortlist", async () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
      data: {
        opportunityId: "job-sol",
        provisional_shortlist: [
          { id: "1", title: "Test Pool", apy: 12.5, protocol: SOLANA_FIXTURE.protocol_slug, chain: SOLANA_FIXTURE.chain, kind: "pool" }
        ]
      }
    });

    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: null,
      isLoading: true,
    });

    render(<DiscoverClient />);
    expect(await screen.findByText(new RegExp(SOLANA_FIXTURE.protocol_slug, "i"))).toBeInTheDocument();
    expect(await screen.findByText(new RegExp(SOLANA_FIXTURE.chain, "i"))).toBeInTheDocument();
  });

  it("renders evm fixture properties in the provisional shortlist", async () => {
    const mockMutate = vi.fn();
    (hooks.useCreateOpportunityAnalysis as any).mockReturnValue({
      mutate: mockMutate,
      isPending: true,
      data: {
        opportunityId: "job-evm",
        provisional_shortlist: [
          { id: "2", title: "Test Pool", apy: 5.5, protocol: EVM_FIXTURE.protocol_slug, chain: EVM_FIXTURE.chain, kind: "lending" }
        ]
      }
    });

    (hooks.useOpportunityAnalysis as any).mockReturnValue({
      data: null,
      isLoading: true,
    });

    render(<DiscoverClient />);
    expect(await screen.findByText(new RegExp(EVM_FIXTURE.protocol_slug, "i"))).toBeInTheDocument();
    expect(await screen.findByText(new RegExp(EVM_FIXTURE.chain, "i"))).toBeInTheDocument();
  });
});
