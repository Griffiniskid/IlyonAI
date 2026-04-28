from src.agent.tools._base import ToolCtx, ok_envelope, err_envelope


def _detect_chains(address: str) -> list[str]:
    # EVM addresses start with 0x and are 42 chars; everything else we try Solana.
    if address.startswith("0x") and len(address) == 42:
        return ["ethereum", "polygon", "bsc", "arbitrum", "optimism", "base", "avalanche"]
    return ["solana"]


async def get_wallet_balance(ctx: ToolCtx, *, wallet=None):
    addr = wallet or ctx.wallet
    if not addr:
        return err_envelope("missing_wallet", "No wallet address provided")

    by_chain: dict[str, str] = {}
    total_usd = 0.0

    moralis = getattr(ctx.services, "moralis", None)
    solana = getattr(ctx.services, "solana", None)

    chains = _detect_chains(addr)
    for chain in chains:
        try:
            if chain == "solana" and solana is not None:
                # Solana total value via the solana client (sum token + SOL USD).
                if hasattr(solana, "get_wallet_usd_value"):
                    usd = await solana.get_wallet_usd_value(addr)
                    by_chain["solana"] = f"{float(usd or 0):.2f}"
                    total_usd += float(usd or 0)
                elif hasattr(solana, "get_sol_price"):
                    bal = await solana.get_sol_balance(addr) if hasattr(solana, "get_sol_balance") else 0
                    price = await solana.get_sol_price() if hasattr(solana, "get_sol_price") else 0
                    usd = float(bal or 0) * float(price or 0)
                    by_chain["solana"] = f"{usd:.2f}"
                    total_usd += usd
            elif moralis is not None and hasattr(moralis, "get_wallet_token_balances"):
                tokens = await moralis.get_wallet_token_balances(addr, chain)
                usd = 0.0
                for t in tokens or []:
                    v = t.get("usd_value") or t.get("valueUsd") or 0
                    try:
                        usd += float(v)
                    except (TypeError, ValueError):
                        pass
                if usd > 0.0:
                    by_chain[chain] = f"{usd:.2f}"
                    total_usd += usd
        except Exception:
            # Never let one chain break the whole response.
            continue

    data = {
        "wallet": addr,
        "total_usd": f"{total_usd:,.2f}",
        "by_chain": by_chain or {chains[0]: "0.00"},
    }
    return ok_envelope(data=data, card_type="balance", card_payload=data)
