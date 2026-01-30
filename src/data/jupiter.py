"""
Jupiter Aggregator API client for Solana swap quotes and transaction building.

This module provides an async client for interacting with Jupiter's Swap API
to get swap quotes and build swap transactions for honeypot detection.

NOTE: Jupiter is a Solana-exclusive DEX aggregator - this client only
works with Solana tokens. No multi-chain support.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
import aiohttp

from src.config import settings

logger = logging.getLogger(__name__)


class JupiterRouteStatus(Enum):
    """Status of Jupiter route availability."""
    AVAILABLE = "available"
    NO_ROUTE = "no_route"
    INSUFFICIENT_LIQUIDITY = "insufficient_liquidity"
    ERROR = "error"


@dataclass
class JupiterQuoteResult:
    """Result from Jupiter Quote API."""
    status: JupiterRouteStatus
    input_mint: str
    output_mint: str
    in_amount: int  # Raw lamports/atomic units
    out_amount: int  # Expected output in atomic units
    out_amount_with_slippage: int  # Minimum output after slippage
    price_impact_pct: float
    route_plan: List[Dict[str, Any]] = field(default_factory=list)
    raw_quote: Optional[Dict] = None
    error: Optional[str] = None


@dataclass
class JupiterSwapResult:
    """Result from Jupiter Swap API."""
    success: bool
    swap_transaction: Optional[str]  # Base64-encoded transaction
    last_valid_block_height: Optional[int]
    simulation_error: Optional[str]
    compute_units: Optional[int]
    raw_response: Optional[Dict] = None
    error: Optional[str] = None


class JupiterClient:
    """
    Async client for Jupiter Aggregator API.

    Supports getting swap quotes and building swap transactions
    for honeypot detection via transaction simulation.

    Usage:
        async with JupiterClient() as client:
            quote = await client.get_quote(token_mint, sol_mint, amount)
            swap = await client.build_swap_transaction(quote, user_pubkey)
    """

    BASE_URL = "https://api.jup.ag/swap/v1"
    DEFAULT_TIMEOUT = settings.jupiter_api_timeout  # From config
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0  # seconds

    # Solana native token addresses
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def __init__(
        self,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES
    ):
        """
        Initialize Jupiter client.

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
        """Close the aiohttp session if we own it."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method ("GET" or "POST")
            url: Full URL to request
            params: Query parameters for GET requests
            json_body: JSON body for POST requests
            retry_count: Current retry attempt number

        Returns:
            JSON response dict or None on failure
        """
        try:
            session = await self._ensure_session()

            if method.upper() == "GET":
                async with session.get(url, params=params) as resp:
                    return await self._handle_response(resp, url, retry_count)
            else:
                async with session.post(url, json=json_body) as resp:
                    return await self._handle_response(resp, url, retry_count)

        except asyncio.TimeoutError:
            logger.warning(f"Jupiter request timeout for {url}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY * (retry_count + 1))
                return await self._make_request(method, url, params, json_body, retry_count + 1)
            return None

        except aiohttp.ClientError as e:
            logger.error(f"Jupiter client error: {e}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY)
                return await self._make_request(method, url, params, json_body, retry_count + 1)
            return None

        except Exception as e:
            logger.error(f"Unexpected Jupiter error: {e}", exc_info=True)
            return None

    async def _handle_response(
        self,
        resp: aiohttp.ClientResponse,
        url: str,
        retry_count: int
    ) -> Optional[Dict[str, Any]]:
        """Handle HTTP response with status code checks."""
        if resp.status == 429:
            logger.warning(f"Jupiter rate limit hit for {url}")
            if retry_count < self.max_retries:
                await asyncio.sleep(self.RETRY_DELAY * (retry_count + 2))
                return None  # Will be retried by caller
            return None

        if resp.status == 400:
            # Bad request - usually means no route available
            try:
                error_data = await resp.json()
                logger.debug(f"Jupiter 400 response: {error_data}")
            except Exception:
                pass
            return None

        if resp.status != 200:
            logger.warning(f"Jupiter API returned status {resp.status} for {url}")
            return None

        try:
            data = await resp.json()
            return data
        except Exception as e:
            logger.error(f"Failed to parse Jupiter JSON: {e}")
            return None

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 100,
        only_direct_routes: bool = False,
        max_accounts: int = 64
    ) -> JupiterQuoteResult:
        """
        Get swap quote from Jupiter.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address (typically SOL for sell detection)
            amount: Amount in atomic units (lamports for SOL)
            slippage_bps: Acceptable slippage in basis points (100 = 1%)
            only_direct_routes: Restrict to single-market routes
            max_accounts: Maximum accounts in transaction

        Returns:
            JupiterQuoteResult with quote details or error status
        """
        url = f"{self.BASE_URL}/quote"
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": str(slippage_bps),
            "restrictIntermediateTokens": "true",
            "maxAccounts": str(max_accounts),
        }
        if only_direct_routes:
            params["onlyDirectRoutes"] = "true"

        logger.debug(f"Getting Jupiter quote: {input_mint[:8]}... -> {output_mint[:8]}..., amount={amount}")

        data = await self._make_request("GET", url, params=params)

        if not data:
            return JupiterQuoteResult(
                status=JupiterRouteStatus.NO_ROUTE,
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount=amount,
                out_amount=0,
                out_amount_with_slippage=0,
                price_impact_pct=0,
                route_plan=[],
                error="No route available or API error"
            )

        # Check for error in response
        if "error" in data:
            return JupiterQuoteResult(
                status=JupiterRouteStatus.ERROR,
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount=amount,
                out_amount=0,
                out_amount_with_slippage=0,
                price_impact_pct=0,
                route_plan=[],
                error=data.get("error", "Unknown error")
            )

        # Parse successful response
        try:
            out_amount = int(data.get("outAmount", 0))
            other_amount_threshold = int(data.get("otherAmountThreshold", out_amount))
            price_impact = float(data.get("priceImpactPct", 0))
            route_plan = data.get("routePlan", [])

            logger.info(
                f"Jupiter quote: {amount} -> {out_amount} "
                f"(impact: {price_impact:.2f}%, routes: {len(route_plan)})"
            )

            return JupiterQuoteResult(
                status=JupiterRouteStatus.AVAILABLE,
                input_mint=data.get("inputMint", input_mint),
                output_mint=data.get("outputMint", output_mint),
                in_amount=int(data.get("inAmount", amount)),
                out_amount=out_amount,
                out_amount_with_slippage=other_amount_threshold,
                price_impact_pct=price_impact,
                route_plan=route_plan,
                raw_quote=data
            )

        except (ValueError, TypeError) as e:
            logger.error(f"Failed to parse Jupiter quote response: {e}")
            return JupiterQuoteResult(
                status=JupiterRouteStatus.ERROR,
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount=amount,
                out_amount=0,
                out_amount_with_slippage=0,
                price_impact_pct=0,
                route_plan=[],
                error=f"Failed to parse response: {e}"
            )

    async def build_swap_transaction(
        self,
        quote: JupiterQuoteResult,
        user_public_key: str,
        dynamic_compute_unit_limit: bool = True
    ) -> JupiterSwapResult:
        """
        Build swap transaction from quote.

        Args:
            quote: JupiterQuoteResult from get_quote()
            user_public_key: User's Solana wallet public key
            dynamic_compute_unit_limit: Enable dynamic CU estimation

        Returns:
            JupiterSwapResult with serialized transaction or error
        """
        if quote.status != JupiterRouteStatus.AVAILABLE or not quote.raw_quote:
            return JupiterSwapResult(
                success=False,
                swap_transaction=None,
                last_valid_block_height=None,
                simulation_error="Invalid or missing quote",
                compute_units=None,
                error="Quote not available for swap"
            )

        url = f"{self.BASE_URL}/swap"
        body = {
            "quoteResponse": quote.raw_quote,
            "userPublicKey": user_public_key,
            "dynamicComputeUnitLimit": dynamic_compute_unit_limit,
            "wrapAndUnwrapSol": True,
            "prioritizationFeeLamports": "auto"
        }

        logger.debug(f"Building swap transaction for {user_public_key[:8]}...")

        data = await self._make_request("POST", url, json_body=body)

        if not data:
            return JupiterSwapResult(
                success=False,
                swap_transaction=None,
                last_valid_block_height=None,
                simulation_error="Failed to build transaction",
                compute_units=None,
                error="Swap API request failed"
            )

        # Check for simulation error in response
        simulation_error = data.get("simulationError")
        swap_transaction = data.get("swapTransaction")

        if simulation_error:
            logger.warning(f"Jupiter simulation error: {simulation_error}")
            return JupiterSwapResult(
                success=False,
                swap_transaction=swap_transaction,
                last_valid_block_height=data.get("lastValidBlockHeight"),
                simulation_error=str(simulation_error),
                compute_units=data.get("computeUnitLimit"),
                raw_response=data,
                error=f"Simulation failed: {simulation_error}"
            )

        if not swap_transaction:
            return JupiterSwapResult(
                success=False,
                swap_transaction=None,
                last_valid_block_height=None,
                simulation_error="No transaction in response",
                compute_units=None,
                raw_response=data,
                error="Missing swap transaction"
            )

        logger.info("Jupiter swap transaction built successfully")
        return JupiterSwapResult(
            success=True,
            swap_transaction=swap_transaction,
            last_valid_block_height=data.get("lastValidBlockHeight"),
            simulation_error=None,
            compute_units=data.get("computeUnitLimit"),
            raw_response=data
        )

    async def get_sell_quote(
        self,
        token_mint: str,
        token_amount: int,
        slippage_bps: int = 100
    ) -> JupiterQuoteResult:
        """
        Convenience method: Get quote for selling tokens for SOL.

        Args:
            token_mint: Token to sell
            token_amount: Amount in atomic units
            slippage_bps: Acceptable slippage in basis points

        Returns:
            JupiterQuoteResult for selling token -> SOL
        """
        return await self.get_quote(
            input_mint=token_mint,
            output_mint=self.SOL_MINT,
            amount=token_amount,
            slippage_bps=slippage_bps
        )

    async def get_buy_quote(
        self,
        token_mint: str,
        sol_amount: int,
        slippage_bps: int = 100
    ) -> JupiterQuoteResult:
        """
        Convenience method: Get quote for buying tokens with SOL.

        Args:
            token_mint: Token to buy
            sol_amount: SOL amount in lamports
            slippage_bps: Acceptable slippage in basis points

        Returns:
            JupiterQuoteResult for buying SOL -> token
        """
        return await self.get_quote(
            input_mint=self.SOL_MINT,
            output_mint=token_mint,
            amount=sol_amount,
            slippage_bps=slippage_bps
        )
