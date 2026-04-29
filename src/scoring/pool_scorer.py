from __future__ import annotations

from typing import Any

from src.api.schemas.agent import SentinelBlock
from src.scoring.normalizer import pool_candidate_from_mapping
from src.scoring.rubric import sentinel_block_from_candidate


def score_pool_mapping(pool: dict[str, Any]) -> SentinelBlock:
    return sentinel_block_from_candidate(pool_candidate_from_mapping(pool))
