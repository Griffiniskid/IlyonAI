"""Tool context for agent execution.

Provides wallet and services access to agent tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolContext:
    """Context passed to agent tools.
    
    Attributes:
        wallet: Optional wallet address for the session
        services: Dictionary of service clients (price, portfolio, etc.)
    """
    wallet: Optional[str] = None
    services: dict[str, Any] = field(default_factory=dict)
    
    def get_service(self, name: str) -> Optional[Any]:
        """Get a service by name."""
        return self.services.get(name)
