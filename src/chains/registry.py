"""
Chain registry - manages chain client instances and configurations.

Provides a centralized way to get chain clients, configs, and metadata
for all supported blockchains.
"""

import logging
from typing import Dict, List, Optional

from src.chains.base import ChainType, ChainConfig, ChainClient, EVM_CHAIN_CONFIGS

logger = logging.getLogger(__name__)


class ChainRegistry:
    """
    Central registry for all supported blockchain networks.

    Manages chain configurations, client instances, and provides
    lookup utilities. Implements lazy initialization - clients are
    only created when first requested.
    """

    _instance: Optional["ChainRegistry"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_bootstrapped", False):
            return
        self._configs: Dict[ChainType, ChainConfig] = {}
        self._clients: Dict[ChainType, ChainClient] = {}
        self._initialized = False
        self._bootstrapped = True

    @classmethod
    def get_instance(cls) -> "ChainRegistry":
        """Get the singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self, settings) -> None:
        """
        Initialize all chain configurations from application settings.

        Args:
            settings: Application settings with RPC URLs and API keys.
        """
        if self._initialized:
            return

        # Solana
        self._configs[ChainType.SOLANA] = ChainConfig(
            chain_type=ChainType.SOLANA,
            rpc_url=settings.solana_rpc_url,
            explorer_url="https://solscan.io",
            explorer_api_url="https://api.solscan.io",
            primary_dex="Jupiter",
            wrapped_native_address="So11111111111111111111111111111111111111112",
            usdc_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            usdt_address="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            block_time_seconds=0.4,
            supports_contract_verification=True,
            supports_token_approvals=False,  # Solana uses delegate model
        )

        # EVM chains
        rpc_mapping = {
            ChainType.ETHEREUM: settings.ethereum_rpc_url,
            ChainType.BASE: settings.base_rpc_url,
            ChainType.ARBITRUM: settings.arbitrum_rpc_url,
            ChainType.BSC: settings.bsc_rpc_url,
            ChainType.POLYGON: settings.polygon_rpc_url,
            ChainType.OPTIMISM: settings.optimism_rpc_url,
            ChainType.AVALANCHE: settings.avalanche_rpc_url,
        }

        explorer_api_keys = {
            ChainType.ETHEREUM: settings.etherscan_api_key,
            ChainType.BSC: settings.bscscan_api_key,
            ChainType.ARBITRUM: settings.arbiscan_api_key,
            ChainType.POLYGON: settings.polygonscan_api_key,
            ChainType.BASE: settings.basescan_api_key,
            ChainType.OPTIMISM: settings.optimism_etherscan_api_key,
            ChainType.AVALANCHE: settings.snowtrace_api_key,
        }

        for chain_type, rpc_url in rpc_mapping.items():
            chain_defaults = EVM_CHAIN_CONFIGS.get(chain_type, {})
            self._configs[chain_type] = ChainConfig(
                chain_type=chain_type,
                rpc_url=rpc_url,
                explorer_url=chain_defaults.get("explorer_url", ""),
                explorer_api_url=chain_defaults.get("explorer_api_url", ""),
                explorer_api_key=explorer_api_keys.get(chain_type),
                primary_dex=chain_defaults.get("primary_dex", ""),
                dex_router_address=chain_defaults.get("dex_router_address"),
                wrapped_native_address=chain_defaults.get("wrapped_native_address"),
                usdc_address=chain_defaults.get("usdc_address"),
                usdt_address=chain_defaults.get("usdt_address"),
                block_time_seconds=chain_defaults.get("block_time_seconds", 12.0),
            )

        self._initialized = True
        logger.info(
            f"ChainRegistry initialized with {len(self._configs)} chains: "
            f"{', '.join(c.display_name for c in self._configs.keys())}"
        )

    def get_config(self, chain: ChainType) -> ChainConfig:
        """
        Get configuration for a specific chain.

        Args:
            chain: The chain type.

        Returns:
            ChainConfig for the requested chain.

        Raises:
            ValueError: If chain is not configured.
        """
        if chain not in self._configs:
            raise ValueError(
                f"Chain '{chain.value}' is not configured. "
                f"Available: {[c.value for c in self._configs.keys()]}"
            )
        return self._configs[chain]

    def get_client(self, chain: ChainType) -> ChainClient:
        """
        Get or create a client for a specific chain.

        Lazily initializes clients on first request.

        Args:
            chain: The chain type.

        Returns:
            ChainClient instance for the requested chain.
        """
        if chain in self._clients:
            return self._clients[chain]

        config = self.get_config(chain)

        if chain == ChainType.SOLANA:
            from src.chains.solana.client import SolanaChainClient
            client = SolanaChainClient(config)
        else:
            from src.chains.evm.client import EVMChainClient
            client = EVMChainClient(config)

        self._clients[chain] = client
        logger.info(f"Created {chain.display_name} chain client")
        return client

    def get_all_chains(self) -> List[ChainType]:
        """Get list of all configured chains."""
        return list(self._configs.keys())

    def get_evm_chains(self) -> List[ChainType]:
        """Get list of configured EVM chains."""
        return [c for c in self._configs.keys() if c.is_evm]

    def get_chain_info(self, chain: ChainType) -> Dict:
        """
        Get display information about a chain for API responses.

        Returns dict suitable for JSON serialization.
        """
        config = self.get_config(chain)
        return {
            "id": chain.value,
            "name": chain.display_name,
            "chain_id": chain.chain_id,
            "is_evm": chain.is_evm,
            "native_token": chain.native_token_symbol,
            "explorer_url": config.explorer_url,
            "primary_dex": config.primary_dex,
            "icon_url": chain.icon_url,
        }

    def get_all_chains_info(self) -> List[Dict]:
        """Get display information for all configured chains."""
        return [self.get_chain_info(chain) for chain in self._configs.keys()]

    async def close_all(self) -> None:
        """Close all active chain clients."""
        for chain_type, client in self._clients.items():
            try:
                await client.close()
                logger.info(f"Closed {chain_type.display_name} client")
            except Exception as e:
                logger.warning(f"Error closing {chain_type.display_name} client: {e}")
        self._clients.clear()
