"""
GoPlus Security API client for multi-chain token security analysis.

GoPlus provides automated security detection for tokens across 20+ chains.
It serves as the primary security data source for EVM chains (replacing
RugCheck which is Solana-specific).

API docs: https://docs.gopluslabs.io/
Free tier: No API key required for basic usage, key recommended for higher limits.
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from src.chains.base import ChainType

logger = logging.getLogger(__name__)

# GoPlus chain ID mapping
GOPLUS_CHAIN_IDS = {
    ChainType.ETHEREUM: "1",
    ChainType.BSC: "56",
    ChainType.POLYGON: "137",
    ChainType.ARBITRUM: "42161",
    ChainType.OPTIMISM: "10",
    ChainType.AVALANCHE: "43114",
    ChainType.BASE: "8453",
    # Solana is supported via a different endpoint
    ChainType.SOLANA: "solana",
}

GOPLUS_BASE_URL = "https://api.gopluslabs.io/api/v1"


class GoPlusClient:
    """
    Client for the GoPlus Security API.

    Provides multi-chain token security analysis including:
    - Honeypot detection
    - Contract risk analysis (mint, pause, blacklist, proxy)
    - Owner/deployer analysis
    - Trading tax detection
    - Holder concentration analysis
    """

    def __init__(self, api_key: Optional[str] = None):
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_key = api_key

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Accept": "application/json"}
            if self._api_key:
                headers["Authorization"] = self._api_key
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            )
        return self._session

    async def _get(self, endpoint: str, params: Dict[str, str] = None) -> Optional[Dict]:
        """Make a GET request to the GoPlus API."""
        session = await self._get_session()
        url = f"{GOPLUS_BASE_URL}/{endpoint}"
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == 1:
                        return data.get("result", {})
                    else:
                        logger.warning(f"GoPlus API error: {data.get('message', 'Unknown')}")
                        return None
                else:
                    logger.warning(f"GoPlus API HTTP {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"GoPlus API request failed: {e}")
            return None

    async def check_token_security(
        self,
        token_address: str,
        chain: ChainType
    ) -> Optional[Dict[str, Any]]:
        """
        Check token security for any supported chain.

        Returns comprehensive security data including:
        - is_honeypot, buy_tax, sell_tax
        - is_mintable, can_take_back_ownership
        - is_proxy, is_open_source
        - owner_address, creator_address
        - holder_count, lp_holder_count
        - And many more risk indicators

        Args:
            token_address: Token contract address.
            chain: Blockchain network.

        Returns:
            Security analysis dict or None if failed.
        """
        chain_id = GOPLUS_CHAIN_IDS.get(chain)
        if not chain_id:
            logger.warning(f"GoPlus does not support chain: {chain.value}")
            return None

        result = await self._get(
            f"token_security/{chain_id}",
            params={"contract_addresses": token_address.lower()}
        )

        if not result:
            return None

        # GoPlus returns results keyed by address (lowercase)
        token_data = result.get(token_address.lower())
        if not token_data:
            # Try without lowering
            for key, value in result.items():
                token_data = value
                break

        if not token_data:
            return None

        # Normalize the response into a clean format
        return self._normalize_token_security(token_data, chain)

    def _normalize_token_security(self, data: Dict, chain: ChainType) -> Dict[str, Any]:
        """Normalize GoPlus response into a standardized format."""

        def _bool(val) -> bool:
            """Convert GoPlus string booleans to Python bool."""
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip() == "1"
            return bool(val)

        def _float(val, default=0.0) -> float:
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        return {
            # Basic info
            "token_name": data.get("token_name", ""),
            "token_symbol": data.get("token_symbol", ""),
            "total_supply": data.get("total_supply", "0"),
            "holder_count": int(data.get("holder_count", 0) or 0),

            # Honeypot detection
            "is_honeypot": _bool(data.get("is_honeypot")),
            "honeypot_with_same_creator": _bool(data.get("honeypot_with_same_creator")),
            "buy_tax": _float(data.get("buy_tax")),
            "sell_tax": _float(data.get("sell_tax")),

            # Contract security
            "is_open_source": _bool(data.get("is_open_source")),
            "is_proxy": _bool(data.get("is_proxy")),
            "is_mintable": _bool(data.get("is_mintable")),
            "can_take_back_ownership": _bool(data.get("can_take_back_ownership")),
            "owner_change_balance": _bool(data.get("owner_change_balance")),
            "hidden_owner": _bool(data.get("hidden_owner")),
            "selfdestruct": _bool(data.get("selfdestruct")),
            "external_call": _bool(data.get("external_call")),

            # Trading restrictions
            "transfer_pausable": _bool(data.get("transfer_pausable")),
            "cannot_buy": _bool(data.get("cannot_buy")),
            "cannot_sell_all": _bool(data.get("cannot_sell_all")),
            "trading_cooldown": _bool(data.get("trading_cooldown")),
            "is_anti_whale": _bool(data.get("is_anti_whale")),
            "anti_whale_modifiable": _bool(data.get("anti_whale_modifiable")),
            "slippage_modifiable": _bool(data.get("slippage_modifiable")),
            "personal_slippage_modifiable": _bool(data.get("personal_slippage_modifiable")),

            # Blacklist
            "is_blacklisted": _bool(data.get("is_blacklisted")),
            "is_whitelisted": _bool(data.get("is_whitelisted")),

            # Owner info
            "owner_address": data.get("owner_address", ""),
            "creator_address": data.get("creator_address", ""),
            "owner_balance": data.get("owner_balance", "0"),
            "owner_percent": _float(data.get("owner_percent")),
            "creator_balance": data.get("creator_balance", "0"),
            "creator_percent": _float(data.get("creator_percent")),

            # LP info
            "lp_holder_count": int(data.get("lp_holder_count", 0) or 0),
            "lp_total_supply": data.get("lp_total_supply", "0"),
            "is_true_token": _bool(data.get("is_true_token")),
            "is_airdrop_scam": _bool(data.get("is_airdrop_scam")),

            # Holders
            "holders": data.get("holders", []),
            "lp_holders": data.get("lp_holders", []),
            "dex": data.get("dex", []),

            # Trust list
            "trust_list": _bool(data.get("trust_list")),

            # Note info
            "note": data.get("note", ""),

            # Chain
            "chain": chain.value,
        }

    async def check_address_security(
        self,
        address: str,
        chain: ChainType
    ) -> Optional[Dict[str, Any]]:
        """
        Check if an address is associated with malicious activity.

        Useful for deployer/wallet risk assessment.
        """
        chain_id = GOPLUS_CHAIN_IDS.get(chain)
        if not chain_id:
            return None

        result = await self._get(
            "address_security",
            params={"address": address.lower(), "chain_id": chain_id}
        )

        if not result:
            return None

        return {
            "is_malicious": result.get("malicious_address") == "1",
            "is_contract": result.get("contract_address") == "1",
            "data_source": result.get("data_source", ""),
            "malicious_behavior": result.get("malicious_behavior", []),
        }

    async def check_approval_security(
        self,
        contract_address: str,
        chain: ChainType
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a contract is risky for token approvals.

        Used by the Shield/Approval Manager feature.
        """
        chain_id = GOPLUS_CHAIN_IDS.get(chain)
        if not chain_id:
            return None

        result = await self._get(
            "approval_security",
            params={"contract_addresses": contract_address.lower(), "chain_id": chain_id}
        )

        return result

    async def check_nft_security(
        self,
        nft_address: str,
        chain: ChainType
    ) -> Optional[Dict[str, Any]]:
        """Check NFT contract security."""
        chain_id = GOPLUS_CHAIN_IDS.get(chain)
        if not chain_id:
            return None

        result = await self._get(
            f"nft_security/{chain_id}",
            params={"contract_addresses": nft_address.lower()}
        )

        return result

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("GoPlusClient closed")
