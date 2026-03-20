import asyncio
import json
import logging

from aiohttp import web

from src.platform.stream_hub import get_stream_hub
from src.api.middleware.replay_guard import ReplayGuard
from src.api.response_envelope import envelope_error_response
from src.config import settings

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15
_stream_replay_guard = ReplayGuard(
    ttl_seconds=settings.replay_guard_ttl_seconds,
    max_skew_seconds=settings.replay_guard_max_skew_seconds,
)


def _topic_from_request(request: web.Request) -> str | None:
    topic = request.query.get("topic", "").strip()
    return topic or None


async def _enforce_replay_guard(request: web.Request) -> web.Response | None:
    nonce = request.headers.get("X-Replay-Nonce")
    ts = request.headers.get("X-Replay-Timestamp")
    actor_id = request.get("user_wallet") or request.headers.get("X-Actor-Id")

    if not (nonce and ts and actor_id):
        return None

    try:
        timestamp = int(ts)
    except ValueError:
        return envelope_error_response(
            "Invalid replay timestamp",
            code="INVALID_REPLAY_TIMESTAMP",
            http_status=400,
        )

    accepted = await _stream_replay_guard.accept(actor_id, nonce, timestamp)
    if accepted:
        return None

    return envelope_error_response(
        "Replay guard rejected request",
        code="REPLAY_REJECTED",
        http_status=401,
    )


async def ws_stream(request: web.Request) -> web.StreamResponse:
    replay_error = await _enforce_replay_guard(request)
    if replay_error is not None:
        return replay_error

    topic = _topic_from_request(request)
    if topic is None:
        return envelope_error_response(
            "Missing required query parameter: topic",
            code="INVALID_QUERY",
            http_status=400,
        )

    hub = get_stream_hub()
    queue = await hub.subscribe(topic)

    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    try:
        while not ws.closed:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                continue
            await ws.send_json(event)
    except (ConnectionResetError, RuntimeError):
        pass
    finally:
        hub.unsubscribe(queue)

    return ws


async def sse_stream(request: web.Request) -> web.StreamResponse:
    replay_error = await _enforce_replay_guard(request)
    if replay_error is not None:
        return replay_error

    topic = _topic_from_request(request)
    if topic is None:
        return envelope_error_response(
            "Missing required query parameter: topic",
            code="INVALID_QUERY",
            http_status=400,
        )

    hub = get_stream_hub()
    queue = await hub.subscribe(topic)

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                transport = request.transport
                if transport is None or transport.is_closing():
                    break
                await response.write(b": keepalive\n\n")
                continue
            payload = f"data: {json.dumps(event)}\n\n".encode("utf-8")
            await response.write(payload)
    except (ConnectionResetError, RuntimeError):
        pass
    finally:
        hub.unsubscribe(queue)

    return response


def setup_stream_routes(app: web.Application) -> None:
    app.router.add_get("/api/v1/stream/ws", ws_stream)
    app.router.add_get("/api/v1/stream/sse", sse_stream)
    logger.info("Stream routes registered")
