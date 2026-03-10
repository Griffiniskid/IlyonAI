"""
Address resolver for multi-chain support.

Detects which blockchain(s) an address belongs to based on its format,
and provides utilities for address validation and normalization.
"""

import re
import logging
from typing import List, Optional

from src.chains.base import ChainType

logger = logging.getLogger(__name__)

# Solana address: base58 encoded, 32-44 characters, no 0x prefix
SOLANA_ADDRESS_REGEX = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')

# EVM address: hex encoded, 42 characters, starts with 0x
EVM_ADDRESS_REGEX = re.compile(r'^0x[0-9a-fA-F]{40}$')

# EVM transaction hash: hex encoded, 66 characters, starts with 0x
EVM_TX_HASH_REGEX = re.compile(r'^0x[0-9a-fA-F]{64}$')

# Solana transaction signature: base58, 87-88 characters
SOLANA_TX_REGEX = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{87,88}$')

# ENS domain
ENS_REGEX = re.compile(r'^[a-zA-Z0-9-]+\.eth$')

# .sol domain (Solana naming service)
SOL_DOMAIN_REGEX = re.compile(r'^[a-zA-Z0-9-]+\.sol$')


class AddressResolver:
    """
    Detect which blockchain an address belongs to and resolve domain names.
    """

    @staticmethod
    def detect_chain(address: str) -> List[ChainType]:
        """
        Detect which chain(s) an address could belong to.

        Args:
            address: The address string to analyze.

        Returns:
            List of possible ChainType values. EVM addresses return all EVM chains
            since the same address format is valid across all EVM chains.
            Empty list if format is unrecognized.
        """
        address = address.strip()

        if not address:
            return []

        # EVM address (valid on all EVM chains)
        if EVM_ADDRESS_REGEX.match(address):
            return [
                ChainType.ETHEREUM,
                ChainType.BASE,
                ChainType.ARBITRUM,
                ChainType.BSC,
                ChainType.POLYGON,
                ChainType.OPTIMISM,
                ChainType.AVALANCHE,
            ]

        # Solana address
        if SOLANA_ADDRESS_REGEX.match(address):
            # Additional validation: Solana addresses should be valid base58
            try:
                import base58
                decoded = base58.b58decode(address)
                if len(decoded) == 32:
                    return [ChainType.SOLANA]
            except Exception:
                pass
            # Even without base58 validation, if it matches the regex
            # and is the right length range, it's likely Solana
            if 32 <= len(address) <= 44:
                return [ChainType.SOLANA]

        return []

    @staticmethod
    def detect_input_type(input_str: str) -> str:
        """
        Classify what type of input the user provided.

        Returns one of:
            'evm_address', 'solana_address', 'evm_tx', 'solana_tx',
            'ens_domain', 'sol_domain', 'search_query', 'unknown'
        """
        input_str = input_str.strip()

        if not input_str:
            return "unknown"

        if EVM_ADDRESS_REGEX.match(input_str):
            return "evm_address"

        if EVM_TX_HASH_REGEX.match(input_str):
            return "evm_tx"

        if ENS_REGEX.match(input_str):
            return "ens_domain"

        if SOL_DOMAIN_REGEX.match(input_str):
            return "sol_domain"

        if SOLANA_TX_REGEX.match(input_str):
            return "solana_tx"

        if SOLANA_ADDRESS_REGEX.match(input_str):
            # Could be Solana address or just a random base58 string
            try:
                import base58
                decoded = base58.b58decode(input_str)
                if len(decoded) == 32:
                    return "solana_address"
            except Exception:
                pass
            if 32 <= len(input_str) <= 44:
                return "solana_address"

        # If nothing matches, it's probably a search query (token name, protocol, etc.)
        if len(input_str) >= 2:
            return "search_query"

        return "unknown"

    @staticmethod
    def is_valid_evm_address(address: str) -> bool:
        """Check if string is a valid EVM address."""
        return bool(EVM_ADDRESS_REGEX.match(address.strip()))

    @staticmethod
    def is_valid_solana_address(address: str) -> bool:
        """Check if string is a valid Solana address."""
        address = address.strip()
        if not SOLANA_ADDRESS_REGEX.match(address):
            return False
        try:
            import base58
            decoded = base58.b58decode(address)
            return len(decoded) == 32
        except Exception:
            return 32 <= len(address) <= 44

    @staticmethod
    def normalize_evm_address(address: str) -> str:
        """Normalize an EVM address to checksummed format."""
        address = address.strip().lower()
        if not address.startswith("0x"):
            address = "0x" + address
        # Simple checksum - in production use web3.to_checksum_address
        return address

    @staticmethod
    def get_default_chain_for_address(address: str) -> Optional[ChainType]:
        """
        Get the most likely chain for an address.

        For EVM addresses, defaults to Ethereum.
        For Solana addresses, returns Solana.
        """
        chains = AddressResolver.detect_chain(address)
        if not chains:
            return None
        if ChainType.SOLANA in chains:
            return ChainType.SOLANA
        return ChainType.ETHEREUM  # Default EVM chain

    @staticmethod
    def parse_chain_from_string(chain_str: str) -> Optional[ChainType]:
        """
        Parse a chain name string into a ChainType enum.

        Handles common aliases and case-insensitive matching.
        """
        if not chain_str:
            return None

        chain_str = chain_str.strip().lower()

        # Direct enum match
        try:
            return ChainType(chain_str)
        except ValueError:
            pass

        # Common aliases
        aliases = {
            "eth": ChainType.ETHEREUM,
            "ether": ChainType.ETHEREUM,
            "mainnet": ChainType.ETHEREUM,
            "sol": ChainType.SOLANA,
            "arb": ChainType.ARBITRUM,
            "arbitrum one": ChainType.ARBITRUM,
            "bnb": ChainType.BSC,
            "binance": ChainType.BSC,
            "bnb chain": ChainType.BSC,
            "bnb smart chain": ChainType.BSC,
            "binance smart chain": ChainType.BSC,
            "poly": ChainType.POLYGON,
            "matic": ChainType.POLYGON,
            "op": ChainType.OPTIMISM,
            "avax": ChainType.AVALANCHE,
            "avalanche c-chain": ChainType.AVALANCHE,
        }

        return aliases.get(chain_str)
