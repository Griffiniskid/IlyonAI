from src.agent.tools._base import ToolCtx, ok_envelope, err_envelope


async def build_transfer_tx(
    ctx, *, to_addr, amount, chain="ethereum", from_addr=None, chain_id=None
):
    from_addr = from_addr or ctx.wallet
    if not from_addr:
        return err_envelope("missing_from", "No sender address")
    data = {
        "steps": [
            {
                "step": 1,
                "action": "transfer",
                "detail": f"Send {amount} to {to_addr} on {chain}",
            }
        ],
        "requires_signature": True,
    }
    return ok_envelope(
        data={"to": to_addr, "amount": amount, "chain": chain},
        card_type="plan",
        card_payload=data,
    )
