import { vi, it, expect, describe } from "vitest"
import { render, screen } from "@testing-library/react"
import CompareClient from "@/app/defi/_components/compare-client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"

import { CHAIN_MATRIX, SOLANA_FIXTURE, EVM_FIXTURE } from '../fixtures/defi';

const useDefiComparisonMock = vi.fn()

// Mock the hook
vi.mock("@/lib/hooks", () => ({
  useDefiComparison: (...args: any[]) => useDefiComparisonMock(...args)
}))

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

describe("CompareClient", () => {
  it("renders a side-by-side comparison matrix", async () => {
    useDefiComparisonMock.mockReturnValue({
      data: {
        matrix: [
          { opportunity_id: "opp_1", protocol: "Protocol A", apy: 10 },
          { opportunity_id: "opp_2", protocol: "Protocol B", apy: 12 },
        ]
      },
      isLoading: false,
    })

    render(
      <QueryClientProvider client={queryClient}>
        <CompareClient asset="USDC" />
      </QueryClientProvider>
    )
    expect(await screen.findByText(/comparison matrix/i)).toBeInTheDocument()
  })

  it("renders a not found message when data is missing", async () => {
    useDefiComparisonMock.mockReturnValue({
      data: null,
      isLoading: false,
    })

    render(
      <QueryClientProvider client={queryClient}>
        <CompareClient asset="USDC" />
      </QueryClientProvider>
    )
    expect(await screen.findByText(/not found/i)).toBeInTheDocument()
  })

  it("renders comparison matrix with solana fixture", async () => {
    useDefiComparisonMock.mockReturnValue({
      data: {
        matrix: [
          { opportunity_id: "opp_1", protocol: SOLANA_FIXTURE.protocol_slug, chain: SOLANA_FIXTURE.chain, apy: 10 },
        ]
      },
      isLoading: false,
    })

    render(
      <QueryClientProvider client={queryClient}>
        <CompareClient asset="USDC" />
      </QueryClientProvider>
    )
    expect(await screen.findByText(new RegExp(SOLANA_FIXTURE.protocol_slug, "i"))).toBeInTheDocument()
  })

  it("renders comparison matrix with evm fixture", async () => {
    useDefiComparisonMock.mockReturnValue({
      data: {
        matrix: [
          { opportunity_id: "opp_2", protocol: EVM_FIXTURE.protocol_slug, chain: EVM_FIXTURE.chain, apy: 12 },
        ]
      },
      isLoading: false,
    })

    render(
      <QueryClientProvider client={queryClient}>
        <CompareClient asset="USDC" />
      </QueryClientProvider>
    )
    expect(await screen.findByText(new RegExp(EVM_FIXTURE.protocol_slug, "i"))).toBeInTheDocument()
  })
})