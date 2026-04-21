import pytest

from src.agent.tools._base import ToolCtx
from src.agent.tools import register_all_tools


class FakeServices:
    pass


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_tools_register():
    services = FakeServices()
    tools = register_all_tools(services=services, user_id=1, wallet="0xabc")
    assert len(tools) == 14
    names = {t.name for t in tools}
    expected = {
        "get_wallet_balance",
        "get_token_price",
        "simulate_swap",
        "build_swap_tx",
        "build_solana_swap",
        "get_defi_market_overview",
        "get_defi_analytics",
        "get_staking_options",
        "search_dexscreener_pairs",
        "find_liquidity_pool",
        "build_stake_tx",
        "build_deposit_lp_tx",
        "build_bridge_tx",
        "build_transfer_tx",
    }
    assert names == expected


# ---------------------------------------------------------------------------
# Individual tool tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_balance_tool():
    from src.agent.tools.balance import get_wallet_balance

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await get_wallet_balance(ctx, wallet="0xabc")
    assert env.ok
    assert env.card_type == "balance"
    assert env.card_payload["wallet"] == "0xabc"


@pytest.mark.asyncio
async def test_balance_tool_no_wallet():
    from src.agent.tools.balance import get_wallet_balance

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet=None)
    env = await get_wallet_balance(ctx)
    assert not env.ok
    assert env.error.code == "missing_wallet"


@pytest.mark.asyncio
async def test_price_tool():
    from src.agent.tools.price import get_token_price

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await get_token_price(ctx, token="ETH", chain="ethereum")
    assert env.ok
    assert env.card_type == "token"
    assert env.card_payload["symbol"] == "ETH"


@pytest.mark.asyncio
async def test_swap_simulate_tool():
    from src.agent.tools.swap_simulate import simulate_swap

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await simulate_swap(
        ctx, chain="ethereum", token_in="ETH", token_out="USDC", amount="1000000"
    )
    assert env.ok
    assert env.card_type == "swap_quote"
    assert env.card_payload["router"] == "auto"


@pytest.mark.asyncio
async def test_swap_build_tool():
    from src.agent.tools.swap_build import build_swap_tx

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await build_swap_tx(
        ctx,
        chain_id=1,
        token_in="ETH",
        token_out="USDC",
        amount_in="1000000",
        from_addr="0xabc",
    )
    assert env.ok
    assert env.card_type == "swap_quote"
    assert env.data["simulation"]["ok"] is True


@pytest.mark.asyncio
async def test_solana_swap_tool():
    from src.agent.tools.solana_swap import build_solana_swap

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="SoLWalleT")
    env = await build_solana_swap(
        ctx,
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount=1000000,
        user_public_key="SoLWalleT",
    )
    assert env.ok
    assert env.card_type == "swap_quote"
    assert env.data["unsigned"] is True


@pytest.mark.asyncio
async def test_market_overview_tool():
    from src.agent.tools.market_overview import get_defi_market_overview

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await get_defi_market_overview(ctx, limit=10)
    assert env.ok
    assert env.card_type == "market_overview"
    assert env.card_payload["protocols"] == []


@pytest.mark.asyncio
async def test_analytics_tool_deep():
    from src.agent.tools.analytics import get_defi_analytics

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await get_defi_analytics(ctx, protocol="aave", asset="ETH")
    assert env.ok
    assert env.card_type == "pool"
    assert env.card_payload["protocol"] == "aave"


@pytest.mark.asyncio
async def test_analytics_tool_list():
    from src.agent.tools.analytics import get_defi_analytics

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await get_defi_analytics(ctx, query="top pools")
    assert env.ok
    assert env.card_type == "market_overview"


@pytest.mark.asyncio
async def test_staking_tool():
    from src.agent.tools.staking import get_staking_options

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await get_staking_options(ctx, chain="ethereum")
    assert env.ok
    assert env.card_type == "allocation"
    assert env.card_payload["positions"] == []


@pytest.mark.asyncio
async def test_dex_search_tool():
    from src.agent.tools.dex_search import search_dexscreener_pairs

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await search_dexscreener_pairs(ctx, query="ETH/USDC")
    assert env.ok
    assert env.card_type == "pair_list"
    assert env.card_payload["query"] == "ETH/USDC"


@pytest.mark.asyncio
async def test_pool_find_tool():
    from src.agent.tools.pool_find import find_liquidity_pool

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await find_liquidity_pool(ctx, protocol="uniswap", asset="ETH")
    assert env.ok
    assert env.card_type == "pool"
    assert env.card_payload["protocol"] == "uniswap"


@pytest.mark.asyncio
async def test_stake_build_tool():
    from src.agent.tools.stake_build import build_stake_tx

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await build_stake_tx(
        ctx, protocol="lido", amount=1000000, user_addr="0xabc"
    )
    assert env.ok
    assert env.card_type == "stake"
    assert env.data["protocol"] == "lido"


@pytest.mark.asyncio
async def test_lp_build_tool():
    from src.agent.tools.lp_build import build_deposit_lp_tx

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await build_deposit_lp_tx(
        ctx,
        protocol="uniswap",
        token_a="ETH",
        token_b="USDC",
        amount_a="1000",
        amount_b="2000000",
        user_addr="0xabc",
    )
    assert env.ok
    assert env.card_type == "plan"
    assert env.card_payload["requires_signature"] is True


@pytest.mark.asyncio
async def test_bridge_build_tool():
    from src.agent.tools.bridge_build import build_bridge_tx

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await build_bridge_tx(
        ctx,
        src_chain_id=1,
        dst_chain_id=8453,
        token_in="ETH",
        token_out="ETH",
        amount="1000000",
        from_addr="0xabc",
    )
    assert env.ok
    assert env.card_type == "bridge"
    assert env.data["estimated_seconds"] == 300


@pytest.mark.asyncio
async def test_transfer_build_tool():
    from src.agent.tools.transfer_build import build_transfer_tx

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet="0xabc")
    env = await build_transfer_tx(
        ctx, to_addr="0xdef", amount="1000000", chain="ethereum"
    )
    assert env.ok
    assert env.card_type == "plan"
    assert env.data["to"] == "0xdef"


@pytest.mark.asyncio
async def test_transfer_build_tool_no_sender():
    from src.agent.tools.transfer_build import build_transfer_tx

    ctx = ToolCtx(services=FakeServices(), user_id=1, wallet=None)
    env = await build_transfer_tx(ctx, to_addr="0xdef", amount="1000000")
    assert not env.ok
    assert env.error.code == "missing_from"


# ---------------------------------------------------------------------------
# StructuredTool invocation via LangChain wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_langchain_tool_invocation():
    services = FakeServices()
    tools = register_all_tools(services=services, user_id=1, wallet="0xabc")
    balance_tool = next(t for t in tools if t.name == "get_wallet_balance")
    result = await balance_tool.ainvoke({"wallet": "0x123"})
    assert result.ok
    assert result.card_payload["wallet"] == "0x123"
