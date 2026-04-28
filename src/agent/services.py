"""Service initialization for agent tools.

Creates instances of all data clients and makes them available to the agent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from src.config import settings

logger = logging.getLogger(__name__)


class AgentServices:
    """Bundle of data services for the agent."""
    
    def __init__(self):
        self.price = None
        self.defillama = None
        self.defi_intelligence = None
        self.jupiter = None
        self.dexscreener = None
        self.moralis = None
        self.solana = None
        self.initialized = False
    
    async def initialize(self):
        """Initialize all service clients."""
        if self.initialized:
            return
        
        try:
            # Initialize CoinGecko (free tier, no key needed)
            from src.data.coingecko import CoinGeckoClient
            self.price = CoinGeckoClient()
            logger.info("CoinGecko client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize CoinGecko: {e}")
        
        try:
            # Initialize DefiLlama (no key needed)
            from src.data.defillama import DefiLlamaClient
            self.defillama = DefiLlamaClient()
            logger.info("DefiLlama client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize DefiLlama: {e}")

        try:
            from src.defi.intelligence_engine import DefiIntelligenceEngine

            self.defi_intelligence = DefiIntelligenceEngine(llama=self.defillama)
            logger.info("DeFi intelligence engine initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize DeFi intelligence engine: {e}")
        
        try:
            # Initialize Jupiter (uses API key if available)
            from src.data.jupiter import JupiterClient
            self.jupiter = JupiterClient(
                api_key=settings.jupiter_api_key if hasattr(settings, 'jupiter_api_key') else None,
                timeout=settings.jupiter_api_timeout if hasattr(settings, 'jupiter_api_timeout') else 15
            )
            logger.info("Jupiter client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Jupiter: {e}")
        
        try:
            # Initialize DexScreener (no key needed)
            from src.data.dexscreener import DexScreenerClient
            self.dexscreener = DexScreenerClient()
            logger.info("DexScreener client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize DexScreener: {e}")
        
        try:
            # Initialize Moralis (uses API key)
            from src.data.moralis import MoralisClient
            self.moralis = MoralisClient(api_key=settings.moralis_api_key)
            logger.info("Moralis client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Moralis: {e}")
        
        try:
            # Initialize Solana client
            from src.data.solana import SolanaClient
            self.solana = SolanaClient(
                rpc_url=settings.solana_rpc_url,
                helius_api_key=settings.helius_api_key if hasattr(settings, 'helius_api_key') else None
            )
            logger.info("Solana client initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Solana: {e}")
        
        self.initialized = True
    
    def to_namespace(self) -> Any:
        """Convert services to namespace object for ToolContext."""
        import types
        ns = types.SimpleNamespace()
        ns.price = self.price
        ns.defillama = self.defillama
        ns.defi_intelligence = self.defi_intelligence
        ns.jupiter = self.jupiter
        ns.dexscreener = self.dexscreener
        ns.moralis = self.moralis
        ns.solana = self.solana
        ns.opportunity = self.defillama  # Alias for yield/staking data
        ns.quote = self.jupiter  # Alias for swap quotes
        ns.portfolio = self.moralis  # Alias for portfolio data
        return ns


# Global service instance (lazy initialization)
_services = None


async def get_agent_services() -> AgentServices:
    """Get or create the global agent services instance."""
    global _services
    if _services is None:
        _services = AgentServices()
        await _services.initialize()
    return _services
