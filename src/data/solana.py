"""
Solana RPC client for on-chain token data and holder analysis.

This module provides an async client for interacting with Solana RPC
to fetch token mint information, holder data, analyze wallet distribution,
and simulate transactions for honeypot detection.

NOTE: This is the core blockchain client for AI Sentinel.
Exclusively designed for Solana mainnet - no other chains supported.
"""

import logging
import base64
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from src.core.models import TokenInfo

# Retry configuration for rate-limited RPC calls
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff delays in seconds


@dataclass
class SimulationResult:
    """Result of transaction simulation."""
    success: bool
    error: Optional[str] = None
    error_code: Optional[int] = None
    logs: List[str] = field(default_factory=list)
    units_consumed: int = 0
    return_data: Optional[Dict] = None

logger = logging.getLogger(__name__)


class SolanaClient:
    """
    Async client for Solana RPC operations.

    Handles on-chain token data fetching including mint authority,
    freeze authority, token supply, and top holder analysis.
    """

    # Solana program addresses
    TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

    # Known addresses to exclude from holder analysis
    KNOWN_ADDRESSES = {
        '5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1',  # Raydium Authority V4
        'So11111111111111111111111111111111111111112',   # Wrapped SOL
        '1nc1nerator11111111111111111111111111111111',   # Burn address
        '11111111111111111111111111111111',              # System program
    }

    def __init__(self, rpc_url: str, helius_api_key: Optional[str] = None):
        """
        Initialize Solana RPC client.

        Args:
            rpc_url: Solana RPC endpoint URL
            helius_api_key: Optional Helius API key for enhanced holder data
        """
        self.rpc_url = rpc_url
        self.helius_api_key = helius_api_key
        self._client: Optional[AsyncClient] = None

    async def _ensure_connected(self):
        """Ensure RPC client is connected"""
        if not self._client:
            self._client = AsyncClient(self.rpc_url, commitment=Commitment("confirmed"))
            logger.info("✅ Solana RPC connected")

    async def close(self):
        """Close the RPC client connection"""
        if self._client:
            await self._client.close()
            self._client = None

    async def _get_holders_via_helius(self, address: str, limit: int = 20) -> List[Dict]:
        """
        Fetch token holders using Helius API (more reliable than standard RPC).

        Args:
            address: Token mint address
            limit: Maximum holders to fetch

        Returns:
            List of holder dicts with 'address' and 'amount'
        """
        if not self.helius_api_key:
            return []

        url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"

        # Use Helius enhanced RPC for token largest accounts
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [address]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Helius API returned {resp.status}")
                        return []

                    data = await resp.json()

                    if 'error' in data:
                        logger.warning(f"Helius API error: {data['error']}")
                        return []

                    result = data.get('result', {})
                    value = result.get('value', [])

                    holders = []
                    for account in value[:limit]:
                        try:
                            amount = 0.0

                            # Helius/Solana RPC returns uiAmount at account level (not nested under amount)
                            # Format: {"address": "...", "amount": "raw", "decimals": 9, "uiAmount": 0.123, "uiAmountString": "0.123"}
                            if 'uiAmount' in account and account['uiAmount'] is not None:
                                amount = float(account['uiAmount'])
                            elif 'ui_amount' in account and account['ui_amount'] is not None:
                                amount = float(account['ui_amount'])
                            elif 'uiAmountString' in account and account['uiAmountString']:
                                amount = float(account['uiAmountString'])
                            elif 'amount' in account:
                                # Fallback: raw amount - need to adjust by decimals
                                raw_amount = account.get('amount', 0)
                                decimals = account.get('decimals', 9)
                                if isinstance(raw_amount, str):
                                    raw_amount = int(raw_amount)
                                amount = raw_amount / (10 ** decimals)

                            holders.append({
                                'address': account.get('address', ''),
                                'amount': amount
                            })
                        except Exception as e:
                            logger.debug(f"Error parsing Helius holder: {e}")
                            continue

                    if holders:
                        logger.info(f"✅ Helius: Found {len(holders)} holders for {address[:8]}")

                    return holders

        except Exception as e:
            logger.warning(f"Helius holder fetch failed: {e}")
            return []

    def is_valid_address(self, address: str) -> bool:
        """
        Validate if a string is a valid Solana address.

        Args:
            address: String to validate

        Returns:
            True if valid Solana address, False otherwise
        """
        try:
            if len(address) < 32 or len(address) > 44:
                return False
            Pubkey.from_string(address)
            return True
        except Exception:
            return False

    async def get_onchain_data(self, address: str) -> Dict:
        """
        Get on-chain token mint data from Solana.

        Fetches mint authority status, freeze authority status,
        total supply, and decimals directly from the blockchain.

        Args:
            address: Solana token mint address

        Returns:
            Dict with structure:
            {
                'mint_auth': bool,      # Mint authority enabled
                'freeze_auth': bool,    # Freeze authority enabled
                'supply': int,          # Total supply (raw)
                'decimals': int         # Token decimals
            }
        """
        await self._ensure_connected()

        # Default result
        result = {
            'mint_auth': True,
            'freeze_auth': True,
            'supply': 0,
            'decimals': 9
        }

        try:
            pubkey = Pubkey.from_string(address)
            info = await self._client.get_account_info(pubkey)

            if not info.value:
                logger.warning(f"No account info for {address[:8]}")
                return result

            data = info.value.data
            owner = str(info.value.owner)

            # Verify this is a token mint account
            if owner not in [self.TOKEN_PROGRAM, self.TOKEN_2022]:
                logger.warning(f"Address {address[:8]} is not a token mint")
                return result

            # Parse token mint data (minimum 82 bytes required)
            if len(data) < 82:
                logger.warning(f"Insufficient data length for {address[:8]}")
                return result

            # Parse mint account structure:
            # Bytes 0-4: mint_authority option (0 = None, 1 = Some)
            # Bytes 36-44: supply (u64)
            # Byte 44: decimals (u8)
            # Bytes 46-50: freeze_authority option (0 = None, 1 = Some)

            result['mint_auth'] = int.from_bytes(data[0:4], 'little') == 1
            result['supply'] = int.from_bytes(data[36:44], 'little')
            result['decimals'] = data[44]
            result['freeze_auth'] = int.from_bytes(data[46:50], 'little') == 1

            logger.info(
                f"✅ On-chain data for {address[:8]}: "
                f"Mint={result['mint_auth']}, "
                f"Freeze={result['freeze_auth']}, "
                f"Supply={result['supply']}"
            )

        except Exception as e:
            logger.error(f"Error fetching on-chain data for {address[:8]}: {e}", exc_info=True)

        return result

    async def get_top_holders(self, address: str, limit: int = 20) -> List[Dict]:
        """
        Get top token holders from Solana.

        Fetches the largest token account balances for the given mint.
        Uses Helius API if available, falls back to standard RPC with retry logic.

        Args:
            address: Solana token mint address
            limit: Maximum number of holders to return (default: 20)

        Returns:
            List of dicts with structure:
            [
                {
                    'address': str,  # Token account address
                    'amount': float  # Token amount (UI format)
                },
                ...
            ]
        """
        # Try Helius first if available (more reliable, no rate limits)
        if self.helius_api_key:
            helius_holders = await self._get_holders_via_helius(address, limit)
            if helius_holders:
                return helius_holders
            logger.debug("Helius returned no holders, trying standard RPC")

        await self._ensure_connected()

        # Retry loop with exponential backoff for rate limiting (429 errors)
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                pubkey = Pubkey.from_string(address)
                resp = await self._client.get_token_largest_accounts(pubkey)

                if not resp or not resp.value:
                    logger.warning(f"⚠️ No holder data returned for {address[:8]}")
                    return []

                holders = []
                for idx, account in enumerate(resp.value[:limit]):
                    try:
                        amount = 0.0

                        # Debug: log the raw account structure for first holder
                        if idx == 0:
                            logger.debug(f"Raw holder account structure: {type(account)}, attrs: {dir(account)}")
                            if hasattr(account, 'amount'):
                                logger.debug(f"Amount structure: {type(account.amount)}, attrs: {dir(account.amount)}")

                        # Parse amount from response - try multiple approaches
                        if hasattr(account, 'amount'):
                            amt_obj = account.amount

                            # Approach 1: ui_amount (float)
                            if hasattr(amt_obj, 'ui_amount') and amt_obj.ui_amount is not None:
                                amount = float(amt_obj.ui_amount)

                            # Approach 2: ui_amount_string (string)
                            elif hasattr(amt_obj, 'ui_amount_string') and amt_obj.ui_amount_string:
                                try:
                                    amount = float(amt_obj.ui_amount_string)
                                except (ValueError, TypeError):
                                    pass

                            # Approach 3: uiAmount (camelCase variant)
                            elif hasattr(amt_obj, 'uiAmount') and amt_obj.uiAmount is not None:
                                amount = float(amt_obj.uiAmount)

                            # Approach 4: Direct dict access
                            elif isinstance(amt_obj, dict):
                                amount = float(amt_obj.get('uiAmount') or amt_obj.get('ui_amount') or 0)

                        # Also try direct account attributes
                        elif hasattr(account, 'uiAmount') and account.uiAmount is not None:
                            amount = float(account.uiAmount)

                        holders.append({
                            'address': str(account.address),
                            'amount': amount
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing holder account {idx}: {e}")
                        continue

                # Log holder data for debugging
                if holders:
                    top_amount = holders[0].get('amount', 0) if holders else 0
                    total_amount = sum(h.get('amount', 0) for h in holders)
                    logger.info(
                        f"✅ Found {len(holders)} holders for {address[:8]}, "
                        f"top holder: {top_amount:,.2f}, total in top-{len(holders)}: {total_amount:,.2f}"
                    )
                else:
                    logger.warning(f"⚠️ Holders list empty for {address[:8]}")

                return holders

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if it's a rate limit error (429)
                if '429' in error_str or 'too many requests' in error_str or 'rate' in error_str:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(
                            f"⚠️ Rate limited on holder fetch for {address[:8]}, "
                            f"retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"❌ Rate limit exceeded after {MAX_RETRIES} attempts for {address[:8]}")
                else:
                    # Non-rate-limit error, don't retry
                    logger.error(f"❌ Error fetching holders for {address[:8]}: {e}", exc_info=True)
                    break

        logger.error(f"❌ Failed to fetch holders for {address[:8]} after retries: {last_error}")
        return []

    async def analyze_holder_distribution(self, token: TokenInfo) -> None:
        """
        Analyze token holder distribution for suspicious patterns.

        Modifies the TokenInfo object in-place with analysis results:
        - top_holder_pct: Percentage held by largest wallet
        - dev_wallet_risk: Whether top holder concentration is risky
        - suspicious_wallets: Number of suspicious wallets detected
        - holder_flags: List of warning messages

        Checks for:
        - High concentration in top wallets (>20% in one wallet)
        - Suspicious round number allocations
        - Related wallets with similar balances

        Args:
            token: TokenInfo object with top_holders already populated
        """
        # Debug logging
        logger.info(
            f"🔍 Starting holder analysis for {token.symbol}: "
            f"holders={len(token.top_holders) if token.top_holders else 0}, "
            f"supply={token.supply}, decimals={token.decimals}"
        )

        if not token.top_holders:
            logger.warning(f"⚠️ No holders data for {token.symbol}")
            return

        if token.supply <= 0:
            logger.warning(f"⚠️ Supply is 0 for {token.symbol}, cannot analyze holders")
            return

        total_supply = token.supply / (10 ** token.decimals)
        logger.debug(f"Total supply (UI): {total_supply:,.2f}")
        flags = []
        suspicious_count = 0

        # Track top-10 holder concentration
        top_10_concentration = 0.0

        for i, holder in enumerate(token.top_holders[:10]):
            addr = holder.get('address', '')
            amount = holder.get('amount', 0)

            # Skip known addresses (LP pools, burn addresses, etc.)
            if not addr or addr in self.KNOWN_ADDRESSES:
                continue

            pct = (amount / total_supply * 100) if total_supply > 0 else 0

            # Accumulate concentration for valid holders
            top_10_concentration += pct

            # ═══════════════════════════════════════════════════════════════
            # TOP-1 HOLDER ANALYSIS
            # ═══════════════════════════════════════════════════════════════
            if i == 0:
                token.top_holder_pct = pct

                # Risky: Top wallet holds >20%
                if pct > 20:
                    token.dev_wallet_risk = True
                    flags.append(f"🐋 Top wallet holds {pct:.1f}%")
                    suspicious_count += 1

                # Critical: Top wallet holds >50%
                if pct > 50:
                    flags.append(f"🚨 CRITICAL: One wallet = {pct:.1f}%")

            # ═══════════════════════════════════════════════════════════════
            # ROUND NUMBER DETECTION (often dev allocations)
            # ═══════════════════════════════════════════════════════════════
            if amount > 0:
                amount_str = f"{amount:.0f}"
                if len(amount_str) > 6:
                    # Count trailing zeros
                    zeros = len(amount_str) - len(amount_str.rstrip('0'))
                    if zeros >= 6:  # Many zeros = possibly dev allocation
                        suspicious_count += 1
                        if suspicious_count <= 3:
                            flags.append(f"⚠️ Wallet #{i+1}: suspiciously round amount")

            # ═══════════════════════════════════════════════════════════════
            # HIGH CONCENTRATION IN TOP WALLETS
            # ═══════════════════════════════════════════════════════════════
            if i < 5 and pct > 10:
                suspicious_count += 1
                if i > 0:  # Don't duplicate top-1 flag
                    flags.append(f"🐋 Wallet #{i+1} holds {pct:.1f}%")

        # ═══════════════════════════════════════════════════════════════
        # RELATED WALLETS DETECTION (similar balances)
        # ═══════════════════════════════════════════════════════════════
        if len(token.top_holders) >= 3:
            amounts = [h.get('amount', 0) for h in token.top_holders[:5] if h.get('amount', 0) > 0]
            if len(amounts) >= 2:
                # Check for very similar balances (difference < 1%)
                for i in range(len(amounts)):
                    for j in range(i + 1, len(amounts)):
                        if amounts[i] > 0 and amounts[j] > 0:
                            diff = abs(amounts[i] - amounts[j]) / max(amounts[i], amounts[j])
                            if diff < 0.01:  # Less than 1% difference
                                flags.append(f"🔗 Wallets #{i+1} and #{j+1} have similar balances (related?)")
                                suspicious_count += 1
                                break
                    else:
                        continue
                    break

        # ═══════════════════════════════════════════════════════════════
        # SET HOLDER CONCENTRATION
        # ═══════════════════════════════════════════════════════════════
        token.holder_concentration = top_10_concentration

        # ═══════════════════════════════════════════════════════════════
        # FINAL SUMMARY
        # ═══════════════════════════════════════════════════════════════
        if suspicious_count >= 3:
            flags.insert(0, f"🚨 Detected {suspicious_count} suspicious wallets!")

        token.suspicious_wallets = suspicious_count
        token.holder_flags = flags[:5]  # Maximum 5 flags

        logger.info(
            f"🔍 Holder analysis for {token.symbol}: "
            f"top-1={token.top_holder_pct:.1f}%, "
            f"top-10={token.holder_concentration:.1f}%, "
            f"suspicious={suspicious_count}"
        )

    async def simulate_transaction(
        self,
        transaction_base64: str,
        sig_verify: bool = False,
        commitment: str = "confirmed"
    ) -> SimulationResult:
        """
        Simulate a transaction without executing it.

        Used for honeypot detection by simulating sell transactions
        to verify they would succeed.

        Args:
            transaction_base64: Base64-encoded serialized transaction
            sig_verify: Whether to verify signatures (False for simulation)
            commitment: Bank state commitment level

        Returns:
            SimulationResult with success status, logs, and error info
        """
        await self._ensure_connected()

        try:
            # Decode the base64 transaction
            tx_bytes = base64.b64decode(transaction_base64)
            tx = VersionedTransaction.from_bytes(tx_bytes)

            logger.debug("Simulating transaction...")

            # Simulate via RPC
            response = await self._client.simulate_transaction(
                tx,
                sig_verify=sig_verify,
                commitment=Commitment(commitment)
            )

            # Parse response
            if not response or not response.value:
                return SimulationResult(
                    success=False,
                    error="No simulation response received",
                    logs=[]
                )

            value = response.value

            # Check for simulation error
            if value.err:
                error_msg = str(value.err)
                error_code = self._extract_error_code(value.err)

                logger.debug(f"Simulation failed: {error_msg}")
                return SimulationResult(
                    success=False,
                    error=error_msg,
                    error_code=error_code,
                    logs=list(value.logs) if value.logs else [],
                    units_consumed=value.units_consumed or 0
                )

            # Simulation succeeded
            logger.debug(f"Simulation succeeded, CU: {value.units_consumed}")
            return SimulationResult(
                success=True,
                logs=list(value.logs) if value.logs else [],
                units_consumed=value.units_consumed or 0,
                return_data=value.return_data if hasattr(value, 'return_data') else None
            )

        except Exception as e:
            logger.error(f"Transaction simulation failed: {e}", exc_info=True)
            return SimulationResult(
                success=False,
                error=str(e),
                logs=[]
            )

    def _extract_error_code(self, err: Any) -> Optional[int]:
        """
        Extract numeric error code from simulation error.

        Parses Solana error format to get custom program error codes.

        Args:
            err: Error object from simulation response

        Returns:
            Integer error code if present, None otherwise
        """
        try:
            # Handle dict-style errors
            if isinstance(err, dict):
                if "InstructionError" in err:
                    instruction_err = err["InstructionError"]
                    if isinstance(instruction_err, list) and len(instruction_err) >= 2:
                        custom_err = instruction_err[1]
                        if isinstance(custom_err, dict) and "Custom" in custom_err:
                            return custom_err["Custom"]

            # Handle string errors with error codes
            err_str = str(err)
            if "Custom" in err_str:
                # Try to extract number from string like "Custom(6000)"
                import re
                match = re.search(r'Custom\((\d+)\)', err_str)
                if match:
                    return int(match.group(1))

        except Exception:
            pass
        return None
