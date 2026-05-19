"""APR-by-range curve computation (spec §6e)."""
from src.defi.apr_curve.empirical_cdf import (
    compute_empirical_cdf_30d,
    empirical_cdf_or_fallback,
)
from src.defi.apr_curve.four_factor import (
    FourFactorAPRPoint,
    capital_efficiency,
    compose_apr_curve,
    fee_yield_full,
    il_drag,
)

__all__ = [
    "compute_empirical_cdf_30d",
    "empirical_cdf_or_fallback",
    "FourFactorAPRPoint",
    "capital_efficiency",
    "compose_apr_curve",
    "fee_yield_full",
    "il_drag",
]
