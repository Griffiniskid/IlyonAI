"""Integration: run the demo prompt against an in-memory app and assert the
SSE stream matches the demo contract.

Uses aiohttp's TestServer directly (no pytest-aiohttp dependency).
Network calls to DefiLlama are stubbed with a small fixture.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.api.schemas.agent import AgentCard


DEMO_PROMPT = (
    "I have $10,000 USDC. Allocate it across the best staking and yield "
    "opportunities, risk-weighted using Sentinel scores."
)


DEMO_POOLS = [
    {"project": "lido", "symbol": "STETH", "chain": "Ethereum", "tvlUsd": 24_500_000_000,
     "apy": 3.1, "ilRisk": "no", "stablecoin": False},
    {"project": "rocket-pool", "symbol": "RETH", "chain": "Ethereum", "tvlUsd": 3_400_000_000,
     "apy": 2.9, "ilRisk": "no", "stablecoin": False},
    {"project": "jito", "symbol": "JITOSOL", "chain": "Solana", "tvlUsd": 2_100_000_000,
     "apy": 7.2, "ilRisk": "no", "stablecoin": False},
    {"project": "aave-v3", "symbol": "AARBUSDC", "chain": "Arbitrum", "tvlUsd": 890_000_000,
     "apy": 4.8, "ilRisk": "no", "stablecoin": True},
    {"project": "pendle", "symbol": "PT-sUSDe", "chain": "Ethereum", "tvlUsd": 320_000_000,
     "apy": 18.2, "ilRisk": "no", "stablecoin": True},
    # noise filtered by composer
    {"project": "junk", "symbol": "JUNK", "chain": "Ethereum", "tvlUsd": 500_000,
     "apy": 612000, "ilRisk": "yes", "stablecoin": False},
]


class _StubDefiLlama:
    async def get_pools(self, **_kwargs):
        return DEMO_POOLS


def _parse_sse(raw: bytes) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    event = None
    data_parts: list[str] = []
    for raw_line in raw.split(b"\n"):
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_parts.append(line[5:].strip())
        elif line == "":
            if event and data_parts:
                try:
                    frames.append((event, json.loads("".join(data_parts))))
                except json.JSONDecodeError:
                    frames.append((event, {"_raw": "".join(data_parts)}))
            event = None
            data_parts = []
    return frames


async def _run_demo() -> list[tuple[str, dict]]:
    from src.api.app import create_api_app
    from src.agent import services as agent_services_mod
    from src.storage import database as storage_db_mod

    async def _stub_get(self):
        self.defillama = _StubDefiLlama()
        self.price = None
        self.jupiter = None
        self.dexscreener = None
        self.moralis = None
        self.solana = None
        self.initialized = True
        return self

    orig_init = agent_services_mod.AgentServices.initialize
    agent_services_mod.AgentServices.initialize = _stub_get

    # Fresh singleton
    import src.agent.services as _svc
    if hasattr(_svc, "_instance"):
        _svc._instance = None

    try:
        app = create_api_app()
        await storage_db_mod.init_database()
        server = TestServer(app)
        client = TestClient(server)
        await client.start_server()
        try:
            resp = await client.post(
                "/api/v1/agent",
                json={"session_id": "demo-test", "message": DEMO_PROMPT},
            )
            assert resp.status == 200, await resp.text()
            body = await resp.read()
            return _parse_sse(body)
        finally:
            await client.close()
    finally:
        agent_services_mod.AgentServices.initialize = orig_init


def test_demo_prompt_emits_three_cards():
    frames = asyncio.run(_run_demo())
    assert frames, "no SSE frames received"

    events: dict[str, list[dict]] = {}
    for ev, data in frames:
        events.setdefault(ev, []).append(data)

    assert "error" not in events, events.get("error")
    assert events.get("thought"), "expected thought frames"
    thought_lines = [frame["content"] for frame in events.get("thought", [])]
    assert len(thought_lines) >= 8
    assert any("Parsed intent" in line for line in thought_lines)
    assert any("DefiLlama" in line for line in thought_lines)
    assert any("Ilyon Shield" in line for line in thought_lines)
    assert any("position cap" in line.lower() for line in thought_lines)
    tools = events.get("tool", [])
    assert tools, "expected tool frames"
    allocate_calls = [t for t in tools if t.get("name") == "allocate_plan"]
    assert len(allocate_calls) == 1, allocate_calls

    cards = events.get("card", [])
    types_seen = {c["card_type"] for c in cards}
    assert {"allocation", "sentinel_matrix", "execution_plan"}.issubset(types_seen), types_seen

    for c in cards:
        AgentCard.model_validate({
            "card_id": c["card_id"],
            "card_type": c["card_type"],
            "payload": c["payload"],
        })

    allocation = next(c for c in cards if c["card_type"] == "allocation")["payload"]
    assert len(allocation["positions"]) == 5
    assert allocation["total_usd"] == "$10,000"
    assert allocation["chains"] >= 2

    plan = next(c for c in cards if c["card_type"] == "execution_plan")["payload"]
    assert len(plan["steps"]) == 5
    assert plan["requires_signature"] is True

    final = events.get("final", [])
    assert len(final) == 1
    assert "Sentinel" in final[0]["content"] or "sentinel" in final[0]["content"]
