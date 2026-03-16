"""
DefiLlama API client for DeFi protocol data.

DefiLlama provides free, open DeFi data including:
- Protocol TVL (Total Value Locked)
- Yield/APY data for pools across all chains
- Stablecoin data
- Bridge data
- Protocol metadata and chain breakdowns

API docs: https://defillama.com/docs/api
No API key required.
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from src.chains.base import ChainType
from src.defi.opportunity_taxonomy import classify_defi_record

logger = logging.getLogger(__name__)

DEFILLAMA_BASE_URL = "https://api.llama.fi"
DEFILLAMA_YIELDS_URL = "https://yields.llama.fi"
DEFILLAMA_COINS_URL = "https://coins.llama.fi"
DEFILLAMA_STABLECOINS_URL = "https://stablecoins.llama.fi"

# DefiLlama chain name mapping
DEFILLAMA_CHAIN_NAMES = {
    ChainType.ETHEREUM: "Ethereum",
    ChainType.BSC: "BSC",
    ChainType.POLYGON: "Polygon",
    ChainType.ARBITRUM: "Arbitrum",
    ChainType.OPTIMISM: "Optimism",
    ChainType.AVALANCHE: "Avalanche",
    ChainType.BASE: "Base",
    ChainType.SOLANA: "Solana",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_pool_record(pool: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize DefiLlama pool data while preserving legacy aliases."""
    tvl_usd = _safe_float(pool.get("tvlUsd"))
    apy = _safe_float(pool.get("apy"))
    apy_base = _safe_float(pool.get("apyBase"))
    apy_reward = _safe_float(pool.get("apyReward"))
    apy_mean_30d = _safe_float(pool.get("apyMean30d"))
    apy_borrow = _safe_float(pool.get("apyBorrow"))
    apy_pct_1d = _safe_float(pool.get("apyPct1D"))
    apy_pct_7d = _safe_float(pool.get("apyPct7D"))
    apy_pct_30d = _safe_float(pool.get("apyPct30D"))
    total_supply_usd = _safe_float(pool.get("totalSupplyUsd"))
    total_borrow_usd = _safe_float(pool.get("totalBorrowUsd"))
    volume_usd_1d = _safe_float(pool.get("volumeUsd1d"))
    volume_usd_7d = _safe_float(pool.get("volumeUsd7d"))

    utilization = pool.get("utilization")
    if utilization is None and total_supply_usd > 0:
        utilization = total_borrow_usd / total_supply_usd
    utilization = _safe_float(utilization)

    normalized = {
        "pool_id": pool.get("pool", ""),
        "pool": pool.get("pool", ""),
        "chain": pool.get("chain", ""),
        "project": pool.get("project", ""),
        "category": pool.get("category", ""),
        "symbol": pool.get("symbol", ""),
        "tvl_usd": tvl_usd,
        "tvlUsd": tvl_usd,
        "apy": apy,
        "apy_base": apy_base,
        "apyBase": apy_base,
        "apy_reward": apy_reward,
        "apyReward": apy_reward,
        "apy_mean_30d": apy_mean_30d,
        "apyMean30d": apy_mean_30d,
        "apy_borrow": apy_borrow,
        "apyBorrow": apy_borrow,
        "apy_pct_1d": apy_pct_1d,
        "apyPct1D": apy_pct_1d,
        "apy_pct_7d": apy_pct_7d,
        "apyPct7D": apy_pct_7d,
        "apy_pct_30d": apy_pct_30d,
        "apyPct30D": apy_pct_30d,
        "il_risk": pool.get("ilRisk", ""),
        "ilRisk": pool.get("ilRisk", ""),
        "stablecoin": bool(pool.get("stablecoin", False)),
        "exposure": pool.get("exposure", ""),
        "volume_usd_1d": volume_usd_1d,
        "volumeUsd1d": volume_usd_1d,
        "volume_usd_7d": volume_usd_7d,
        "volumeUsd7d": volume_usd_7d,
        "pool_meta": pool.get("poolMeta"),
        "poolMeta": pool.get("poolMeta"),
        "underlying_tokens": pool.get("underlyingTokens", []),
        "underlyingTokens": pool.get("underlyingTokens", []),
        "reward_tokens": pool.get("rewardTokens", []),
        "rewardTokens": pool.get("rewardTokens", []),
        "url": pool.get("url", ""),
        "audits": pool.get("audits") or 0,
        "age_days": _safe_float(pool.get("ageDays")),
        "ageDays": _safe_float(pool.get("ageDays")),
        "total_supply_usd": total_supply_usd,
        "totalSupplyUsd": total_supply_usd,
        "total_borrow_usd": total_borrow_usd,
        "totalBorrowUsd": total_borrow_usd,
        "utilization": utilization,
    }
    normalized.update(classify_defi_record(normalized))
    return normalized


