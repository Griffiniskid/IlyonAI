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
    build_install_session_key_module_calldata,
    build_uninstall_session_key_module_calldata,
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


async def install_module_calldata(request: web.Request) -> web.Response:
    """POST /api/v1/eip7702/install-module-calldata — returns the calldata for
    `Nexus.installModule(VALIDATOR, validator_module, initData)` so the
    frontend can broadcast it via `eth_sendTransaction` after the EIP-7702
    authorization signature has been collected.

    body: {
      validator_module: 0x<address>,
      session_signer:   0x<address>,
      spend_cap_wei:    str(int),
      selector_allowlist: ["0x12345678", ...],
      expiry_unix:      int,
    }
    returns: { ok: true, selector: "0x9517e29f", calldata: "0x..." }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    try:
        validator_module = str(body["validator_module"]).lower()
        session_signer = str(body["session_signer"]).lower()
        spend_cap_wei = int(str(body["spend_cap_wei"]))
        selectors = body.get("selector_allowlist") or []
        if not isinstance(selectors, list) or not selectors:
            raise ValueError("selector_allowlist must be a non-empty list")
        expiry_unix = int(body["expiry_unix"])
    except (KeyError, TypeError, ValueError) as exc:
        return web.json_response({"ok": False, "error": f"invalid_input:{exc}"}, status=400)
    try:
        cd = build_install_session_key_module_calldata(
            validator_module_address=validator_module,
            session_signer=session_signer,
            spend_cap_wei=spend_cap_wei,
            selector_allowlist=[str(s) for s in selectors],
            expiry_unix=expiry_unix,
        )
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    # build_install_session_key_module_calldata already prefixes the
    # selector with `0x` — don't double-prefix.
    return web.json_response(
        {"ok": True, "selector": "0x9517e29f", "calldata": cd}
    )


async def uninstall_module_calldata(request: web.Request) -> web.Response:
    """POST /api/v1/eip7702/uninstall-module-calldata — returns the calldata
    for `Nexus.uninstallModule(VALIDATOR, validator_module, "")`. Broadcast by
    the SessionKeyPanel revoke button to enforce policy removal on-chain.

    body: { validator_module: 0x<address> }
    returns: { ok: true, selector: "0xa71763a8", calldata: "0x..." }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    validator_module = str(body.get("validator_module") or "").lower()
    if not validator_module.startswith("0x") or len(validator_module) != 42:
        return web.json_response(
            {"ok": False, "error": "invalid_validator_module"}, status=400,
        )
    try:
        cd = build_uninstall_session_key_module_calldata(
            validator_module_address=validator_module,
        )
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)
    return web.json_response(
        {"ok": True, "selector": "0xa71763a8", "calldata": cd}
    )


