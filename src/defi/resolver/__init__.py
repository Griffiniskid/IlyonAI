"""Centralized entity resolution (V7-015).

Replaces scattered adapter-local `_resolve_token` / `_resolve_pool` / chain-id
helpers with a single `EntityResolver` service that consults the canonical
registries in `src/data/`.

Spec §3 — centralized entity resolution.
"""
from __future__ import annotations

from src.defi.resolver.entity_resolver import (
    ChainInfo,
    EntityResolver,
    TokenInfo,
)

__all__ = ["EntityResolver", "TokenInfo", "ChainInfo"]
