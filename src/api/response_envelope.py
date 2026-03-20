"""Shared API response envelope contracts."""

from typing import Any, Dict, List, Optional

from aiohttp import web

from pydantic import BaseModel, Field


def make_envelope(data: Any, *, status: str = "ok", meta: Optional[Dict[str, Any]] = None,
                  errors: Optional[List[Dict[str, Any]]] = None, trace_id: Optional[str] = None,
                  freshness: str = "live") -> Dict[str, Any]:
    """Build a standard API response envelope."""
    return {
        "status": status,
        "data": data,
        "meta": meta or {},
        "errors": errors or [],
        "trace_id": trace_id,
        "freshness": freshness,
    }


class ApiResponseMeta(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


class ApiResponseEnvelope(BaseModel):
    status: str = "ok"
    data: Any = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    trace_id: Optional[str] = None
    freshness: str = "live"


def envelope_response(
    data: Any,
    *,
    http_status: int = 200,
    status: str = "ok",
    meta: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    trace_id: Optional[str] = None,
    freshness: str = "live",
) -> web.Response:
    """Build an aiohttp JSON response using the shared envelope."""
    return web.json_response(
        make_envelope(
            data=data,
            status=status,
            meta=meta,
            errors=errors,
            trace_id=trace_id,
            freshness=freshness,
        ),
        status=http_status,
    )


def envelope_error_response(
    error: str,
    *,
    code: str,
    http_status: int,
    details: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    freshness: str = "live",
) -> web.Response:
    """Build an envelope error response with standard fields."""
    return envelope_response(
        data={},
        http_status=http_status,
        status="error",
        meta=meta,
        errors=[{"code": code, "message": error, "details": details or {}}],
        trace_id=trace_id,
        freshness=freshness,
    )
