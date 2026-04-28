"""BNB Greenfield client for long-term memory summaries.

Stub-mode when FEATURE_GREENFIELD_MEMORY=False: writes/reads from local tmpdir.
"""
import json
import os
import tempfile
from pathlib import Path
from src.config import settings


class GreenfieldClient:
    def __init__(self):
        self._stub_dir = Path(tempfile.gettempdir()) / "ilyon_greenfield_stub"
        if not settings.FEATURE_GREENFIELD_MEMORY:
            self._stub_dir.mkdir(parents=True, exist_ok=True)

    async def put_object(self, key: str, body: bytes) -> None:
        if settings.FEATURE_GREENFIELD_MEMORY:
            # TODO: real Greenfield SP HTTP API call
            pass
        else:
            self._stub_dir.joinpath(key.replace("/", "_")).write_bytes(body)

    async def get_object(self, key: str) -> bytes | None:
        if settings.FEATURE_GREENFIELD_MEMORY:
            # TODO: real Greenfield SP HTTP API call
            return None
        else:
            p = self._stub_dir.joinpath(key.replace("/", "_"))
            return p.read_bytes() if p.exists() else None
