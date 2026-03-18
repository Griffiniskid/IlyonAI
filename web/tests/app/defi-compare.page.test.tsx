import { vi, it, expect, describe } from "vitest"
import { render, screen } from "@testing-library/react"
import CompareClient from "@/app/defi/_components/compare-client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"

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
})