import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useOpportunityAnalysis, useDefiOpportunities, useDefiAnalyzer } from '../../lib/hooks';
import * as api from '../../lib/api';

vi.mock('../../lib/api', () => ({
  getDefiOpportunity: vi.fn(),
  getDefiOpportunities: vi.fn(),
  analyzeDefi: vi.fn(),
}));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe('Opportunity Analysis Hooks', () => {
  beforeEach(() => {
    queryClient.clear();
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('useOpportunityAnalysis', () => {
    it('should fetch and poll an opportunity analysis', async () => {
      const mockResult = { id: '1', title: 'Test Op', kind: 'pool', protocol: 'proto', apy: 10, tvl_usd: 100 };
      vi.mocked(api.getDefiOpportunity).mockResolvedValue(mockResult as any);

      const { result } = renderHook(() => useOpportunityAnalysis('1', { pollInterval: 100 }), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.title).toBe('Test Op');
      expect(api.getDefiOpportunity).toHaveBeenCalledWith('1', expect.anything());
    });
  });

  describe('useDefiOpportunities', () => {
    it('should fetch opportunities', async () => {
      const mockResult = { opportunities: [], count: 0, summary: {}, highlights: {}, filters: {}, data_source: 'DefiLlama' };
      vi.mocked(api.getDefiOpportunities).mockResolvedValue(mockResult as any);

      const { result } = renderHook(() => useDefiOpportunities({ minApy: 10 }), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.count).toBe(0);
      expect(api.getDefiOpportunities).toHaveBeenCalledWith({ minApy: 10 });
    });
  });

  describe('useDefiAnalyzer', () => {
    it('should call analyzeDefi', async () => {
      const mockResult = { count: { pools: 1 }, summary: {}, highlights: {}, top_pools: [], top_yields: [], top_lending_markets: [], top_opportunities: [], matching_protocols: [], protocol_spotlights: [], data_source: 'DefiLlama' };
      vi.mocked(api.analyzeDefi).mockResolvedValue(mockResult as any);

      const { result } = renderHook(() => useDefiAnalyzer({ query: 'test' }), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data?.count.pools).toBe(1);
      expect(api.analyzeDefi).toHaveBeenCalledWith({ query: 'test' });
    });
  });
});
