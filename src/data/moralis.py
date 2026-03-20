"""
Moralis API integration for multi-chain wallet data.

Used primarily for wallet token holdings, P&L, and transaction history
across EVM chains.
"""

import aiohttp
import logging
from typing import Dict, List, Optional
from src.config import settings

logger = logging.getLogger(__name__)

CHAIN_MAPPING = {
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum",
    "bsc": "bsc",
    "polygon": "polygon",
    "optimism": "optimism",
    "avalanche": "avalanche"
}

SUPPORTED_EVM_CHAINS = tuple(CHAIN_MAPPING.keys())

class MoralisClient:
    """Client for Moralis Web3 API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.moralis_api_key
        self.base_url = "https://deep-index.moralis.io/api/v2.2"
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "accept": "application/json",
                "X-API-Key": self.api_key or ""
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_wallet_token_balances(self, wallet_address: str, chain: str) -> List[Dict]:
        """
        Fetch ERC20 token balances for a wallet on a specific chain.
        Returns empty list if no API key or on error.
        """
        if not self.api_key:
            return []

        moralis_chain = CHAIN_MAPPING.get(chain)
        if not moralis_chain:
            return []

        # We exclude spam tokens
        url = f"{self.base_url}/{wallet_address}/erc20"
        params = {
            "chain": moralis_chain,
            "exclude_spam": "true"
        }

        try:
            session = await self.get_session()
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    logger.warning(f"Moralis API error: {resp.status} - {await resp.text()}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching Moralis wallet balances: {e}")
            return []

    def capability_overrides(self) -> Dict[str, Dict[str, Dict[str, object]]]:
        """Return parity matrix overrides for Moralis-backed EVM chains."""
        reason = "Moralis wallet endpoint currently provides spot holdings only"
        overrides: Dict[str, Dict[str, Dict[str, object]]] = {}
        for chain in SUPPORTED_EVM_CHAINS:
            overrides[chain] = {
                "spot_holdings": {"supported": True, "reason": None},
                "lp_positions": {"supported": False, "reason": reason},
                "lending_positions": {"supported": False, "reason": reason},
                "vault_positions": {"supported": False, "reason": reason},
                "risk_decomposition": {"supported": False, "reason": reason},
                "alert_coverage": {"supported": False, "reason": reason},
            }
        return overrides
