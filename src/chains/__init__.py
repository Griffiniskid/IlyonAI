"""
Multi-chain abstraction layer for Ilyon AI.

Provides a unified interface for interacting with different blockchains
including Solana, Ethereum, and all major EVM chains.
"""

from src.chains.base import ChainType, ChainConfig, ChainClient
from src.chains.registry import ChainRegistry
from src.chains.address import AddressResolver

__all__ = [
    "ChainType",
    "ChainConfig", 
    "ChainClient",
    "ChainRegistry",
    "AddressResolver",
]
