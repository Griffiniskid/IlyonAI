import asyncio
import logging

from aiohttp import web
import json
import uuid

from src.alerts.audit_log import write_audit_record
from src.alerts.producer import AlertProducer
from src.alerts.store import InMemoryAlertStore
from src.api.middleware.webhook_signature import verify_webhook_signature
from src.api.routes.auth import require_auth, require_scope
from src.api.response_envelope import envelope_error_response, envelope_response
from src.config import settings


ALERT_STORE_KEY = web.AppKey("alert_store", InMemoryAlertStore)


def _get_store(request: web.Request) -> InMemoryAlertStore:
    return request.app[ALERT_STORE_KEY]


def _severity_is_valid(value: object) -> bool:
    if isinstance(value, str):
        return True
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    return False


def _validate_rule_payload(payload: object, *, partial: bool) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "payload must be object"

    name_present = "name" in payload
    severity_present = "severity" in payload

    if not partial:
        if not name_present or not severity_present:
            return False, "name and severity are required"

    if partial and not (name_present or severity_present):
        return False, "at least one of name or severity is required"

    if name_present and not isinstance(payload.get("name"), str):
        return False, "name must be string"

    if severity_present and not _severity_is_valid(payload.get("severity")):
        return False, "severity must be string or list[string]"

    return True, None


async def _enforce_optional_webhook_signature(request: web.Request, payload_text: str) -> web.Response | None:
    signature = request.headers.get("X-Webhook-Signature")
    if signature is None:
        return None

    secret = settings.webhook_signing_secret
    if not verify_webhook_signature(payload_text, signature, secret):
        return envelope_error_response(
            "Invalid webhook signature",
            code="INVALID_WEBHOOK_SIGNATURE",
            http_status=401,
        )

    return None

async def create_alert_rule(request: web.Request):
    store = _get_store(request)
    payload_text = await request.text()
    signature_error = await _enforce_optional_webhook_signature(request, payload_text)
    if signature_error is not None:
        return signature_error

    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        return envelope_error_response(
            "Invalid JSON payload",
            code="INVALID_REQUEST",
            http_status=400,
        )
    valid, error = _validate_rule_payload(payload, partial=False)
    if not valid:
        return envelope_error_response(error or "Invalid payload", code="INVALID_REQUEST", http_status=400)
    rule = store.create_rule(payload)
    actor_id = request.get("user_wallet", "anonymous")
    trace_id = request.headers.get("X-Trace-Id") or request.get("trace_id") or uuid.uuid4().hex
    await write_audit_record(
        "alert_rule.create",
        actor_id=actor_id,
        trace_id=trace_id,
        payload={"rule_id": rule.id, "name": rule.name},
    )
    return envelope_response(rule.model_dump(), http_status=201)


async def list_alert_rules(request: web.Request):
    store = _get_store(request)
    rules = [rule.model_dump() for rule in store.list_rules()]
    return envelope_response(rules)


async def get_alert_rule(request: web.Request):
    store = _get_store(request)
    rule_id = request.match_info["rule_id"]
    rule = store.get_rule(rule_id)
    if rule is None:
        return envelope_error_response("not found", code="NOT_FOUND", http_status=404)
    return envelope_response(rule.model_dump())


async def update_alert_rule(request: web.Request):
    store = _get_store(request)
    rule_id = request.match_info["rule_id"]
    payload_text = await request.text()
    signature_error = await _enforce_optional_webhook_signature(request, payload_text)
    if signature_error is not None:
        return signature_error

    try:
        payload = json.loads(payload_text or "{}")
    except json.JSONDecodeError:
        return envelope_error_response(
            "Invalid JSON payload",
            code="INVALID_REQUEST",
            http_status=400,
        )
    valid, error = _validate_rule_payload(payload, partial=True)
    if not valid:
        return envelope_error_response(error or "Invalid payload", code="INVALID_REQUEST", http_status=400)
    updated = store.update_rule(rule_id, payload)
    if updated is None:
        return envelope_error_response("not found", code="NOT_FOUND", http_status=404)
    actor_id = request.get("user_wallet", "anonymous")
    trace_id = request.headers.get("X-Trace-Id") or request.get("trace_id") or uuid.uuid4().hex
    await write_audit_record(
        "alert_rule.update",
        actor_id=actor_id,
        trace_id=trace_id,
        payload={"rule_id": updated.id, "name": updated.name},
    )
    return envelope_response(updated.model_dump())


