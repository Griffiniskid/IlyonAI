"""
RugCheck API client for LP lock verification and security analysis.

This module provides an async client for interacting with the RugCheck.xyz API
to check LP locks, analyze token security, and identify risk factors.
"""

import logging
import asyncio
from typing import Optional, Dict, List, Any
import aiohttp

logger = logging.getLogger(__name__)


class RugCheckClient:
    """
    Async client for RugCheck.xyz API.

    Checks LP locks, token security, and identifies risks through
    the RugCheck verification system.

    Usage:
        # With context manager (recommended)
        async with RugCheckClient() as client:
            data = await client.check_token("token_address")

        # Manual lifecycle
        client = RugCheckClient()
        data = await client.check_token("token_address")
        await client.close()
    """

    BASE_URL = "https://api.rugcheck.xyz/v1/tokens"
    DEFAULT_TIMEOUT = 10  # seconds
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES
    ):
        """
        Initialize RugCheck client.

        Args:
            session: Optional existing aiohttp session. If None, creates its own.
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts on failure
        """
        self._session = session
        self._owns_session = session is None
        self.timeout = timeout
        self.max_retries = max_retries

    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources"""
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """
        Ensure we have a valid session.

        Returns:
            Active aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
            self._owns_session = True
        return self._session

    async def close(self):
        """Close the aiohttp session if we own it"""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        url: str,
        retry_count: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with retry logic.

        Args:
            url: Full URL to request
            retry_count: Current retry attempt number

        Returns:
            JSON response dict or None on failure
        """
        try:
            session = await self._ensure_session()

            async with session.get(url) as resp:
                # Check status code
                if resp.status == 429:
                    # Rate limited
                    logger.warning(f"RugCheck rate limit hit for {url}")
                    if retry_count < self.max_retries:
                        await asyncio.sleep(self.RETRY_DELAY * (retry_count + 1))
                        return await self._make_request(url, retry_count + 1)
                    return None

                if resp.status != 200:
                    logger.warning(f"RugCheck API returned status {resp.status} for {url}")
                    return None

                # Parse JSON
                try:
                    data = await resp.json()
                    return data
                except Exception as e:
                    logger.error(f"Failed to parse RugCheck JSON: {e}")
                    return None

        except asyncio.TimeoutError:
            logger.warning(f"RugCheck request timeout for {url}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY)
                return await self._make_request(url, retry_count + 1)
            return None

        except aiohttp.ClientError as e:
            logger.error(f"RugCheck client error: {e}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY)
                return await self._make_request(url, retry_count + 1)
            return None

        except Exception as e:
            logger.error(f"Unexpected RugCheck error: {e}", exc_info=True)
            return None

    async def check_token(self, address: str) -> Dict[str, Any]:
        """
        Check token security and LP lock status via RugCheck.

        Analyzes token for LP locks, security risks, and authority issues.
        Checks multiple data sources within RugCheck API:
        - lockers: Direct LP lock providers
        - markets: DEX market LP lock information
        - lockerOwners: LP lock ownership data

        Args:
            address: Solana token address

        Returns:
            Dict with structure:
            {
                'lp_locked': bool,           # Whether LP is locked
                'lp_lock_percent': float,    # Percentage of LP locked (0-100)
                'lock_info': Optional[Dict], # Details about the lock
                'rugcheck_score': int,       # RugCheck security score
                'risks': List[str],          # List of identified risks
                'mint_authority': Optional,  # Mint authority status
                'freeze_authority': Optional # Freeze authority status
            }
        """
        # Default result structure
        result = {
            'lp_locked': False,
            'lp_lock_percent': 0.0,
            'lock_info': None,
            'rugcheck_score': 0,
            'risks': [],
            'mint_authority': None,
            'freeze_authority': None
        }

        url = f"{self.BASE_URL}/{address}/report"

        logger.info(f"🔍 Checking RugCheck for {address[:8]}...")

        data = await self._make_request(url)

        if not data:
            logger.warning(f"No RugCheck data for token {address[:8]}")
            return result

        try:
            # ═══════════════════════════════════════════════════════════════
            # LP LOCK DETECTION - Check 'lockers' field
            # ═══════════════════════════════════════════════════════════════
            lockers = data.get('lockers', [])
            if lockers:
                result['lp_locked'] = True
                # Handle both list and dict formats
                if isinstance(lockers, list) and len(lockers) > 0:
                    result['lock_info'] = lockers[0]
                    logger.info(f"✅ LP Lock found via lockers: {len(lockers)} locker(s)")
                elif isinstance(lockers, dict):
                    result['lock_info'] = lockers
                    logger.info(f"✅ LP Lock found via lockers (dict format)")

            # ═══════════════════════════════════════════════════════════════
            # LP LOCK DETECTION - Check 'markets' for locked LP
            # ═══════════════════════════════════════════════════════════════
            markets = data.get('markets', [])
            for market in markets:
                lp = market.get('lp', {})
                lp_locked_pct = lp.get('lpLockedPct', 0) or 0

                if lp.get('lpLocked', False) or lp_locked_pct > 0:
                    result['lp_locked'] = True
                    result['lp_lock_percent'] = lp_locked_pct
                    result['lock_info'] = {
                        'locked_pct': lp_locked_pct,
                        'locked_usd': lp.get('lpLockedUSD', 0),
                        'market': market.get('marketId', 'unknown')
                    }
                    logger.info(f"✅ LP Lock from markets: {lp_locked_pct:.1f}%")
                    break

            # ═══════════════════════════════════════════════════════════════
            # LP LOCK DETECTION - Check 'lockerOwners'
            # ═══════════════════════════════════════════════════════════════
            locker_owners = data.get('lockerOwners', [])
            if locker_owners and len(locker_owners) > 0:
                result['lp_locked'] = True
                logger.info(f"✅ LP Lock via lockerOwners: {len(locker_owners)}")

            # ═══════════════════════════════════════════════════════════════
            # RUGCHECK SCORE
            # ═══════════════════════════════════════════════════════════════
            result['rugcheck_score'] = data.get('score', 0)

            # ═══════════════════════════════════════════════════════════════
            # RISK FACTORS
            # ═══════════════════════════════════════════════════════════════
            risks = data.get('risks', [])
            # Extract risk names, limit to top 5
            result['risks'] = [r.get('name', '') for r in risks[:5]]

            # ═══════════════════════════════════════════════════════════════
            # MINT/FREEZE AUTHORITY
            # ═══════════════════════════════════════════════════════════════
            result['mint_authority'] = data.get('mintAuthority')
            result['freeze_authority'] = data.get('freezeAuthority')

            # Log summary
            lock_status = "LOCKED" if result['lp_locked'] else "NOT LOCKED"
            logger.info(
                f"✅ RugCheck complete for {address[:8]}: "
                f"LP {lock_status}, Score: {result['rugcheck_score']}, "
                f"Risks: {len(result['risks'])}"
            )

            return result

        except Exception as e:
            logger.error(f"Error parsing RugCheck data for {address[:8]}: {e}", exc_info=True)
            return result
