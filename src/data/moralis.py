"""
Moralis API integration for multi-chain wallet data.

Used primarily for wallet token holdings, P&L, and transaction history
across EVM chains.
"""

import aiohttp
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional
from src.config import settings
from src.data.moralis_rotator import MoralisKeyRotator, get_rotator

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
    """Client for Moralis Web3 API with rate-limit-aware key rotation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        rotator: Optional[MoralisKeyRotator] = None,
    ):
        # Explicit api_key still works for tests; runtime path uses the rotator.
        self._explicit_key = api_key
        self._rotator = rotator
        self.base_url = "https://deep-index.moralis.io/api/v2.2"
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def rotator(self) -> MoralisKeyRotator:
        if self._rotator is not None:
            return self._rotator
        return get_rotator()

    @property
    def api_key(self) -> Optional[str]:
        # Surface a representative key (first eligible) for legacy callers
        # that read `client.api_key` directly. The actual per-request key is
        # selected inside `_request`.
        if self._explicit_key:
            return self._explicit_key
        rotator = self.rotator
        if rotator.empty:
            return settings.moralis_api_key  # legacy fallback
        return rotator.acquire()

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"accept": "application/json"})
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        timeout: int = 10,
        max_attempts: Optional[int] = None,
    ) -> Optional[aiohttp.ClientResponse]:
        """Execute a request with key rotation on 401/429.

        Returns the final response (caller closes it) or None when all keys
        are exhausted. Logs per-attempt diagnostics.
        """
        rotator = self.rotator
        # When an explicit key was injected (tests, internal calls) skip rotation.
        if self._explicit_key:
            session = await self.get_session()
            return await session.request(
                method, url, params=params, json=json, timeout=timeout,
                headers={"X-API-Key": self._explicit_key},
            )
        attempts = max_attempts if max_attempts is not None else max(1, rotator.size)
        last_response: Optional[aiohttp.ClientResponse] = None
        for attempt in range(attempts):
            key = rotator.acquire()
            if not key:
                logger.warning("Moralis rotator has no eligible keys (attempt %s/%s)", attempt + 1, attempts)
                return None
            session = await self.get_session()
            try:
                response = await session.request(
                    method, url, params=params, json=json, timeout=timeout,
                    headers={"X-API-Key": key},
                )
            except Exception as exc:  # network/connection failure on this key
                logger.warning("Moralis request error on key …%s: %s", key[-6:], exc)
                rotator.mark_rate_limited(key, cooldown_s=15.0)
                continue
            if response.status == 200:
                rotator.mark_success(key)
                return response
            if response.status == 429:
                logger.warning("Moralis 429 on key …%s; rotating", key[-6:])
                rotator.mark_rate_limited(key)
                await response.release()
                last_response = response
                continue
            if response.status in {401, 403}:
                logger.warning("Moralis %s on key …%s; marking invalid", response.status, key[-6:])
                rotator.mark_invalid(key)
                await response.release()
                last_response = response
                continue
            # Any other status — return it, caller decides.
            return response
        return last_response

    async def get_wallet_token_balances(self, wallet_address: str, chain: str) -> List[Dict]:
        """Fetch ERC20 token balances for a wallet on a specific chain.

        Returns empty list when no Moralis keys are configured or on error.
        """
        if not self._explicit_key and self.rotator.empty and not settings.moralis_api_key:
            return []

        moralis_chain = CHAIN_MAPPING.get(chain)
        if not moralis_chain:
            return []

        url = f"{self.base_url}/{wallet_address}/erc20"
        params = {"chain": moralis_chain, "exclude_spam": "true"}
        try:
            response = await self._request("GET", url, params=params, timeout=10)
            if response is None:
                logger.warning("Moralis: all keys exhausted for %s on %s", wallet_address, chain)
                return []
            try:
                if response.status == 200:
                    return await response.json()
                logger.warning("Moralis API error: %s - %s", response.status, await response.text())
                return []
            finally:
                await response.release()
        except Exception as e:
            logger.error("Error fetching Moralis wallet balances: %s", e)
            return []

    def capability_overrides(self) -> Dict[str, Dict[str, Dict[str, object]]]:
        """Return parity matrix overrides for Moralis-backed EVM chains."""
        overrides: Dict[str, Dict[str, Dict[str, object]]] = {}
        for chain in SUPPORTED_EVM_CHAINS:
            overrides[chain] = {
                "spot_holdings": {"supported": True, "reason": None},
                "lp_positions": {"supported": False, "reason": "LP tracking requires protocol-specific integrations"},
                "lending_positions": {"supported": False, "reason": "Lending protocol integrations not yet available"},
                "vault_positions": {"supported": False, "reason": "Vault integrations not yet available"},
                "risk_decomposition": {"supported": False, "reason": "Requires position-level risk modeling"},
                "alert_coverage": {"supported": False, "reason": "Alert system integration pending"},
            }
        return overrides
