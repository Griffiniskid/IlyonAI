"""
API route handlers for Solana Actions.
"""

from src.api.routes.actions import setup_actions_routes
from src.api.routes.blinks import setup_blinks_routes

__all__ = ["setup_actions_routes", "setup_blinks_routes"]
