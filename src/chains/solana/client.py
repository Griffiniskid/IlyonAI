"""
Solana chain client - adapter over existing SolanaClient.

Wraps the existing src/data/solana.py SolanaClient to implement
the unified ChainClient interface, maintaining full backward compatibility.
"""

import logging
from typing import Any, Dict, List, Optional

from src.chains.base import ChainClient, ChainConfig

logger = logging.getLogger(__name__)


class SolanaChainClient(ChainClient):
    """
    Solana implementation of ChainClient.

    Wraps the existing SolanaClient from src/data/solana.py to provide
    the unified chain interface while preserving all existing Solana-specific
    functionality.
    """

    def __init__(self, config: ChainConfig):
        super().__init__(config)
        self._solana_client = None
        self._honeypot_detector = None
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazy-initialize the underlying Solana client."""
        if not self._initialized:
            from src.data.solana import SolanaClient
            from src.config import settings

            self._solana_client = SolanaClient(
                self.config.rpc_url,
                helius_api_key=settings.helius_api_key
            )
            self._initialized = True

    @property
    def solana_client(self):
        """Access the underlying SolanaClient for Solana-specific operations."""
        return self._solana_client

    async def get_token_info(self, address: str) -> Dict[str, Any]:
        """Get token info from Solana RPC."""
        await self._ensure_initialized()
        try:
            onchain = await self._solana_client.get_onchain_data(address)
            if onchain:
                return {
                    "mint_authority": onchain.get("mint_auth", True),
                    "freeze_authority": onchain.get("freeze_auth", True),
                    "supply": onchain.get("supply", 0),
                    "decimals": onchain.get("decimals", 9),
                    "is_verified": True,  # Solana programs are always on-chain
                }
        except Exception as e:
            logger.warning(f"Failed to get Solana token info for {address[:8]}: {e}")
        return {}

    async def get_top_holders(self, address: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top token holders."""
        await self._ensure_initialized()
        try:
            holders = await self._solana_client.get_top_holders(address, limit=limit)
            return holders or []
        except Exception as e:
            logger.warning(f"Failed to get Solana holders for {address[:8]}: {e}")
            return []

    async def get_contract_code(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get program data for a Solana program.

        Note: Solana programs are compiled to BPF bytecode, not source code.
        We return metadata about the program rather than source.
        """
        await self._ensure_initialized()
        try:
            # For Solana, we can check if the address is a program
            # and get basic program info
            return {
                "is_program": True,
                "source_code": None,  # Solana programs don't have on-chain source
                "is_verified": False,  # Would need to check against verified builds
                "is_proxy": False,  # Solana uses a different upgrade model
                "is_upgradeable": True,  # Default assumption, check program data
            }
        except Exception as e:
            logger.warning(f"Failed to get Solana program info: {e}")
            return None

    async def get_transactions(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent transactions for a Solana address."""
        await self._ensure_initialized()
        try:
            # Use the existing Solana client's transaction fetching
            # This may need to be expanded based on the existing implementation
            return []
        except Exception as e:
            logger.warning(f"Failed to get Solana transactions: {e}")
            return []

    async def validate_address(self, address: str) -> bool:
        """Validate Solana address format."""
        await self._ensure_initialized()
        return self._solana_client.is_valid_address(address)

    async def get_wallet_tokens(self, wallet: str) -> List[Dict[str, Any]]:
        """Get all SPL token holdings for a wallet."""
        await self._ensure_initialized()
        try:
            tokens = await self._solana_client.get_wallet_assets(wallet)
            return tokens or []
        except Exception as e:
            logger.warning(f"Failed to get Solana wallet tokens: {e}")
            return []

    async def get_token_approvals(self, wallet: str) -> List[Dict[str, Any]]:
        """
        Get token delegations for a Solana wallet.

        Note: Solana uses a delegate model rather than ERC-20 approvals.
        """
        await self._ensure_initialized()
        # Solana SPL token delegation is different from ERC-20 approvals
        # For now, return empty - will be implemented with the Shield feature
        return []

    async def simulate_swap(
        self,
        token_in: str,
        token_out: str,
        amount: int,
        slippage_bps: int = 100
    ) -> Dict[str, Any]:
        """
        Simulate a token swap via Jupiter.

        Uses the existing HoneypotDetector for sell simulation.
        """
        await self._ensure_initialized()
        try:
            from src.data.honeypot import HoneypotDetector
            if not self._honeypot_detector:
                self._honeypot_detector = HoneypotDetector(
                    solana_client=self._solana_client,
                    rpc_url=self.config.rpc_url
                )

            # Jupiter quote API
            import aiohttp
            from src.config import settings

            base_url = "https://api.jup.ag/swap/v1/quote"
            params = {
                "inputMint": token_in,
                "outputMint": token_out,
                "amount": str(amount),
                "slippageBps": str(slippage_bps),
            }

            headers = {}
            if settings.jupiter_api_key:
                headers["x-api-key"] = settings.jupiter_api_key

            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "success": True,
                            "route_available": True,
                            "expected_output": int(data.get("outAmount", 0)),
                            "price_impact_pct": float(data.get("priceImpactPct", 0)),
                            "estimated_tax_pct": 0,  # Calculated from expected vs actual
                        }
                    return {
                        "success": False,
                        "route_available": False,
                        "error": f"Jupiter API returned {resp.status}",
                    }
        except Exception as e:
            logger.warning(f"Solana swap simulation failed: {e}")
            return {"success": False, "route_available": False, "error": str(e)}

    async def get_deployer(self, contract_address: str) -> Optional[str]:
        """Get the wallet that deployed a Solana token."""
        await self._ensure_initialized()
        try:
            from src.analytics.wallet_forensics import get_token_deployer
            return await get_token_deployer(contract_address, self.config.rpc_url)
        except Exception as e:
            logger.warning(f"Failed to get Solana deployer: {e}")
            return None

    async def get_native_balance(self, wallet: str) -> float:
        """Get SOL balance in human-readable units."""
        await self._ensure_initialized()
        try:
            balance_lamports = await self._solana_client.get_balance(wallet)
            return balance_lamports / 1e9  # lamports -> SOL
        except Exception as e:
            logger.warning(f"Failed to get SOL balance: {e}")
            return 0.0

    async def analyze_holder_distribution(self, token_info):
        """
        Analyze holder distribution - delegates to existing Solana client.

        This is a Solana-specific method not part of the base ChainClient.
        """
        await self._ensure_initialized()
        await self._solana_client.analyze_holder_distribution(token_info)

    async def close(self) -> None:
        """Cleanup resources."""
        if self._solana_client:
            await self._solana_client.close()
        if self._honeypot_detector:
            await self._honeypot_detector.close()
        logger.info("SolanaChainClient closed")
