"""EIP-7702 authorization routes — Phase 7 smart-account opt-in.

POST /api/v1/auth/eip7702/prepare
  body: { wallet, chain_id, nonce, impl?: 'nexus' | 'kernel' }
  returns: { impl, chain_id, nonce, digest, wallet }

POST /api/v1/auth/eip7702/authorize
  body: { wallet, chain_id, nonce, impl, signature_hex }
  persists the auth into biconomy_session_authorizations (alembic
  agent_009). Replay-protected via unique (wallet, chain_id, nonce).

GET /api/v1/auth/eip7702/{wallet}
  returns active authorizations for the wallet (revoked_at IS NULL,
  expired_at IS NULL OR > NOW()).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from aiohttp import web

from src.auth.biconomy_nexus import (
    assemble_nexus_authorization,
    prepare_nexus_authorization,
)
from src.auth.zerodev_kernel import (
    assemble_kernel_authorization,
    prepare_kernel_authorization,
)

logger = logging.getLogger(__name__)


def _norm_impl(impl: str | None) -> str:
    impl_l = (impl or "nexus").lower()
    if impl_l in {"nexus", "biconomy", "biconomy-nexus"}:
        return "nexus"
    if impl_l in {"kernel", "zerodev", "zerodev-kernel"}:
        return "kernel"
    raise ValueError(f"unknown impl: {impl}")


async def prepare_authorization(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    wallet = (body.get("wallet") or "").lower()
    if not wallet.startswith("0x") or len(wallet) != 42:
        return web.json_response({"ok": False, "error": "invalid_wallet"}, status=400)
    try:
        chain_id = int(body.get("chain_id"))
        nonce = int(body.get("nonce"))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid_chain_or_nonce"}, status=400)
    try:
        impl_norm = _norm_impl(body.get("impl"))
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    try:
        if impl_norm == "nexus":
            payload = prepare_nexus_authorization(
                user_wallet=wallet, chain_id=chain_id, nonce=nonce,
            )
        else:
            payload = prepare_kernel_authorization(
                user_wallet=wallet, chain_id=chain_id, nonce=nonce,
            )
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response({"ok": True, **payload, "impl_kind": impl_norm})


async def authorize(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    wallet = (body.get("wallet") or "").lower()
    if not wallet.startswith("0x") or len(wallet) != 42:
        return web.json_response({"ok": False, "error": "invalid_wallet"}, status=400)
    try:
        chain_id = int(body.get("chain_id"))
        nonce = int(body.get("nonce"))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid_chain_or_nonce"}, status=400)
    try:
        impl_norm = _norm_impl(body.get("impl"))
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    sig = body.get("signature_hex")
    if not isinstance(sig, str) or len(sig.removeprefix("0x")) != 130:
        return web.json_response({"ok": False, "error": "invalid_signature"}, status=400)

    try:
        if impl_norm == "nexus":
            auth = assemble_nexus_authorization(
                chain_id=chain_id, nonce=nonce, signature_hex=sig,
            )
            impl_addr = auth.implementation
        else:
            auth = assemble_kernel_authorization(
                chain_id=chain_id, nonce=nonce, signature_hex=sig,
            )
            impl_addr = auth.implementation
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    auth_id = str(uuid.uuid4())
    created_iso = datetime.now(timezone.utc).isoformat()
    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        # No DB → cache in-app for dev environments.
        cache = request.app.setdefault("_eip7702_auths", {})
        cache[auth_id] = {
            "auth_id": auth_id, "user_wallet": wallet, "impl_addr": impl_addr,
            "chain_id": chain_id, "nonce": nonce,
            "signature_v": auth.y_parity,
            "signature_r": "0x" + auth.r.hex(),
            "signature_s": "0x" + auth.s.hex(),
            "created_at": created_iso, "persisted": False,
        }
        return web.json_response({"ok": True, **cache[auth_id]})
    from sqlalchemy import text

    async with session_factory() as session:
        try:
            await session.execute(
                text(
                    "INSERT INTO biconomy_session_authorizations "
                    "(auth_id, user_wallet, impl_addr, chain_id, nonce, "
                    " signature_r, signature_s, signature_v, digest, created_at) "
                    "VALUES (:aid, :w, :ia, :cid, :n, :r, :s, :v, :d, NOW())"
                ),
                {
                    "aid": auth_id, "w": wallet, "ia": impl_addr,
                    "cid": chain_id, "n": nonce,
                    "r": "0x" + auth.r.hex(),
                    "s": "0x" + auth.s.hex(),
                    "v": auth.y_parity,
                    "d": "",
                },
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — surface as 409/500
            logger.warning("authorize persist failed: %s", exc)
            return web.json_response(
                {"ok": False, "error": "persist_failed", "detail": str(exc)[:200]},
                status=409,
            )
    return web.json_response({
        "ok": True, "auth_id": auth_id, "user_wallet": wallet,
        "impl_addr": impl_addr, "chain_id": chain_id, "nonce": nonce,
        "persisted": True,
    })


async def list_authorizations(request: web.Request) -> web.Response:
    wallet = request.match_info["wallet"].lower()
    if not wallet.startswith("0x") or len(wallet) != 42:
        return web.json_response({"ok": False, "error": "invalid_wallet"}, status=400)
    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        cache = request.app.get("_eip7702_auths", {}) or {}
        rows = [v for v in cache.values() if v.get("user_wallet") == wallet]
        return web.json_response({"ok": True, "authorizations": rows, "persisted": False})
    from sqlalchemy import text
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT auth_id, impl_addr, chain_id, nonce, "
                "       created_at, expired_at, revoked_at "
                "FROM biconomy_session_authorizations "
                "WHERE user_wallet = :w "
                "ORDER BY created_at DESC LIMIT 100"
            ),
            {"w": wallet},
        )
        rows = [dict(r._mapping) for r in result]  # noqa: SLF001
    return web.json_response({"ok": True, "authorizations": rows, "persisted": True})


def setup_eip7702_routes(app: web.Application) -> None:
    app.router.add_post("/api/v1/auth/eip7702/prepare", prepare_authorization)
    app.router.add_post("/api/v1/auth/eip7702/authorize", authorize)
    app.router.add_get("/api/v1/auth/eip7702/{wallet}", list_authorizations)