class DefiLlamaClient:
    """
    Client for the DefiLlama API.

    Provides DeFi analytics data including TVL, yields, and protocol info
    across all supported chains.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Accept": "application/json"},
            )
        return self._session

    async def _get(self, url: str, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
        """Make a GET request."""
        session = await self._get_session()
        request_params = params or {}
        try:
            async with session.get(url, params=request_params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning(f"DefiLlama API HTTP {resp.status} for {url}")
                    return None
        except Exception as e:
            logger.error(f"DefiLlama API request failed: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # TVL & PROTOCOL DATA
    # ═══════════════════════════════════════════════════════════════

    async def get_protocols(self) -> List[Dict[str, Any]]:
        """
        Get all DeFi protocols with TVL data.

        Returns list of protocols with: name, tvl, chains, category, etc.
        """
        data = await self._get(f"{DEFILLAMA_BASE_URL}/protocols")
        return data if isinstance(data, list) else []

    async def get_protocol(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed protocol data by slug (e.g., 'aave', 'uniswap').

        Returns TVL breakdown by chain, historical data, etc.
        """
        return await self._get(f"{DEFILLAMA_BASE_URL}/protocol/{slug}")

    async def get_protocol_tvl(self, slug: str) -> Optional[Dict[str, Any]]:
        """Alias for get_protocol — returns detailed TVL + chain breakdown."""
        return await self.get_protocol(slug)

    async def get_chain_tvl(self, chain: ChainType) -> Optional[float]:
        """Get total TVL for a specific chain."""
        chain_name = DEFILLAMA_CHAIN_NAMES.get(chain)
        if not chain_name:
            return None

        data = await self._get(f"{DEFILLAMA_BASE_URL}/v2/chains")
        if not data or not isinstance(data, list):
            return None

        for item in data:
            if item.get("name", "").lower() == chain_name.lower():
                return float(item.get("tvl", 0))
        return None

    async def get_all_chains_tvl(self) -> Dict[str, float]:
        """Get TVL for all chains."""
        data = await self._get(f"{DEFILLAMA_BASE_URL}/v2/chains")
        if not data or not isinstance(data, list):
            return {}

        result = {}
        for item in data:
            name = item.get("name", "")
            tvl = float(item.get("tvl", 0))
            result[name] = tvl
        return result

    # ═══════════════════════════════════════════════════════════════
    # YIELD / APY DATA
    # ═══════════════════════════════════════════════════════════════

    async def get_pools(
        self,
        chain: Optional[ChainType] = None,
        project: Optional[str] = None,
        min_tvl: float = 0,
        min_apy: float = 0,
        stablecoin_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get yield farming pools/opportunities.

        Args:
            chain: Filter by chain (None = all chains).
            project: Filter by project name (e.g., 'aave-v3').
            min_tvl: Minimum TVL in USD.
            min_apy: Minimum APY percentage.
            stablecoin_only: Only show stablecoin pools.

        Returns:
            List of pool dicts with: pool, chain, project, symbol, tvlUsd, apy, etc.
        """
        data = await self._get(f"{DEFILLAMA_YIELDS_URL}/pools")
        if not data or not isinstance(data, dict):
            return []

        pools = data.get("data", [])
        if not isinstance(pools, list):
            return []

        chain_name = DEFILLAMA_CHAIN_NAMES.get(chain) if chain else None

        filtered = []
        for pool in pools:
            # Apply filters
            if chain_name and pool.get("chain", "").lower() != chain_name.lower():
                continue
            if project and pool.get("project", "").lower() != project.lower():
                continue
            if pool.get("tvlUsd", 0) < min_tvl:
                continue

            apy = pool.get("apy", 0) or 0
            if apy < min_apy:
                continue

            if stablecoin_only and not pool.get("stablecoin", False):
                continue

            filtered.append(_normalize_pool_record(pool))

        # Sort by APY descending
        filtered.sort(key=lambda x: x.get("apy", 0), reverse=True)
        return filtered

    async def get_pool_history(self, pool_id: str) -> List[Dict[str, Any]]:
        """Get historical APY/TVL data for a specific pool."""
        data = await self._get(f"{DEFILLAMA_YIELDS_URL}/chart/{pool_id}")
        if not data or not isinstance(data, dict):
            return []
        return data.get("data", [])

    async def get_pool_chart(self, pool_id: str) -> List[Dict[str, Any]]:
        """Alias for get_pool_history — returns historical APY/TVL data."""
        return await self.get_pool_history(pool_id)

    # ═══════════════════════════════════════════════════════════════
    # TOKEN PRICE DATA
    # ═══════════════════════════════════════════════════════════════

    async def get_token_prices(
        self,
        tokens: List[Dict[str, str]],
    ) -> Dict[str, float]:
        """
        Get current prices for multiple tokens.

        Args:
            tokens: List of dicts with 'chain' and 'address' keys.
                    Example: [{"chain": "ethereum", "address": "0x..."}]

        Returns:
            Dict mapping "chain:address" to USD price.
        """
        # Build coins parameter: "chain:address,chain:address,..."
        coins = []
        for t in tokens:
            chain = t.get("chain", "")
            address = t.get("address", "")
            if chain and address:
                coins.append(f"{chain}:{address}")

        if not coins:
            return {}

        coins_str = ",".join(coins)
        data = await self._get(
            f"{DEFILLAMA_COINS_URL}/prices/current/{coins_str}"
        )

        if not data or not isinstance(data, dict):
            return {}

        prices = {}
        for key, info in data.get("coins", {}).items():
            prices[key] = info.get("price", 0)

        return prices

    # ═══════════════════════════════════════════════════════════════
    # STABLECOIN DATA
    # ═══════════════════════════════════════════════════════════════

    async def get_stablecoins(self) -> List[Dict[str, Any]]:
        """Get all stablecoins with market cap and chain distribution."""
        data = await self._get(f"{DEFILLAMA_STABLECOINS_URL}/stablecoins")
        if not data or not isinstance(data, dict):
            return []
        return data.get("peggedAssets", [])

    # ═══════════════════════════════════════════════════════════════
    # BRIDGE DATA
    # ═══════════════════════════════════════════════════════════════

    async def get_bridges(self) -> List[Dict[str, Any]]:
        """Get all cross-chain bridges with volume data."""
        data = await self._get(f"{DEFILLAMA_BASE_URL}/bridges")
        if not data or not isinstance(data, dict):
            return []
        return data.get("bridges", [])

    # ═══════════════════════════════════════════════════════════════
    # SEARCH & DISCOVERY
    # ═══════════════════════════════════════════════════════════════

    async def search_protocols(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search for DeFi protocols by name.

        Performs client-side filtering on the protocols list.
        """
        protocols = await self.get_protocols()
        query_lower = query.lower()

        matches = []
        for p in protocols:
            name = p.get("name", "").lower()
            symbol = p.get("symbol", "").lower()
            slug = p.get("slug", "").lower()

            if query_lower in name or query_lower in symbol or query_lower in slug:
                matches.append({
                    "name": p.get("name", ""),
                    "slug": p.get("slug", ""),
                    "symbol": p.get("symbol", ""),
                    "tvl": p.get("tvl", 0),
                    "chains": p.get("chains", []),
                    "category": p.get("category", ""),
                    "logo": p.get("logo", ""),
                    "url": p.get("url", ""),
                    "audits": p.get("audits", "0"),
                    "audit_links": p.get("audit_links", []),
                })

            if len(matches) >= limit:
                break

        # Sort by TVL descending
        matches.sort(key=lambda x: x.get("tvl", 0), reverse=True)
        return matches

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("DefiLlamaClient closed")
