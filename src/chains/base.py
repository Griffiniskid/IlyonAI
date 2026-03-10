"""
Base classes and enums for the multi-chain abstraction layer.

Defines ChainType enum, ChainConfig dataclass, and the abstract ChainClient
that all chain-specific clients must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChainType(Enum):
    """Supported blockchain networks."""
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    BASE = "base"
    ARBITRUM = "arbitrum"
    BSC = "bsc"
    POLYGON = "polygon"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"

    @property
    def display_name(self) -> str:
        """Human-readable chain name."""
        names = {
            "solana": "Solana",
            "ethereum": "Ethereum",
            "base": "Base",
            "arbitrum": "Arbitrum",
            "bsc": "BNB Smart Chain",
            "polygon": "Polygon",
            "optimism": "Optimism",
            "avalanche": "Avalanche",
        }
        return names.get(self.value, self.value.title())

    @property
    def is_evm(self) -> bool:
        """Whether this is an EVM-compatible chain."""
        return self != ChainType.SOLANA

    @property
    def chain_id(self) -> Optional[int]:
        """EVM chain ID. None for non-EVM chains."""
        chain_ids = {
            "ethereum": 1,
            "bsc": 56,
            "polygon": 137,
            "arbitrum": 42161,
            "optimism": 10,
            "avalanche": 43114,
            "base": 8453,
        }
        return chain_ids.get(self.value)

    @property
    def native_token_symbol(self) -> str:
        """Native gas token symbol."""
        symbols = {
            "solana": "SOL",
            "ethereum": "ETH",
            "base": "ETH",
            "arbitrum": "ETH",
            "bsc": "BNB",
            "polygon": "POL",
            "optimism": "ETH",
            "avalanche": "AVAX",
        }
        return symbols.get(self.value, "ETH")

    @property
    def native_token_decimals(self) -> int:
        """Native token decimals."""
        if self == ChainType.SOLANA:
            return 9
        return 18  # All EVM chains use 18 decimals for native token

    @property
    def icon_url(self) -> str:
        """Chain icon URL for UI display."""
        base = "https://raw.githubusercontent.com/trustwallet/assets/master/blockchains"
        mapping = {
            "solana": f"{base}/solana/info/logo.png",
            "ethereum": f"{base}/ethereum/info/logo.png",
            "base": f"{base}/base/info/logo.png",
            "arbitrum": f"{base}/arbitrum/info/logo.png",
            "bsc": f"{base}/smartchain/info/logo.png",
            "polygon": f"{base}/polygon/info/logo.png",
            "optimism": f"{base}/optimism/info/logo.png",
            "avalanche": f"{base}/avalanchec/info/logo.png",
        }
        return mapping.get(self.value, "")


@dataclass
class ChainConfig:
    """
    Configuration for a specific blockchain network.

    Contains RPC endpoints, block explorer URLs, DEX router addresses,
    and other chain-specific settings.
    """
    chain_type: ChainType
    rpc_url: str
    rpc_url_fallback: Optional[str] = None

    # Block explorer
    explorer_url: str = ""
    explorer_api_url: str = ""
    explorer_api_key: Optional[str] = None

    # DEX configuration
    primary_dex: str = ""
    dex_router_address: Optional[str] = None
    wrapped_native_address: Optional[str] = None

    # Stablecoin addresses (for price references)
    usdc_address: Optional[str] = None
    usdt_address: Optional[str] = None

    # Chain-specific settings
    block_time_seconds: float = 12.0
    supports_contract_verification: bool = True
    supports_token_approvals: bool = True  # False for Solana (uses delegate model)

    # Rate limiting
    max_requests_per_second: int = 5


# Pre-configured chain configs
EVM_CHAIN_CONFIGS: Dict[ChainType, Dict[str, Any]] = {
    ChainType.ETHEREUM: {
        "explorer_url": "https://etherscan.io",
        "explorer_api_url": "https://api.etherscan.io/api",
        "primary_dex": "Uniswap V3",
        "dex_router_address": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "wrapped_native_address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "usdc_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "usdt_address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "block_time_seconds": 12.0,
    },
    ChainType.BASE: {
        "explorer_url": "https://basescan.org",
        "explorer_api_url": "https://api.basescan.org/api",
        "primary_dex": "Uniswap V3",
        "dex_router_address": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "wrapped_native_address": "0x4200000000000000000000000000000000000006",
        "usdc_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "usdt_address": None,
        "block_time_seconds": 2.0,
    },
    ChainType.ARBITRUM: {
        "explorer_url": "https://arbiscan.io",
        "explorer_api_url": "https://api.arbiscan.io/api",
        "primary_dex": "Uniswap V3",
        "dex_router_address": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "wrapped_native_address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
        "usdc_address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "usdt_address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "block_time_seconds": 0.25,
    },
    ChainType.BSC: {
        "explorer_url": "https://bscscan.com",
        "explorer_api_url": "https://api.bscscan.com/api",
        "primary_dex": "PancakeSwap V3",
        "dex_router_address": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
        "wrapped_native_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "usdc_address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
        "usdt_address": "0x55d398326f99059fF775485246999027B3197955",
        "block_time_seconds": 3.0,
    },
    ChainType.POLYGON: {
        "explorer_url": "https://polygonscan.com",
        "explorer_api_url": "https://api.polygonscan.com/api",
        "primary_dex": "QuickSwap",
        "dex_router_address": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        "wrapped_native_address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "usdc_address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "usdt_address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "block_time_seconds": 2.0,
    },
    ChainType.OPTIMISM: {
        "explorer_url": "https://optimistic.etherscan.io",
        "explorer_api_url": "https://api-optimistic.etherscan.io/api",
        "primary_dex": "Uniswap V3",
        "dex_router_address": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "wrapped_native_address": "0x4200000000000000000000000000000000000006",
        "usdc_address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        "usdt_address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "block_time_seconds": 2.0,
    },
    ChainType.AVALANCHE: {
        "explorer_url": "https://snowtrace.io",
        "explorer_api_url": "https://api.snowtrace.io/api",
        "primary_dex": "Trader Joe",
        "dex_router_address": "0x60aE616a2155Ee3d9A68541Ba4544862310933d4",
        "wrapped_native_address": "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
        "usdc_address": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
        "usdt_address": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
        "block_time_seconds": 2.0,
    },
}


class ChainClient(ABC):
    """
    Abstract base class for blockchain clients.

    All chain-specific clients (Solana, EVM) must implement this interface
    to provide a unified API for the analyzer.
    """

    def __init__(self, config: ChainConfig):
        self.config = config
        self.chain_type = config.chain_type

    @property
    def chain(self) -> ChainType:
        return self.chain_type

    @abstractmethod
    async def get_token_info(self, address: str) -> Dict[str, Any]:
        """
        Get basic token information from on-chain data.

        Returns dict with keys: name, symbol, decimals, supply, 
        mint_authority (Solana) or owner (EVM), etc.
        """
        ...

    @abstractmethod
    async def get_top_holders(self, address: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top token holders with balances and percentages.

        Returns list of dicts with: address, balance, percentage.
        """
        ...

    @abstractmethod
    async def get_contract_code(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get contract source code or bytecode.

        Returns dict with: source_code, abi, compiler_version, is_verified,
        is_proxy, implementation_address (if proxy).
        Returns None if address is not a contract.
        """
        ...

    @abstractmethod
    async def get_transactions(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent transactions for an address.

        Returns list of dicts with: hash, from, to, value, timestamp, type.
        """
        ...

    @abstractmethod
    async def validate_address(self, address: str) -> bool:
        """Validate that the address is a valid format for this chain."""
        ...

    @abstractmethod
    async def get_wallet_tokens(self, wallet: str) -> List[Dict[str, Any]]:
        """
        Get all token holdings for a wallet address.

        Returns list of dicts with: mint/address, name, symbol, amount,
        value_usd, price_usd, logo.
        """
        ...

    @abstractmethod
    async def get_token_approvals(self, wallet: str) -> List[Dict[str, Any]]:
        """
        Get all token approvals/delegations for a wallet.

        Returns list of dicts with: token_address, token_symbol, spender,
        allowance, is_unlimited.
        """
        ...

    @abstractmethod
    async def simulate_swap(
        self,
        token_in: str,
        token_out: str,
        amount: int,
        slippage_bps: int = 100
    ) -> Dict[str, Any]:
        """
        Simulate a token swap to detect honeypots and measure sell tax.

        Returns dict with: success, route_available, expected_output,
        price_impact_pct, estimated_tax_pct.
        """
        ...

    @abstractmethod
    async def get_deployer(self, contract_address: str) -> Optional[str]:
        """
        Get the wallet that deployed a token/contract.

        Returns deployer address or None if not found.
        """
        ...

    @abstractmethod
    async def get_native_balance(self, wallet: str) -> float:
        """Get native token balance (SOL, ETH, BNB, etc.) in human-readable units."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources (HTTP sessions, connections, etc.)."""
        ...

    def get_explorer_url(self, address: str, type: str = "address") -> str:
        """
        Get block explorer URL for an address or transaction.

        Args:
            address: The address or transaction hash.
            type: 'address', 'tx', or 'token'.
        """
        base = self.config.explorer_url
        if type == "tx":
            return f"{base}/tx/{address}"
        elif type == "token":
            return f"{base}/token/{address}"
        return f"{base}/address/{address}"
