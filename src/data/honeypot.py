"""
Honeypot detection for Solana tokens via transaction simulation.

Detects tokens that cannot be sold (honeypots) by simulating sell transactions
through Jupiter and Solana RPC. This approach is more reliable than static
code analysis because scammers can hide malicious logic.

Detection works by:
1. Building a sell transaction (token -> SOL) via Jupiter
2. Simulating the transaction via Solana RPC
3. Analyzing results to detect:
   - Complete sell blocks (honeypots)
   - High sell taxes (partial honeypots)
   - Normal tokens (can sell freely)
"""

import logging
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum

from src.data.jupiter import JupiterClient, JupiterRouteStatus
from src.data.solana import SolanaClient
from src.config import settings

logger = logging.getLogger(__name__)


class HoneypotStatus(Enum):
    """Classification of honeypot detection result."""
    SAFE = "safe"                        # Can sell normally
    HIGH_TAX = "high_tax"                # Can sell but high tax (>20%)
    EXTREME_TAX = "extreme_tax"          # Can sell but extreme tax (>50%)
    HONEYPOT = "honeypot"                # Cannot sell (simulation fails)
    UNABLE_TO_VERIFY = "unable_to_verify"  # No route available
    ERROR = "error"                      # Detection failed


@dataclass
class HoneypotResult:
    """Result of honeypot detection."""
    status: HoneypotStatus
    is_honeypot: bool
    confidence: float  # 0-1 confidence score

    # Sell tax analysis
    sell_tax_percent: Optional[float] = None  # Effective sell tax %
    expected_output_lamports: int = 0         # What we expected
    actual_output_lamports: int = 0           # What simulation showed

    # Simulation details
    simulation_success: bool = False
    simulation_error: Optional[str] = None
    simulation_logs: List[str] = field(default_factory=list)

    # Route information
    route_available: bool = False
    route_dex: Optional[str] = None  # Primary DEX in route
    price_impact_pct: float = 0.0

    # Warnings and explanations
    warnings: List[str] = field(default_factory=list)
    explanation: str = ""
    error: Optional[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.simulation_logs is None:
            self.simulation_logs = []


class HoneypotDetector:
    """
    Detects honeypot tokens using Jupiter quote + Solana simulation.

    Detection Flow:
    1. Get Jupiter quote for selling 0.1 SOL worth of tokens -> SOL
    2. Build swap transaction via Jupiter
    3. Simulate transaction via Solana RPC
    4. Analyze results:
       - Simulation error/failure -> Honeypot
       - Success but 0 output -> 100% sell tax honeypot
       - Success with low output -> High sell tax
       - Success with expected output -> Safe

    Note: If Jupiter has no route, we mark as "unable to verify",
    NOT as honeypot (per user requirements).
    """

    # Tax thresholds (from config)
    HIGH_TAX_THRESHOLD = settings.honeypot_high_tax_threshold
    EXTREME_TAX_THRESHOLD = settings.honeypot_extreme_tax_threshold
    HONEYPOT_TAX_THRESHOLD = 95.0   # 95%+ is effectively a honeypot

    # Simulation parameters (from config)
    DEFAULT_SELL_AMOUNT_SOL = settings.honeypot_simulation_amount_sol
    LAMPORTS_PER_SOL = 1_000_000_000

    # Dummy wallet for simulation (doesn't need to exist with funds)
    # Using a valid but unfunded wallet for simulation
    SIMULATION_WALLET = "GjcqPprUxwY3xhp5xf2JA5jUZ2B2RYvXaBwajAZw4oeT"

    def __init__(
        self,
        jupiter_client: Optional[JupiterClient] = None,
        solana_client: Optional[SolanaClient] = None,
        rpc_url: Optional[str] = None
    ):
        """
        Initialize honeypot detector.

        Args:
            jupiter_client: Optional JupiterClient instance
            solana_client: Optional SolanaClient instance
            rpc_url: Solana RPC URL (used if solana_client not provided)
        """
        self.jupiter = jupiter_client
        self.solana = solana_client
        self.rpc_url = rpc_url
        self._owns_jupiter = jupiter_client is None
        self._owns_solana = solana_client is None
        logger.info("Honeypot detector initialized with Jupiter simulation")

    async def _ensure_clients(self):
        """Ensure Jupiter and Solana clients are initialized."""
        if self.jupiter is None:
            self.jupiter = JupiterClient()
        if self.solana is None and self.rpc_url:
            self.solana = SolanaClient(self.rpc_url)

    async def close(self):
        """Cleanup resources."""
        if self._owns_jupiter and self.jupiter:
            await self.jupiter.close()
        if self._owns_solana and self.solana:
            await self.solana.close()

    async def check(
        self,
        token_address: str,
        token_decimals: int = 9,
        token_price_usd: float = 0.0,
        sol_price_usd: float = 150.0
    ) -> HoneypotResult:
        """
        Check if a token is a honeypot by simulating a sell.

        Args:
            token_address: Solana token mint address
            token_decimals: Token decimal places
            token_price_usd: Current token price (for amount calculation)
            sol_price_usd: Current SOL price

        Returns:
            HoneypotResult with detection findings
        """
        await self._ensure_clients()

        try:
            # Step 1: Calculate token amount for 0.1 SOL worth
            token_amount = self._calculate_token_amount(
                token_price_usd=token_price_usd,
                token_decimals=token_decimals,
                target_sol_value=self.DEFAULT_SELL_AMOUNT_SOL,
                sol_price_usd=sol_price_usd
            )

            if token_amount <= 0:
                return self._create_unable_to_verify_result(
                    "Cannot calculate token amount - missing price data"
                )

            logger.info(
                f"Checking honeypot for {token_address[:8]}..., "
                f"simulating sell of {token_amount} atomic units"
            )

            # Step 2: Get Jupiter quote for selling tokens -> SOL
            quote = await self.jupiter.get_sell_quote(
                token_mint=token_address,
                token_amount=token_amount,
                slippage_bps=100  # 1% slippage
            )

            if quote.status == JupiterRouteStatus.NO_ROUTE:
                logger.info(f"No Jupiter route for {token_address[:8]}")
                return self._create_unable_to_verify_result(
                    "No Jupiter route available for this token"
                )

            if quote.status == JupiterRouteStatus.ERROR:
                logger.warning(f"Jupiter API error for {token_address[:8]}: {quote.error}")
                return self._create_unable_to_verify_result(
                    f"Jupiter API error: {quote.error}"
                )

            # Step 3: Build swap transaction
            swap = await self.jupiter.build_swap_transaction(
                quote=quote,
                user_public_key=self.SIMULATION_WALLET
            )

            if not swap.success or not swap.swap_transaction:
                # Jupiter itself reported a simulation error
                return self._analyze_jupiter_failure(
                    quote=quote,
                    swap=swap,
                    token_address=token_address
                )

            # Step 4: Additional Solana RPC simulation (optional, for extra confidence)
            # Jupiter already simulates, but we can double-check
            if self.solana:
                simulation = await self.solana.simulate_transaction(
                    transaction_base64=swap.swap_transaction
                )

                if not simulation.success:
                    return self._analyze_rpc_simulation_failure(
                        quote=quote,
                        simulation=simulation,
                        token_address=token_address
                    )

            # Step 5: Analyze quote results for tax detection
            return self._analyze_quote_results(
                quote=quote,
                token_address=token_address,
                token_amount=token_amount,
                target_sol_lamports=int(self.DEFAULT_SELL_AMOUNT_SOL * self.LAMPORTS_PER_SOL)
            )

        except Exception as e:
            logger.error(f"Honeypot check failed for {token_address[:8]}: {e}", exc_info=True)
            return HoneypotResult(
                status=HoneypotStatus.ERROR,
                is_honeypot=False,  # Don't assume honeypot on error
                confidence=0.0,
                error=str(e),
                explanation="Honeypot detection encountered an error"
            )

    def _calculate_token_amount(
        self,
        token_price_usd: float,
        token_decimals: int,
        target_sol_value: float,
        sol_price_usd: float
    ) -> int:
        """
        Calculate token amount for target SOL value.

        Returns:
            Token amount in atomic units (with decimals applied)
        """
        if token_price_usd <= 0 or sol_price_usd <= 0:
            return 0

        target_usd = target_sol_value * sol_price_usd
        token_amount = target_usd / token_price_usd
        atomic_amount = int(token_amount * (10 ** token_decimals))

        logger.debug(
            f"Calculated token amount: {token_amount:.2f} tokens "
            f"({atomic_amount} atomic) for ${target_usd:.2f}"
        )
        return atomic_amount

    def _analyze_jupiter_failure(
        self,
        quote,
        swap,
        token_address: str
    ) -> HoneypotResult:
        """
        Analyze why Jupiter swap building failed - likely honeypot.
        """
        error_msg = swap.simulation_error or swap.error or "Unknown error"

        # Check for common honeypot error patterns
        honeypot_indicators = [
            "insufficient funds",
            "transfer amount exceeds",
            "custom program error",
            "account not found",
            "invalid account",
            "exceeds desired",
            "slippage",
        ]

        is_likely_honeypot = any(
            indicator in error_msg.lower()
            for indicator in honeypot_indicators
        )

        # Check if it's a slippage issue (high tax indicator)
        is_slippage_issue = "slippage" in error_msg.lower() or "exceeds" in error_msg.lower()

        if is_slippage_issue:
            # This likely indicates extremely high tax
            logger.warning(f"Slippage error for {token_address[:8]} - likely extreme tax")
            return HoneypotResult(
                status=HoneypotStatus.EXTREME_TAX,
                is_honeypot=False,
                confidence=0.75,
                route_available=True,
                route_dex=self._extract_dex_from_route(quote.route_plan),
                price_impact_pct=quote.price_impact_pct,
                simulation_success=False,
                simulation_error=error_msg,
                warnings=["Extreme slippage detected - very high sell tax likely"],
                explanation=f"Transaction failed due to slippage: {error_msg}"
            )

        if is_likely_honeypot:
            logger.warning(f"Honeypot indicators found for {token_address[:8]}")
            return HoneypotResult(
                status=HoneypotStatus.HONEYPOT,
                is_honeypot=True,
                confidence=0.85,
                route_available=True,
                route_dex=self._extract_dex_from_route(quote.route_plan),
                price_impact_pct=quote.price_impact_pct,
                simulation_success=False,
                simulation_error=error_msg,
                warnings=["Token appears to block sell transactions"],
                explanation=f"Sell simulation failed: {error_msg}"
            )

        # Less confident - could be temporary issue
        return HoneypotResult(
            status=HoneypotStatus.UNABLE_TO_VERIFY,
            is_honeypot=False,
            confidence=0.5,
            route_available=True,
            simulation_success=False,
            simulation_error=error_msg,
            warnings=["Simulation failed but cause unclear"],
            explanation=f"Could not verify sellability: {error_msg}"
        )

    def _analyze_rpc_simulation_failure(
        self,
        quote,
        simulation,
        token_address: str
    ) -> HoneypotResult:
        """
        Analyze Solana RPC simulation failure.
        """
        error_msg = simulation.error or "Unknown simulation error"

        # Program errors usually indicate intentional blocks
        if simulation.error_code is not None:
            logger.warning(
                f"Program error {simulation.error_code} for {token_address[:8]}"
            )
            return HoneypotResult(
                status=HoneypotStatus.HONEYPOT,
                is_honeypot=True,
                confidence=0.9,
                route_available=True,
                route_dex=self._extract_dex_from_route(quote.route_plan),
                simulation_success=False,
                simulation_error=error_msg,
                simulation_logs=simulation.logs,
                warnings=[f"Program error {simulation.error_code} - sell blocked"],
                explanation=f"Transaction rejected by program: {error_msg}"
            )

        return HoneypotResult(
            status=HoneypotStatus.HONEYPOT,
            is_honeypot=True,
            confidence=0.8,
            route_available=True,
            route_dex=self._extract_dex_from_route(quote.route_plan),
            simulation_success=False,
            simulation_error=error_msg,
            simulation_logs=simulation.logs,
            warnings=["Sell transaction simulation failed"],
            explanation=f"Simulation failed: {error_msg}"
        )

    def _analyze_quote_results(
        self,
        quote,
        token_address: str,
        token_amount: int,
        target_sol_lamports: int
    ) -> HoneypotResult:
        """
        Analyze successful quote to detect sell tax.
        """
        expected_output = target_sol_lamports  # What we'd expect with 0 tax
        actual_output = quote.out_amount

        # Calculate effective sell tax based on price impact
        # High price impact = high effective tax
        if expected_output > 0 and actual_output > 0:
            # Tax = how much less we get than expected
            # Account for normal price impact (subtract small expected impact)
            base_impact = min(quote.price_impact_pct, 5.0)  # Normal impact up to 5%
            effective_ratio = actual_output / expected_output

            # If output is very low relative to expected, calculate tax
            if effective_ratio < 1.0:
                tax_percent = (1.0 - effective_ratio) * 100
            else:
                tax_percent = 0.0

            # Also consider reported price impact as tax indicator
            if quote.price_impact_pct > 30:
                tax_percent = max(tax_percent, quote.price_impact_pct)
        else:
            tax_percent = 0 if actual_output > 0 else 100

        # Classify result based on tax
        if tax_percent >= self.HONEYPOT_TAX_THRESHOLD:
            status = HoneypotStatus.HONEYPOT
            is_honeypot = True
            confidence = 0.95
            warnings = [f"Effective {tax_percent:.1f}% sell tax = honeypot"]
            logger.warning(f"HONEYPOT: {token_address[:8]} has {tax_percent:.1f}% tax")
        elif tax_percent >= self.EXTREME_TAX_THRESHOLD:
            status = HoneypotStatus.EXTREME_TAX
            is_honeypot = False
            confidence = 0.9
            warnings = [f"Extreme {tax_percent:.1f}% sell tax detected"]
            logger.warning(f"Extreme tax: {token_address[:8]} has {tax_percent:.1f}% tax")
        elif tax_percent >= self.HIGH_TAX_THRESHOLD:
            status = HoneypotStatus.HIGH_TAX
            is_honeypot = False
            confidence = 0.85
            warnings = [f"High {tax_percent:.1f}% sell tax detected"]
            logger.info(f"High tax: {token_address[:8]} has {tax_percent:.1f}% tax")
        else:
            status = HoneypotStatus.SAFE
            is_honeypot = False
            confidence = 0.9
            warnings = []
            logger.info(f"SAFE: {token_address[:8]} can be sold (tax: {tax_percent:.1f}%)")

        return HoneypotResult(
            status=status,
            is_honeypot=is_honeypot,
            confidence=confidence,
            sell_tax_percent=tax_percent,
            expected_output_lamports=expected_output,
            actual_output_lamports=actual_output,
            simulation_success=True,
            route_available=True,
            route_dex=self._extract_dex_from_route(quote.route_plan),
            price_impact_pct=quote.price_impact_pct,
            warnings=warnings,
            explanation=self._build_explanation(status, tax_percent)
        )

    def _create_unable_to_verify_result(self, reason: str) -> HoneypotResult:
        """Create result for unable to verify cases."""
        logger.info(f"Unable to verify honeypot: {reason}")
        return HoneypotResult(
            status=HoneypotStatus.UNABLE_TO_VERIFY,
            is_honeypot=False,  # Don't assume risk
            confidence=0.0,
            route_available=False,
            warnings=[reason],
            explanation=f"Unable to verify sellability: {reason}"
        )

    def _extract_dex_from_route(self, route_plan: list) -> Optional[str]:
        """Extract primary DEX name from route plan."""
        if route_plan:
            try:
                first_hop = route_plan[0]
                swap_info = first_hop.get("swapInfo", {})
                return swap_info.get("label", "Unknown DEX")
            except (IndexError, KeyError, TypeError):
                pass
        return None

    def _build_explanation(self, status: HoneypotStatus, tax_percent: float) -> str:
        """Build human-readable explanation."""
        if status == HoneypotStatus.SAFE:
            if tax_percent > 0:
                return f"Token can be sold with {tax_percent:.1f}% tax"
            return "Token can be sold normally with minimal tax"
        elif status == HoneypotStatus.HIGH_TAX:
            return f"Token has {tax_percent:.1f}% sell tax - trading is expensive"
        elif status == HoneypotStatus.EXTREME_TAX:
            return f"Token has {tax_percent:.1f}% sell tax - most value lost on sell"
        elif status == HoneypotStatus.HONEYPOT:
            return "Token cannot be sold - this is a honeypot"
        else:
            return "Sellability could not be verified"


# Global instance
_detector: Optional[HoneypotDetector] = None


def get_honeypot_detector(rpc_url: Optional[str] = None) -> HoneypotDetector:
    """Get or create global honeypot detector instance."""
    global _detector
    if _detector is None:
        _detector = HoneypotDetector(rpc_url=rpc_url)
    return _detector
