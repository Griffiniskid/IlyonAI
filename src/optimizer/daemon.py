"""APScheduler-based opt-in rebalance daemon."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings
from src.optimizer.delta import MoveCandidate, should_move
from src.optimizer.notifier import notify_proposal
from src.optimizer.plan_synth import build_rebalance_intent
from src.optimizer.safety import SafetyGates, plan_ttl
from src.optimizer.snapshot import snapshot_from_user
from src.optimizer.target_builder import build_target
from src.storage.agent_plans import save_plan
from src.storage.database import get_database


class OptimizerDaemon:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._running = False

    async def start(self) -> bool:
        if not settings.OPTIMIZER_ENABLED:
            return False
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._snapshot_job,
            "interval",
            hours=6,
            jitter=300,
            id="snapshot_job",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._propose_job,
            "cron",
            hour=4,
            minute=0,
            jitter=300,
            id="propose_job",
            replace_existing=True,
        )
        self._scheduler.start()
        self._running = True
        return True

    async def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        self._running = False

    async def _snapshot_job(self) -> None:
        db = await get_database()
        # TODO: iterate opted-in users; for now, no-op if no user table exists yet.

    async def _propose_job(self) -> None:
        db = await get_database()
        from src.storage.agent_preferences import get_or_default
        # In production this iterates all opted-in users.
        # Stub: propose for a hardcoded user ID that can be overridden via env.
        import os
        user_id = int(os.environ.get("OPTIMIZER_TEST_USER", "0"))
        if not user_id:
            return
        prefs = await get_or_default(db, user_id=user_id)
        if not prefs.auto_rebalance_opt_in:
            return
        gates = SafetyGates(user_id=user_id)
        ok, reason = gates.can_propose(
            last_proposal_at=None,
            total_proposals_today=0,
        )
        if not ok:
            return

        holdings = await snapshot_from_user("")
        target = await build_target(holdings, risk_budget=prefs.risk_budget, total_usd=None)
        moves = []
        for h, t in zip(holdings, target):
            cand = MoveCandidate(
                usd_value=t.get("usd", 0),
                apy_delta=t.get("apy", 0) - h.get("apy", 0),
                sentinel_delta=t.get("sentinel", 0) - h.get("sentinel", 0),
                estimated_gas_usd=t.get("estimated_gas_usd", 20),
            )
            if should_move(cand):
                moves.append({"from": h, "to": t, "candidate": cand})

        if not moves:
            return

        from src.agent.planner import build_plan
        intent = build_rebalance_intent(moves)
        plan = build_plan(intent)
        await save_plan(
            db,
            user_id=user_id,
            payload=plan,
            status="proposed",
            expires_at=plan_ttl(),
        )
        await notify_proposal(user_id=user_id, plan_id=plan.plan_id, title=plan.title, db=db)