async def delete_alert_rule(request: web.Request):
    store = _get_store(request)
    rule_id = request.match_info["rule_id"]
    payload_text = await request.text()
    signature_error = await _enforce_optional_webhook_signature(request, payload_text)
    if signature_error is not None:
        return signature_error

    deleted = store.delete_rule(rule_id)
    if not deleted:
        return envelope_error_response("not found", code="NOT_FOUND", http_status=404)
    actor_id = request.get("user_wallet", "anonymous")
    trace_id = request.headers.get("X-Trace-Id") or request.get("trace_id") or uuid.uuid4().hex
    await write_audit_record(
        "alert_rule.delete",
        actor_id=actor_id,
        trace_id=trace_id,
        payload={"rule_id": rule_id},
    )
    return web.Response(status=204)


create_alert_rule = require_auth(require_scope("alerts:write")(create_alert_rule))
update_alert_rule = require_auth(require_scope("alerts:write")(update_alert_rule))
delete_alert_rule = require_auth(require_scope("alerts:write")(delete_alert_rule))

async def list_alerts(request: web.Request):
    store = _get_store(request)
    severity = request.query.get("severity")
    alerts = [record.model_dump() for record in store.list_alerts(severity=severity)]
    return envelope_response(alerts)


async def update_alert(request: web.Request):
    store = _get_store(request)
    alert_id = request.match_info["alert_id"]

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return envelope_error_response(
            "Invalid JSON payload",
            code="INVALID_REQUEST",
            http_status=400,
        )

    if not isinstance(payload, dict):
        return envelope_error_response("payload must be object", code="INVALID_REQUEST", http_status=400)

    action = payload.get("action")
    allowed_actions = {"seen", "acknowledge", "snooze", "unsnooze", "resolve"}
    if not isinstance(action, str) or action not in allowed_actions:
        return envelope_error_response("invalid action", code="INVALID_REQUEST", http_status=400)

    try:
        updated = store.apply_alert_action(alert_id, action, payload.get("snoozed_until"))
    except ValueError as exc:
        return envelope_error_response(str(exc), code="INVALID_REQUEST", http_status=400)

    if updated is None:
        return envelope_error_response("not found", code="NOT_FOUND", http_status=404)

    return envelope_response(updated.model_dump())


async def _run_alert_producer(app: web.Application):
    """Background task that runs the alert producer every 5 minutes."""
    store = app[ALERT_STORE_KEY]
    producer = AlertProducer(store=store)
    while True:
        try:
            await producer.run_cycle()
        except Exception as e:
            logging.getLogger(__name__).warning(f"Alert producer cycle failed: {e}")
        await asyncio.sleep(300)  # 5 minutes


def setup_alert_routes(app: web.Application, store: InMemoryAlertStore | None = None):
    app[ALERT_STORE_KEY] = store or InMemoryAlertStore()
    app.router.add_post("/api/v1/alerts/rules", create_alert_rule)
    app.router.add_get("/api/v1/alerts/rules", list_alert_rules)
    app.router.add_get("/api/v1/alerts/rules/{rule_id}", get_alert_rule)
    app.router.add_put("/api/v1/alerts/rules/{rule_id}", update_alert_rule)
    app.router.add_delete("/api/v1/alerts/rules/{rule_id}", delete_alert_rule)
    app.router.add_get("/api/v1/alerts", list_alerts)
    app.router.add_patch("/api/v1/alerts/{alert_id}", update_alert)

    async def start_producer(app_ref: web.Application):
        app_ref["_alert_producer_task"] = asyncio.create_task(_run_alert_producer(app_ref))

    async def stop_producer(app_ref: web.Application):
        task = app_ref.get("_alert_producer_task")
        if task:
            task.cancel()

    app.on_startup.append(start_producer)
    app.on_cleanup.append(stop_producer)
