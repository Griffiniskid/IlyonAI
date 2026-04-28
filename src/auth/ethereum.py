"""Ethereum (EVM) signature verification for MetaMask login."""
from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct


def verify_ethereum_signature(address: str, message: str, signature: str) -> bool:
    """Verify an EIP-191 personal-signature recovered address matches *address*."""
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=signature
        )
        return recovered.lower() == address.lower()
    except Exception:
        return False