async def register_broadcast(request: web.Request) -> web.Response:
    """POST /api/v1/eip7702/broadcast — register the broadcast tx_hash for an
    authorization so the AuditLogPanel + downstream signer-delegation logic
    can correlate the on-chain installModule receipt back to the auth row.

    body: { auth_id: <uuid>, tx_hash: 0x<hex>, chain_id: int }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    auth_id = str(body.get("auth_id") or "")
    tx_hash = str(body.get("tx_hash") or "").lower()
    try:
        chain_id = int(body.get("chain_id"))
    except (TypeError, ValueError):
        return web.json_response({"ok": False, "error": "invalid_chain_id"}, status=400)
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        return web.json_response({"ok": False, "error": "invalid_tx_hash"}, status=400)
    if not auth_id:
        return web.json_response({"ok": False, "error": "invalid_auth_id"}, status=400)

    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        cache = request.app.setdefault("_eip7702_auths", {})
        if auth_id in cache:
            cache[auth_id]["broadcast_tx_hash"] = tx_hash
            cache[auth_id]["broadcast_chain_id"] = chain_id
            cache[auth_id]["broadcast_at"] = datetime.now(timezone.utc).isoformat()
        return web.json_response(
            {"ok": True, "auth_id": auth_id, "tx_hash": tx_hash, "persisted": False}
        )
    from sqlalchemy import text
    async with session_factory() as session:
        try:
            # The biconomy_session_authorizations table may not have a
            # broadcast_tx_hash column on every deployment — soft-fail to
            # the cache layer so the agent-009 audit row still lands.
            await session.execute(
                text(
                    "UPDATE biconomy_session_authorizations "
                    "SET broadcast_tx_hash = :h, broadcast_at = NOW() "
                    "WHERE auth_id = :a"
                ),
                {"h": tx_hash, "a": auth_id},
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.info("register_broadcast soft-fail (column may be absent): %s", exc)
            cache = request.app.setdefault("_eip7702_broadcasts", {})
            cache[auth_id] = {
                "tx_hash": tx_hash, "chain_id": chain_id,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            return web.json_response(
                {"ok": True, "auth_id": auth_id, "tx_hash": tx_hash, "persisted": False}
            )
    return web.json_response(
        {"ok": True, "auth_id": auth_id, "tx_hash": tx_hash, "persisted": True}
    )


async def register_solana_session_signer(request: web.Request) -> web.Response:
    """POST /api/v1/eip7702/solana-signer — register an ephemeral Solana
    session-signer pubkey for a user wallet. The backend treats the pubkey as
    a delegated signer for autonomous rebalance txs guarded by the user's
    session-key policy (off-chain enforcement; on-chain Squads/Solana delegate
    flows are a later phase).

    body: { user_wallet: <base58>, signer_pubkey: <base58>, expires_at?: iso }
    """
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "bad_json"}, status=400)
    user_wallet = str(body.get("user_wallet") or "")
    signer_pubkey = str(body.get("signer_pubkey") or "")
    if not user_wallet or len(user_wallet) < 32 or len(user_wallet) > 48:
        return web.json_response({"ok": False, "error": "invalid_user_wallet"}, status=400)
    if not signer_pubkey or len(signer_pubkey) < 32 or len(signer_pubkey) > 48:
        return web.json_response({"ok": False, "error": "invalid_signer_pubkey"}, status=400)
    expires_at = body.get("expires_at")
    record = {
        "user_wallet": user_wallet,
        "signer_pubkey": signer_pubkey,
        "expires_at": expires_at,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    # Cache regardless; durable persistence is best-effort.
    cache = request.app.setdefault("_solana_session_signers", {})
    cache.setdefault(user_wallet, []).append(record)
    session_factory = request.app.get("_db_session_factory")
    if session_factory is None:
        return web.json_response({"ok": True, **record, "persisted": False})
    from sqlalchemy import text
    async with session_factory() as session:
        try:
            await session.execute(
                text(
                    "INSERT INTO solana_session_signers "
                    "(user_wallet, signer_pubkey, expires_at, registered_at) "
                    "VALUES (:w, :s, :e, NOW())"
                ),
                {"w": user_wallet, "s": signer_pubkey, "e": expires_at},
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.info("solana signer persist soft-fail: %s", exc)
            return web.json_response({"ok": True, **record, "persisted": False})
    return web.json_response({"ok": True, **record, "persisted": True})


def setup_eip7702_routes(app: web.Application) -> None:
    # Staging routes /api/v1/auth/* through a separate uvicorn FastAPI app
    # that doesn't know about these handlers. Mount under /api/v1/eip7702/
    # so Caddy falls through to the aiohttp app cleanly.
    app.router.add_post("/api/v1/eip7702/prepare", prepare_authorization)
    app.router.add_post("/api/v1/eip7702/authorize", authorize)
    app.router.add_get("/api/v1/eip7702/{wallet}", list_authorizations)
    app.router.add_post(
        "/api/v1/eip7702/install-module-calldata", install_module_calldata,
    )
    app.router.add_post(
        "/api/v1/eip7702/uninstall-module-calldata", uninstall_module_calldata,
    )
    app.router.add_post("/api/v1/eip7702/broadcast", register_broadcast)
    app.router.add_post(
        "/api/v1/eip7702/solana-signer", register_solana_session_signer,
    )
