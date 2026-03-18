import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as api from '../../lib/api';

describe('Opportunities API', () => {
  let fetchMock: any;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock;
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'http://localhost:8080');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should getDefiOpportunities', async () => {
    const mockResponse = {
      opportunities: [
        { id: '1', kind: 'pool', title: 'Op1', protocol: 'proto', chain: 'ethereum', apy: 10, tvl_usd: 1000 }
      ],
      count: 1,
      summary: {},
      highlights: {},
      methodology: {},
      filters: {},
      data_source: 'DefiLlama'
    };
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(mockResponse),
    });

    const res = await api.getDefiOpportunities({ minApy: 5 });
    expect(res.opportunities.length).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8080/api/v1/defi/opportunities?min_apy=5', expect.any(Object));
  });

  it('should getDefiOpportunity', async () => {
    const mockResponse = { id: '1', title: 'Op1', kind: 'pool', protocol: 'proto', chain: 'ethereum', apy: 10, tvl_usd: 1000 };
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(mockResponse),
    });

    const res = await api.getDefiOpportunity('1', { includeAi: true });
    expect(res.id).toBe('1');
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8080/api/v1/defi/opportunities/1?include_ai=true', expect.any(Object));
  });

  it('should analyzeDefi', async () => {
    const mockResponse = { count: { pools: 1 }, summary: {}, highlights: {}, top_pools: [], top_yields: [], top_lending_markets: [], top_opportunities: [], matching_protocols: [], protocol_spotlights: [], data_source: 'DefiLlama' };
    fetchMock.mockResolvedValueOnce({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve(mockResponse),
    });

    const res = await api.analyzeDefi({ query: 'test' });
    expect(res.count.pools).toBe(1);
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8080/api/v1/defi/analyze?query=test', expect.any(Object));
  });
});
