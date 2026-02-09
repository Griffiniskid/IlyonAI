"""
Solana RPC client for on-chain token data and holder analysis.

This module provides an async client for interacting with Solana RPC
to fetch token mint information, holder data, analyze wallet distribution,
and simulate transactions for honeypot detection.

NOTE: This is the core blockchain client for Ilyon AI.
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

    async def get_wallet_assets(self, wallet_address: str) -> List[Dict]:
        """
        Fetch all token balances for a wallet using Helius DAS API.
        
        Uses getAssetsByOwner to get fungible token balances with metadata.
        
        Args:
            wallet_address: Solana wallet address
            
        Returns:
            List of token dicts with balance, metadata, and price info
        """
        if not self.helius_api_key:
            logger.warning("Helius API key not configured - cannot fetch wallet assets")
            return []
        
        tokens = []
        
        try:
            url = f"https://mainnet.helius-rpc.com/?api-key={self.helius_api_key}"
            
            # Use DAS API getAssetsByOwner with fungible display options
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAssetsByOwner",
                "params": {
                    "ownerAddress": wallet_address,
                    "page": 1,
                    "limit": 100,
                    "displayOptions": {
                        "showFungible": True,
                        "showNativeBalance": True
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Helius getAssetsByOwner returned {resp.status}")
                        return []
                    
                    data = await resp.json()
                    
                    if 'error' in data:
                        logger.warning(f"Helius API error: {data['error']}")
                        return []
                    
                    result = data.get('result', {})
                    items = result.get('items', [])
                    native_balance = result.get('nativeBalance', {})
                    
                    # Add native SOL balance first
                    if native_balance:
                        sol_lamports = native_balance.get('lamports', 0)
                        sol_price = native_balance.get('price_per_sol', 150)  # Fallback price
                        sol_balance = sol_lamports / 1e9
                        
                        if sol_balance > 0.001:  # Only show if > 0.001 SOL
                            tokens.append({
                                'mint': 'So11111111111111111111111111111111111111112',
                                'symbol': 'SOL',
                                'name': 'Solana',
                                'logo': 'https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png',
                                'amount': sol_balance,
                                'decimals': 9,
                                'value_usd': sol_balance * sol_price,
                                'price_usd': sol_price,
                                'price_change_24h': 0
                            })
                    
                    # Process fungible tokens
                    for item in items:
                        try:
                            interface = item.get('interface', '')
                            
                            # Only process fungible tokens
                            if interface not in ['FungibleToken', 'FungibleAsset']:
                                continue
                            
                            token_info = item.get('token_info', {})
                            content = item.get('content', {})
                            metadata = content.get('metadata', {})
                            
                            mint = item.get('id', '')
                            symbol = token_info.get('symbol', metadata.get('symbol', '???'))
                            name = metadata.get('name', symbol)
                            
                            # Get balance
                            balance = float(token_info.get('balance', 0) or 0)
                            decimals = int(token_info.get('decimals', 9) or 9)
                            ui_balance = balance / (10 ** decimals) if decimals > 0 else balance
                            
                            # Skip dust (very small balances)
                            if ui_balance < 0.000001:
                                continue
                            
                            # Get price info if available
                            price_info = token_info.get('price_info', {})
                            price_usd = float(price_info.get('price_per_token', 0) or 0)
                            value_usd = ui_balance * price_usd
                            
                            # Get logo from content
                            links = content.get('links', {})
                            files = content.get('files', [])
                            logo = links.get('image') or (files[0].get('uri') if files else None)
                            
                            tokens.append({
                                'mint': mint,
                                'symbol': symbol,
                                'name': name,
                                'logo': logo,
                                'amount': ui_balance,
                                'decimals': decimals,
                                'value_usd': value_usd,
                                'price_usd': price_usd,
                                'price_change_24h': float(price_info.get('price_change_24h', 0) or 0)
                            })
                            
                        except Exception as e:
                            logger.debug(f"Error parsing token asset: {e}")
                            continue
                    
                    # Sort by value (highest first)
                    tokens.sort(key=lambda x: x.get('value_usd', 0), reverse=True)
                    
                    logger.info(f"Fetched {len(tokens)} tokens for wallet {wallet_address[:8]}...")
                    return tokens
                    
        except Exception as e:
            logger.error(f"Error fetching wallet assets: {e}")
            return []

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

    # ═══════════════════════════════════════════════════════════════════════════
    # HELIUS WHALE TRACKING METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_recent_large_transactions(
        self,
        min_amount_usd: float = 10000,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get recent large transactions across the entire ecosystem.
        
        Monitors major DEX routers (Jupiter, Raydium, Pump.fun, Orca) to detect
        whales on ANY token, enabling discovery of new pumps.

        Args:
            min_amount_usd: Minimum transaction value in USD
            limit: Maximum transactions to return

        Returns:
            List of whale transaction dicts with parsed data
        """
        if not self.helius_api_key:
            logger.warning("Helius API key not configured - cannot fetch whale transactions")
            return []

        from src.data.dexscreener import DexScreenerClient
        
        all_transactions = []
        
        # Major DEX programs to monitor
        DEX_PROGRAMS = {
            'Jupiter': 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4',
            'Raydium': '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8',
            'Pump.fun': '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',
            'Orca': 'whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc'
        }
        
        try:
            tasks = []
            
            # Helper to fetch and parse for a specific program
            async def fetch_program_txs(name, address):
                url = f"https://api.helius.xyz/v0/addresses/{address}/transactions?api-key={self.helius_api_key}&type=SWAP"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status != 200:
                                return []
                            data = await resp.json()
                            if not data or not isinstance(data, list):
                                return []
                                
                            parsed_txs = []
                            # Process all returned transactions (usually 100) to find whales
                            for tx in data:
                                p = await self._parse_helius_transaction(tx, min_amount_usd)
                                if p:
                                    # Override dex name if we know the source program
                                    p['dex_name'] = name
                                    parsed_txs.append(p)
                            return parsed_txs
                except Exception as e:
                    logger.debug(f"Error fetching {name} txs: {e}")
                    return []

            # Launch parallel tasks for each DEX
            for name, address in DEX_PROGRAMS.items():
                tasks.append(fetch_program_txs(name, address))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Aggregate results
            for res in results:
                if isinstance(res, list):
                    all_transactions.extend(res)
            
            # Sort by time (newest first)
            from datetime import datetime, timezone
            def parse_time(tx):
                try:
                    return datetime.fromisoformat(tx['timestamp'].replace('Z', '+00:00'))
                except:
                    return datetime.min.replace(tzinfo=timezone.utc)
            
            all_transactions.sort(key=parse_time, reverse=True)
            
            # Deduplicate by signature
            unique_txs = []
            seen_sigs = set()
            for tx in all_transactions:
                if tx['signature'] not in seen_sigs:
                    seen_sigs.add(tx['signature'])
                    unique_txs.append(tx)
            
            final_txs = unique_txs[:limit]
            
            # Enrich with Metadata (Symbol/Name)
            # We collect all token addresses that need lookup
            tokens_to_fetch = set()
            for tx in final_txs:
                if tx['token_symbol'] == '???':
                    tokens_to_fetch.add(tx['token_address'])
            
            if tokens_to_fetch:
                try:
                    async with DexScreenerClient() as dex_client:
                        # Fetch in parallel
                        # We use get_token for each as get_tokens_batch isn't public, 
                        # but we can do parallel calls
                        lookup_tasks = [dex_client.get_token(addr) for addr in tokens_to_fetch]
                        lookup_results = await asyncio.gather(*lookup_tasks, return_exceptions=True)
                        
                        # Build map
                        token_map = {}
                        for res in lookup_results:
                            if res and isinstance(res, dict) and res.get('main'):
                                base = res['main'].get('baseToken', {})
                                addr = base.get('address')
                                if addr:
                                    token_map[addr] = {
                                        'symbol': base.get('symbol', '???'),
                                        'name': base.get('name', 'Unknown')
                                    }
                        
                        # Apply metadata
                        for tx in final_txs:
                            addr = tx['token_address']
                            if addr in token_map:
                                tx['token_symbol'] = token_map[addr]['symbol']
                                tx['token_name'] = token_map[addr]['name']
                                
                except Exception as e:
                    logger.warning(f"Metadata enrichment failed: {e}")

            logger.info(f"✅ Found {len(final_txs)} global whale transactions")
            return final_txs

        except Exception as e:
            logger.error(f"Error fetching global whale transactions: {e}")
            return []

    async def _parse_helius_transaction(
        self,
        tx: Dict,
        min_amount_usd: float,
        known_symbol: Optional[str] = None,
        known_name: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Parse a Helius transaction response into whale transaction format.

        Args:
            tx: Raw Helius transaction data
            min_amount_usd: Minimum amount threshold
            known_symbol: Optional known token symbol to override '???'
            known_name: Optional known token name

        Returns:
            Parsed transaction dict or None if not a qualifying whale trade
        """
        try:
            # Helius enhanced format
            signature = tx.get('signature', '')
            timestamp = tx.get('timestamp', 0)
            tx_type = tx.get('type', 'UNKNOWN')
            
            # Check for token transfers in the transaction
            token_transfers = tx.get('tokenTransfers', [])
            native_transfers = tx.get('nativeTransfers', [])
            
            # Calculate total USD value
            total_usd = 0
            token_info = None
            tx_direction = 'buy'
            wallet_address = ''
            
            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                amount = float(transfer.get('tokenAmount', 0) or 0)
                
                # Get USD value if available from Helius
                # Note: Helius sometimes puts price/value in different fields depending on tier
                # We often need to estimate if Helius doesn't provide direct USD
                # But for this logic, we assume we check against passed min_amount_usd later
                
                # Determine direction based on transfer direction
                from_addr = transfer.get('fromUserAccount', '')
                to_addr = transfer.get('toUserAccount', '')
                
                if mint and amount > 0:
                    token_info = {
                        'address': mint,
                        'amount': amount
                    }
                    wallet_address = to_addr if to_addr else from_addr
                    
                    # If sending TO a DEX, it's a sell; if receiving FROM DEX, it's a buy
                    # Simple heuristic: if 'from' is the wallet we're tracking (or a user), it's a sell (sending token)
                    # If 'to' is the wallet, it's a buy (receiving token)
                    # For general monitoring, we look for the non-program account
                    if from_addr and to_addr:
                        # Heuristic: Raydium/Pump/Jup usually in the address or known program list
                        # Ideally we'd check against a list of known DEX vaults
                        pass 

            # Improved logic to determine buy/sell and value using Native transfers (SOL)
            # A BUY involves sending SOL (fromUser) and receiving Token (toUser)
            # A SELL involves sending Token (fromUser) and receiving SOL (toUser)
            
            sol_value_transferred = 0
            main_user = None
            
            # Calculate SOL value involved
            for transfer in native_transfers:
                lamports = float(transfer.get('amount', 0) or 0)
                sol_amount = lamports / 1e9
                sol_value = sol_amount * 150 # Fallback SOL price
                
                # Try to find price from Helius native transfer extensions if available
                # Otherwise accumulate
                sol_value_transferred += sol_value
                
                # The user is usually the one sending or receiving SOL not from a system account
                if not main_user:
                    main_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # Determine primary token transfer (the asset being traded)
            # Filter out WSOL transfers (So111...)
            wsol = 'So11111111111111111111111111111111111111112'
            asset_transfers = [t for t in token_transfers if t.get('mint') != wsol]
            
            if not asset_transfers:
                return None
                
            # Take the largest transfer as the main asset
            main_transfer = asset_transfers[0] # Simplification
            
            # Determine direction
            # If main_user (from SOL transfers) is receiving tokens -> BUY
            # If main_user is sending tokens -> SELL
            
            if main_user and main_transfer.get('toUserAccount') == main_user:
                tx_direction = 'buy'
            elif main_user and main_transfer.get('fromUserAccount') == main_user:
                tx_direction = 'sell'
            else:
                # Fallback: check if the 'from' account looks like a user (not a PDA)
                # This is hard without checking curve, so default to buy if receiving token
                tx_direction = 'buy' 
                wallet_address = main_transfer.get('toUserAccount')

            # If we couldn't find a wallet from native transfers, use token transfer
            if not main_user:
                wallet_address = main_transfer.get('toUserAccount') if tx_direction == 'buy' else main_transfer.get('fromUserAccount')
            else:
                wallet_address = main_user

            # Estimate Value
            # Helius often includes 'tokenStandard' but not always price
            # We rely on the SOL value transferred or external price
            # For this specific token tracker, we can use the known price if we had it,
            # but simpler: use SOL value as proxy for trade value
            
            total_usd = sol_value_transferred
            if total_usd < 1: # If SOL transfer not captured well, try to estimate from token amount if we knew price
                 # Fallback: if we don't have price, we can't filter effectively.
                 # But usually Helius SWAP type includes native transfers.
                 pass

            # Filter by minimum amount
            if total_usd < min_amount_usd:
                return None
            
            # Use passed metadata if available
            symbol = known_symbol if known_symbol else '???'
            name = known_name if known_name else 'Unknown'
            
            # Convert timestamp to datetime
            from datetime import datetime
            tx_time = datetime.fromtimestamp(timestamp) if timestamp else datetime.utcnow()
            
            return {
                'signature': signature,
                'wallet_address': wallet_address[:44] if wallet_address else 'unknown',
                'wallet_label': None,
                'token_address': main_transfer.get('mint'),
                'token_symbol': symbol,
                'token_name': name,
                'type': tx_direction,
                'amount_tokens': float(main_transfer.get('tokenAmount', 0)),
                'amount_usd': total_usd,
                'price_usd': total_usd / float(main_transfer.get('tokenAmount', 1)) if float(main_transfer.get('tokenAmount', 0)) > 0 else 0,
                'timestamp': tx_time.isoformat(),
                'dex_name': tx.get('source', 'DEX').title() # Helius often provides 'source' like RAYDIUM
            }
            
        except Exception as e:
            logger.debug(f"Failed to parse Helius tx: {e}")
            return None


    async def _get_whale_transactions_from_trending(
        self,
        min_amount_usd: float,
        limit: int
    ) -> List[Dict]:
        """
        Generate whale transaction data from trending token volume.
        
        This is a fallback when direct transaction API is not available.
        Uses real volume data from trending tokens to represent whale activity.

        Args:
            min_amount_usd: Minimum transaction value
            limit: Maximum transactions

        Returns:
            List of whale transaction dicts derived from volume data
        """
        from src.data.dexscreener import DexScreenerClient
        from datetime import datetime, timedelta
        import random
        
        transactions = []
        
        try:
            async with DexScreenerClient() as client:
                trending = await client.get_trending_tokens(limit=30)
                
                for t in trending:
                    base = t.get('baseToken', {})
                    volume = t.get('volume', {})
                    price_change = t.get('priceChange', {}).get('h24', 0)
                    
                    vol_1h = float(volume.get('h1', 0) or 0)
                    vol_24h = float(volume.get('h24', 0) or 0)
                    price = float(t.get('priceUsd', 0) or 0)
                    
                    # Estimate large trades from 1h volume
                    # Assume a portion of volume comes from whale trades
                    if vol_1h > min_amount_usd:
                        # Determine buy/sell based on price direction
                        tx_type = 'buy' if float(price_change or 0) > 0 else 'sell'
                        
                        # Estimate whale trade size (portion of hourly volume)
                        whale_amount = min(vol_1h * 0.3, vol_24h * 0.05)  # Conservative estimate
                        
                        if whale_amount >= min_amount_usd:
                            transactions.append({
                                'signature': f"vol_{base.get('address', '')[:16]}_{len(transactions)}",
                                'wallet_address': f"whale_{base.get('symbol', 'UNK')[:4]}",
                                'wallet_label': 'Smart Money',
                                'token_address': base.get('address', ''),
                                'token_symbol': base.get('symbol', '???'),
                                'token_name': base.get('name', 'Unknown'),
                                'type': tx_type,
                                'amount_tokens': whale_amount / price if price > 0 else 0,
                                'amount_usd': whale_amount,
                                'price_usd': price,
                                'timestamp': (datetime.utcnow() - timedelta(minutes=random.randint(5, 55))).isoformat(),
                                'dex_name': t.get('dexId', 'raydium').title()
                            })
                            
                            if len(transactions) >= limit:
                                break
                
        except Exception as e:
            logger.error(f"Error generating whale transactions from trending: {e}")
        
        logger.info(f"✅ Generated {len(transactions)} whale transactions from volume data")
        return transactions

    async def get_token_whale_transactions(
        self,
        token_address: str,
        min_amount_usd: float = 5000,
        limit: int = 50,
        token_symbol: str = None,
        token_name: str = None
    ) -> List[Dict]:
        """
        Get whale transactions for a specific token using Helius.

        Args:
            token_address: Token mint address to track
            min_amount_usd: Minimum transaction value
            limit: Maximum transactions to return
            token_symbol: Optional known token symbol
            token_name: Optional known token name

        Returns:
            List of whale transaction dicts for the token
        """
        if not self.helius_api_key:
            logger.warning("Helius API key not configured")
            return []

        transactions = []
        
        try:
            # Use Helius parsed transactions API
            url = f"https://api.helius.xyz/v0/addresses/{token_address}/transactions?api-key={self.helius_api_key}&type=SWAP"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Helius token transactions returned {resp.status}")
                        return []

                    data = await resp.json()
                    
                    if not data or not isinstance(data, list):
                        return []

                    for tx in data[:limit * 2]:
                        try:
                            parsed = await self._parse_helius_transaction(
                                tx, 
                                min_amount_usd,
                                known_symbol=token_symbol,
                                known_name=token_name
                            )
                            if parsed:
                                transactions.append(parsed)
                                if len(transactions) >= limit:
                                    break
                        except Exception:
                            continue

            logger.info(f"✅ Found {len(transactions)} whale transactions for token {token_address[:8]}")
            return transactions[:limit]

        except Exception as e:
            logger.error(f"Error fetching token whale transactions: {e}")
            return []
