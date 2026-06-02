import asyncio
from types import SimpleNamespace

from src.agent.tools.execute_pool_position import execute_pool_position


async def one(i: int) -> None:
    ctx = SimpleNamespace(
        wallet="0x1111111111111111111111111111111111111111",
        evm_wallet="0x1111111111111111111111111111111111111111",
        solana_wallet=None,
        user_id="t",
        session_id="t",
    )
    r = await execute_pool_position(
        ctx,
        pool="1ba6ccca-7122-47ce-854e-06883f9b2897",
        amount=10,
        amount_is_usd=True,
        asset_in="BUSD",
        chain="bsc",
        extra={"user_message": "x"},
    )
    d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
    cp = d.get("card_payload") or {}
    bl = cp.get("blockers") or []
    parts = []
    for b in bl:
        msg = b.get("detail") or b.get("title") or b.get("code") or ""
        parts.append(msg[:90])
    status = cp.get("status")
    print("run {}: status={} blockers={} :: {}".format(i, status, len(bl), " | ".join(parts)[:160]))


async def main() -> None:
    for i in range(8):
        try:
            await one(i)
        except Exception as e:  # noqa: BLE001
            print("run {}: EXC {}: {}".format(i, type(e).__name__, str(e)[:140]))


if __name__ == "__main__":
    asyncio.run(main())
