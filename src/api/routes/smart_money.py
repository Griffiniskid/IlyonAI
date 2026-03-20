"""Smart money API routes."""

from aiohttp import web

from src.api.response_envelope import envelope_response
from src.api.schemas.responses import SmartMoneyOverviewResponse


async def get_smart_money_overview(request: web.Request) -> web.Response:
    payload = SmartMoneyOverviewResponse().model_dump(mode="json")
    return envelope_response(payload, meta={"surface": "smart_money_overview"})


def setup_smart_money_routes(app: web.Application):
    app.router.add_get("/api/v1/smart-money/overview", get_smart_money_overview)
