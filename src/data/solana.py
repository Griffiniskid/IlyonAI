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
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import aiohttp
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

from src.analytics.anomaly_detector import BehavioralAnomalyDetector
from src.analytics.time_series import TimeSeriesDataPoint
from src.analytics.wallet_forensics import WalletForensicsEngine, get_token_deployer
from src.core.models import TokenInfo
from src.smart_money.models import CanonicalFlowEvent
from src.smart_money.normalizer import normalize_event

# Retry configuration for rate-limited RPC calls
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff delays in seconds


def to_canonical_flow_event(raw_event: Dict[str, Any]) -> CanonicalFlowEvent:
    canonical_raw = dict(raw_event)
    canonical_raw.setdefault("chain", "solana")
    return normalize_event(canonical_raw)


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

    # Well-known token mints for whale detection
    WSOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    STABLECOIN_MINTS = {USDC_MINT, USDT_MINT}
    # All payment-side mints (not the traded asset)
    PAYMENT_MINTS = {WSOL_MINT, USDC_MINT, USDT_MINT}

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
        self._anomaly_detector = BehavioralAnomalyDetector()
        self._wallet_forensics = WalletForensicsEngine(solana_rpc_url=rpc_url)

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

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

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
                        err = data['error']
                        err_msg = err.get('message', '') if isinstance(err, dict) else str(err)
                        err_code = err.get('code') if isinstance(err, dict) else None
                        logger.warning(f"Helius API error: {err}")
                        if err_code == -32600 or 'Too many accounts' in err_msg:
                            logger.info(f"Skipping holder fetch for {address[:8]}: mint too large")
                            return []
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
                        sol_price = native_balance.get('price_per_sol', 200)  # Fallback price
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
            # When Helius is configured, trust its answer (incl. empty) and skip
            # the public-RPC fallback. The fallback otherwise 429s on huge mints
            # and adds 30+ seconds of retry backoff to every analyzer call.
            return helius_holders

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
    # SOL PRICE CACHE
    # ═══════════════════════════════════════════════════════════════════════════

    _sol_price_cache: Dict = {}  # class-level cache

    async def _get_sol_price(self) -> float:
        """
        Get current SOL price in USD, cached for 60 seconds.
        Uses Jupiter Price API as primary, CoinGecko as fallback.
        """
        import time
        cache = SolanaClient._sol_price_cache
        if cache.get('price') and cache.get('time', 0) > time.time() - 60:
            return cache['price']

        # Try Jupiter Price API first
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.jup.ag/price/v2?ids=So11111111111111111111111111111111111111112",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("data", {}).get(
                            "So11111111111111111111111111111111111111112", {}
                        ).get("price", 0))
                        if price > 0:
                            cache['price'] = price
                            cache['time'] = time.time()
                            logger.debug(f"SOL price from Jupiter: ${price:.2f}")
                            return price
        except Exception as e:
            logger.debug(f"Jupiter price API failed: {e}")

        # Fallback to CoinGecko
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("solana", {}).get("usd", 0))
                        if price > 0:
                            cache['price'] = price
                            cache['time'] = time.time()
                            logger.debug(f"SOL price from CoinGecko: ${price:.2f}")
                            return price
        except Exception as e:
            logger.debug(f"CoinGecko price API failed: {e}")

        # Last resort fallback
        return cache.get('price', 200.0)

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
        
        # Get real SOL price for accurate USD calculations
        sol_price = await self._get_sol_price()
        logger.info(f"Using SOL price: ${sol_price:.2f} for whale tracking")

        # Major DEX programs to monitor (expanded coverage)
        DEX_PROGRAMS = {
            'Jupiter': 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4',
            'Raydium': '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8',
            'Raydium CLMM': 'CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK',
            'Raydium CP': 'CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C',
            'Pump.fun': '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',
            'Orca': 'whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc',
            'Meteora': 'LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo',
            'Phoenix': 'PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY',
            'Lifinity': '2wT8Yq49kHgDzXuPxZSaeLaH1qbmGXtEyPy64bL7aD3s',
        }
        
        try:
            # Helper to fetch and parse for a specific program
            async def fetch_program_txs(name: str, address: str, session: aiohttp.ClientSession) -> List[Dict]:
                url = (
                    f"https://api.helius.xyz/v0/addresses/{address}/transactions"
                    f"?api-key={self.helius_api_key}&type=SWAP&limit=100"
                )

                for attempt in range(2):
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status != 200:
                                should_retry = resp.status in {429, 500, 502, 503, 504} and attempt < 1
                                if should_retry:
                                    await asyncio.sleep(RETRY_DELAYS[attempt])
                                    continue
                                logger.debug(f"Helius {name} fetch returned status {resp.status}")
                                return []

                            data = await resp.json()
                            if not data or not isinstance(data, list):
                                return []

                            parsed_txs = []
                            for tx in data:
                                parsed = await self._parse_helius_transaction(
                                    tx,
                                    min_amount_usd,
                                    sol_price=sol_price
                                )
                                if parsed:
                                    parsed['dex_name'] = name
                                    parsed_txs.append(parsed)

                            return parsed_txs
                    except Exception as e:
                        if attempt < 1:
                            await asyncio.sleep(RETRY_DELAYS[attempt])
                            continue
                        logger.debug(f"Error fetching {name} txs: {e}")

                return []

            async with aiohttp.ClientSession() as session:
                tasks = [fetch_program_txs(name, address, session) for name, address in DEX_PROGRAMS.items()]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Aggregate results
            for res in results:
                if isinstance(res, list):
                    all_transactions.extend(res)
            
            # Sort by time (newest first)
            from datetime import datetime, timezone

            def parse_time(tx):
                timestamp = tx.get('timestamp')
                if not timestamp:
                    return 0.0
                try:
                    dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.timestamp()
                except Exception:
                    return 0.0
            
            all_transactions.sort(key=parse_time, reverse=True)
            
            # Deduplicate by signature
            unique_txs = []
            seen_sigs = set()
            for tx in all_transactions:
                signature = tx.get('signature')
                if signature:
                    if signature in seen_sigs:
                        continue
                    seen_sigs.add(signature)
                unique_txs.append(tx)
            
            final_txs = unique_txs[:limit]
            
            # Enrich with Metadata (Symbol/Name)
            # We collect all token addresses that need lookup
            tokens_to_fetch = set()
            for tx in final_txs:
                if tx.get('token_symbol') == '???' and tx.get('token_address'):
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
        known_name: Optional[str] = None,
        sol_price: Optional[float] = None
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

            effective_sol_price = sol_price or 200.0

            # ── Calculate USD value from native SOL transfers ──
            sol_value_transferred = 0
            main_user = None

            for transfer in native_transfers:
                lamports = float(transfer.get('amount', 0) or 0)
                sol_amount = lamports / 1e9
                sol_value = sol_amount * effective_sol_price
                sol_value_transferred += sol_value

                if not main_user:
                    main_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # ── Calculate USD value from stablecoin (USDC/USDT) transfers ──
            stablecoin_usd = 0
            stablecoin_user = None

            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                if mint in self.STABLECOIN_MINTS:
                    amount = float(transfer.get('tokenAmount', 0) or 0)
                    stablecoin_usd += amount
                    if not stablecoin_user:
                        stablecoin_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # ── Calculate USD value from wrapped SOL token transfers ──
            wsol_usd = 0
            wsol_user = None

            for transfer in token_transfers:
                mint = transfer.get('mint', '')
                if mint == self.WSOL_MINT:
                    amount = float(transfer.get('tokenAmount', 0) or 0)
                    wsol_usd += amount * effective_sol_price
                    if not wsol_user:
                        wsol_user = transfer.get('fromUserAccount') or transfer.get('toUserAccount')

            # For swap routes with multiple transfer legs, avoid runaway over-counting.
            # Use the strongest payment-side estimate while still supporting mixed paths.
            payment_estimates = [
                sol_value_transferred,
                stablecoin_usd,
                wsol_usd,
                sol_value_transferred + stablecoin_usd,
                stablecoin_usd + wsol_usd,
            ]
            total_usd = max(payment_estimates)

            # If no SOL transfers, derive main_user from stablecoin/WSOL transfers
            if not main_user and stablecoin_user:
                main_user = stablecoin_user
            if not main_user and wsol_user:
                main_user = wsol_user

            # ── Determine primary token transfer (the traded asset) ──
            # Filter out payment-side mints (WSOL, USDC, USDT)
            asset_transfers = [t for t in token_transfers if t.get('mint') not in self.PAYMENT_MINTS]

            if not asset_transfers:
                return None

            # Pick the largest token transfer as the main asset
            main_transfer = max(asset_transfers, key=lambda t: float(t.get('tokenAmount', 0) or 0))

            # ── Determine buy/sell direction ──
            if main_user and main_transfer.get('toUserAccount') == main_user:
                tx_direction = 'buy'
            elif main_user and main_transfer.get('fromUserAccount') == main_user:
                tx_direction = 'sell'
            else:
                tx_direction = 'buy'
                wallet_address = main_transfer.get('toUserAccount')

            if not main_user:
                wallet_address = main_transfer.get('toUserAccount') if tx_direction == 'buy' else main_transfer.get('fromUserAccount')
            else:
                wallet_address = main_user

            # Filter by minimum amount
            if total_usd < min_amount_usd:
                return None
            
            # Use passed metadata if available
            symbol = known_symbol if known_symbol else '???'
            name = known_name if known_name else 'Unknown'
            
            # Convert timestamp to timezone-aware UTC datetime
            from datetime import datetime, timezone
            tx_time = (
                datetime.fromtimestamp(timestamp, tz=timezone.utc)
                if timestamp else datetime.now(timezone.utc)
            )
            
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


    async def get_whale_transactions(
        self,
        min_amount_usd: float = 5000,
        limit: int = 50,
    ) -> List[Dict]:
        """Get global whale transactions using real Helius on-chain data."""
        return await self.get_recent_large_transactions(
            min_amount_usd=min_amount_usd,
            limit=limit,
        )

    async def get_token_whale_transactions(
        self,
        token_address: str,
        min_amount_usd: float = 5000,
        limit: int = 50,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None
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

        # Get real SOL price for accurate USD calculations
        sol_price = await self._get_sol_price()
        transactions = []
        seen_signatures = set()

        try:
            async with aiohttp.ClientSession() as session:
                before_signature = None
                max_pages = 3

                for _ in range(max_pages):
                    url = (
                        f"https://api.helius.xyz/v0/addresses/{token_address}/transactions"
                        f"?api-key={self.helius_api_key}&type=SWAP&limit=100"
                    )
                    if before_signature:
                        url = f"{url}&before={before_signature}"

                    data = None
                    for attempt in range(2):
                        try:
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                                if resp.status != 200:
                                    should_retry = resp.status in {429, 500, 502, 503, 504} and attempt < 1
                                    if should_retry:
                                        await asyncio.sleep(RETRY_DELAYS[attempt])
                                        continue
                                    logger.warning(f"Helius token transactions returned {resp.status}")
                                    data = []
                                    break

                                data = await resp.json()
                                break
                        except Exception:
                            if attempt < 1:
                                await asyncio.sleep(RETRY_DELAYS[attempt])
                                continue
                            data = []

                    if not data or not isinstance(data, list):
                        break

                    for tx in data:
                        try:
                            signature = tx.get('signature')
                            if signature and signature in seen_signatures:
                                continue

                            parsed = await self._parse_helius_transaction(
                                tx,
                                min_amount_usd,
                                known_symbol=token_symbol,
                                known_name=token_name,
                                sol_price=sol_price
                            )
                            if not parsed:
                                continue

                            if signature:
                                seen_signatures.add(signature)

                            transactions.append(parsed)
                            if len(transactions) >= limit:
                                break
                        except Exception:
                            continue

                    if len(transactions) >= limit:
                        break

                    if len(data) < 100:
                        break

                    before_signature = data[-1].get('signature')
                    if not before_signature:
                        break

            logger.info(f"✅ Found {len(transactions)} whale transactions for token {token_address[:8]}")
            return transactions[:limit]

        except Exception as e:
            logger.error(f"Error fetching token whale transactions: {e}")
            return []

    async def get_behavior_transactions(
        self,
        token_address: str,
        min_amount_usd: float = 5000,
        limit: int = 50,
        token_symbol: Optional[str] = None,
        token_name: Optional[str] = None,
    ) -> List[Dict]:
        transactions = await self.get_token_whale_transactions(
            token_address=token_address,
            min_amount_usd=min_amount_usd,
            limit=limit,
            token_symbol=token_symbol,
            token_name=token_name,
        )
        return await self._annotate_behavior_transactions(token_address, transactions)

    async def _annotate_behavior_transactions(self, token_address: str, transactions: List[Dict]) -> List[Dict]:
        if not transactions:
            return []

        anomaly_flags = [flag.to_dict() for flag in self._anomaly_detector.detect_behavior_flags(self._build_behavior_time_series(transactions))]
        entity_heuristics = [
            heuristic.to_dict()
            for heuristic in await self._detect_entity_heuristics(token_address, transactions)
        ]

        annotated = []
        for tx in transactions:
            enriched = dict(tx)
            enriched["anomaly_flags"] = anomaly_flags
            enriched["entity_heuristics"] = entity_heuristics
            annotated.append(enriched)
        return annotated

    async def _detect_entity_heuristics(self, token_address: str, transactions: List[Dict]):
        total_abs_amount = sum(abs(float(tx.get("amount_usd", 0) or 0)) for tx in transactions)
        if total_abs_amount <= 0:
            return []

        wallet_totals: Dict[str, float] = {}
        for tx in transactions:
            wallet = str(tx.get("wallet_address") or "")
            if not wallet:
                continue
            wallet_totals[wallet] = wallet_totals.get(wallet, 0.0) + abs(float(tx.get("amount_usd", 0) or 0))

        top_holders = [
            {"address": wallet, "share": amount / total_abs_amount}
            for wallet, amount in sorted(wallet_totals.items(), key=lambda item: item[1], reverse=True)
        ]
        deployer_wallet = await get_token_deployer(token_address, self.rpc_url)
        return self._wallet_forensics.detect_entity_heuristics(deployer_wallet, top_holders)

    def _build_behavior_time_series(self, transactions: List[Dict]) -> List[TimeSeriesDataPoint]:
        ordered = sorted(transactions, key=lambda tx: str(tx.get("timestamp") or ""))
        max_amount = max(abs(float(tx.get("amount_usd", 0) or 0)) for tx in ordered) if ordered else 0.0
        liquidity_proxy = sum(abs(float(tx.get("amount_usd", 0) or 0)) for tx in ordered) * 1.5
        points: List[TimeSeriesDataPoint] = []

        for tx in ordered:
            amount = abs(float(tx.get("amount_usd", 0) or 0))
            tx_type = str(tx.get("type") or "buy").lower()
            if tx_type == "sell":
                liquidity_proxy = max(1000.0, liquidity_proxy - amount)
            else:
                liquidity_proxy += amount * 0.05

            timestamp_raw = tx.get("timestamp")
            if isinstance(timestamp_raw, str):
                timestamp = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
            elif isinstance(timestamp_raw, datetime):
                timestamp = timestamp_raw
            else:
                timestamp = datetime.utcnow()

            points.append(
                TimeSeriesDataPoint(
                    timestamp=timestamp,
                    liquidity_usd=liquidity_proxy,
                    buy_count=1 if tx_type != "sell" else 0,
                    sell_count=1 if tx_type == "sell" else 0,
                    large_sells=1 if tx_type == "sell" and amount >= max_amount * 0.5 else 0,
                    whale_net_flow_usd=amount if tx_type != "sell" else -amount,
                )
            )

        return points
