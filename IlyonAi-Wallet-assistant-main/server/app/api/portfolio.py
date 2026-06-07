"""
Portfolio endpoint — 15-chain native + USDC + USDT balance scanner.
No API keys required; uses public RPC nodes only.

GET /api/portfolio/{wallet_address}
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter
from web3 import Web3
from app.agents.crypto_agent import MORALIS_API_KEY, _scan_single_address  # shared scanner

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Concurrent-request dedupe + 30s TTL cache.
#
# Phase A (Playwright tester-ready validation) found that 5 concurrent
# requests for the same wallet all returned 500 — the wallet-assistant
# fans out to ~15 RPCs + Moralis + Binance for prices, and the parallel
# httpx clients + RPC connection storm overloaded somewhere. Sequential
# requests after that work fine.
#
# Fix: per-wallet asyncio.Lock so concurrent requests for the same wallet
# share the first request's work, plus a short TTL cache so repeat fetches
# within 30 s reuse the last successful payload. Cache keyed by the raw
# `{wallet_address}` path segment (already lower-cased by clients).
# ---------------------------------------------------------------------------

_PORTFOLIO_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PORTFOLIO_LOCKS: dict[str, asyncio.Lock] = {}
_PORTFOLIO_TTL = 30.0  # seconds


def _portfolio_lock(key: str) -> asyncio.Lock:
    lock = _PORTFOLIO_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PORTFOLIO_LOCKS[key] = lock
    return lock

# ---------------------------------------------------------------------------
# Chain config — mirrors crypto_agent._BALANCE_CHAINS with UI metadata
# ---------------------------------------------------------------------------

_CHAINS: list[dict[str, Any]] = [
    {
        "name": "Ethereum",
        "rpcs": ["https://eth.llamarpc.com", "https://ethereum.publicnode.com"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "Ξ", "grad": "linear-gradient(135deg,#627EEA,#3c5aa8)",
        "tokens": [
            {"symbol": "USDC", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
            {"symbol": "USDT", "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        ],
    },
    {
        "name": "BNB Chain",
        "rpcs": ["https://bsc-dataseed.binance.org", "https://bsc.publicnode.com"],
        "native": "BNB", "pricePair": "BNBUSDT",
        "icon": "⬡", "grad": "linear-gradient(135deg,#F0B90B,#E8832A)",
        "tokens": [
            {"symbol": "USDC", "address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
            {"symbol": "USDT", "address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
        ],
    },
    {
        "name": "Polygon",
        "rpcs": ["https://polygon-bor-rpc.publicnode.com", "https://1rpc.io/matic"],
        "native": "MATIC", "pricePair": "MATICUSDT",
        "icon": "⬡", "grad": "linear-gradient(135deg,#8247E5,#5a2fa0)",
        "tokens": [
            {"symbol": "USDC", "address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
            {"symbol": "USDT", "address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
        ],
    },
    {
        "name": "Arbitrum",
        "rpcs": ["https://arb1.arbitrum.io/rpc", "https://arbitrum.publicnode.com"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "A", "grad": "linear-gradient(135deg,#28A0F0,#1a6fa8)",
        "tokens": [
            {"symbol": "USDC", "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
            {"symbol": "USDT", "address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
        ],
    },
    {
        "name": "Optimism",
        "rpcs": ["https://mainnet.optimism.io", "https://optimism.publicnode.com"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "O", "grad": "linear-gradient(135deg,#FF0420,#990213)",
        "tokens": [
            {"symbol": "USDC", "address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
            {"symbol": "USDT", "address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "decimals": 6},
        ],
    },
    {
        "name": "Base",
        "rpcs": ["https://mainnet.base.org", "https://base.llamarpc.com"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "B", "grad": "linear-gradient(135deg,#0052FF,#0038b8)",
        "tokens": [
            {"symbol": "USDC", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
            {"symbol": "USDT", "address": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", "decimals": 6},
        ],
    },
    {
        "name": "Avalanche",
        "rpcs": ["https://api.avax.network/ext/bc/C/rpc", "https://avalanche-c-chain-rpc.publicnode.com"],
        "native": "AVAX", "pricePair": "AVAXUSDT",
        "icon": "▲", "grad": "linear-gradient(135deg,#E84142,#a02e2e)",
        "tokens": [
            {"symbol": "USDC", "address": "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", "decimals": 6},
            {"symbol": "USDT", "address": "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", "decimals": 6},
        ],
    },
    {
        "name": "zkSync Era",
        "rpcs": ["https://mainnet.era.zksync.io"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "Z", "grad": "linear-gradient(135deg,#8C8DFC,#4e4fa8)",
        "tokens": [
            {"symbol": "USDC", "address": "0x1d17CBcF0D6D143135aE902365D2E5e2A16538D4", "decimals": 6},
            {"symbol": "USDT", "address": "0x493257fD37EFE3a9E3a304E4C8c71706d1eE41f7", "decimals": 6},
        ],
    },
    {
        "name": "Linea",
        "rpcs": ["https://rpc.linea.build", "https://linea.publicnode.com"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "L", "grad": "linear-gradient(135deg,#61DFFF,#2a9ab5)",
        "tokens": [
            {"symbol": "USDC", "address": "0x176211869cA2b568f2A7D4EE941E073a821EE1ff", "decimals": 6},
            {"symbol": "USDT", "address": "0xA219439258ca9da29E9Cc4cE5596924745e12B93", "decimals": 6},
        ],
    },
    {
        "name": "Scroll",
        "rpcs": ["https://rpc.scroll.io", "https://scroll.publicnode.com"],
        "native": "ETH", "pricePair": "ETHUSDT",
        "icon": "S", "grad": "linear-gradient(135deg,#FFDBB0,#c47e30)",
        "tokens": [
            {"symbol": "USDC", "address": "0x06eFdBFf2a14a7c8E15944D1F4A48F9F95F663A4", "decimals": 6},
            {"symbol": "USDT", "address": "0xf55BEC9cafDbE8730f096Aa55dad6D22d44099Df", "decimals": 6},
        ],
    },
    {
        "name": "Mantle",
        "rpcs": ["https://rpc.mantle.xyz", "https://mantle.publicnode.com"],
        "native": "MNT", "pricePair": "MNTUSDT",
        "icon": "M", "grad": "linear-gradient(135deg,#2EBAC6,#1a7a82)",
        "tokens": [
            {"symbol": "USDC", "address": "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9", "decimals": 6},
            {"symbol": "USDT", "address": "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE", "decimals": 6},
        ],
    },
    {
        "name": "Fantom",
        "rpcs": ["https://rpcapi.fantom.network", "https://fantom-mainnet.public.blastapi.io"],
        "native": "FTM", "pricePair": "FTMUSDT",
        "icon": "F", "grad": "linear-gradient(135deg,#1969FF,#0f40a8)",
        "tokens": [
            {"symbol": "USDC", "address": "0x04068DA6C83AFCFA0e13ba15A6696662335D5B75", "decimals": 6},
            {"symbol": "USDT", "address": "0x049d68029688eAbF473097a2fC38ef61633A3C7A", "decimals": 6},
        ],
    },
    {
        "name": "Gnosis",
        "rpcs": ["https://rpc.gnosischain.com", "https://gnosis.publicnode.com"],
        "native": "xDAI", "pricePair": "DAIUSDT",
        "icon": "G", "grad": "linear-gradient(135deg,#04795B,#024d3b)",
        "tokens": [
            {"symbol": "USDC", "address": "0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83", "decimals": 6},
            {"symbol": "USDT", "address": "0x4ECaBa5870353805a9F068101A40E0f32ed605C6", "decimals": 6},
        ],
    },
    {
        "name": "Celo",
        "rpcs": ["https://forno.celo.org", "https://celo.publicnode.com"],
        "native": "CELO", "pricePair": "CELOUSDT",
        "icon": "C", "grad": "linear-gradient(135deg,#FCFF52,#a8aa2e)",
        "tokens": [
            {"symbol": "USDC", "address": "0xcebA9300f2b948710d2653dD7B07f33A8B32118C", "decimals": 6},
            {"symbol": "USDT", "address": "0x48065fbBE25f71C9282ddf5e1cD6D6A887483D5e", "decimals": 6},
        ],
    },
    {
        "name": "Cronos",
        "rpcs": ["https://evm.cronos.org", "https://cronos.publicnode.com"],
        "native": "CRO", "pricePair": "CROUSDT",
        "icon": "C", "grad": "linear-gradient(135deg,#002D74,#001540)",
        "tokens": [
            {"symbol": "USDC", "address": "0xc21223249CA28397B4B6541dfFaEcC539BfF0c59", "decimals": 6},
            {"symbol": "USDT", "address": "0x66e428c3f67a68878562e79A0234c1F83c208770", "decimals": 6},
        ],
    },
]

_STABLECOIN_ICON = "₮"
_USDC_GRAD = "linear-gradient(135deg,#2775CA,#1a4e8f)"
_USDT_GRAD = "linear-gradient(135deg,#26A17B,#1A7A5E)"

_TOKEN_META: dict[str, dict[str, str]] = {
    "ETH":   {"icon": "Ξ", "grad": "linear-gradient(135deg,#627EEA,#3c5aa8)", "name": "Ethereum"},
    "WETH":  {"icon": "Ξ", "grad": "linear-gradient(135deg,#627EEA,#3c5aa8)", "name": "Wrapped Ether"},
    "BNB":   {"icon": "⬡", "grad": "linear-gradient(135deg,#F0B90B,#E8832A)", "name": "BNB"},
    "SOL":   {"icon": "◎", "grad": "linear-gradient(135deg,#9945FF,#14F195)", "name": "Solana"},
    "MATIC": {"icon": "⬡", "grad": "linear-gradient(135deg,#8247E5,#5a2fa0)", "name": "Polygon"},
    "AVAX":  {"icon": "▲", "grad": "linear-gradient(135deg,#E84142,#a02e2e)", "name": "Avalanche"},
    "USDC":  {"icon": "$",  "grad": _USDC_GRAD, "name": "USD Coin"},
    "USDT":  {"icon": "₮",  "grad": _USDT_GRAD, "name": "Tether USD"},
    "DAI":   {"icon": "◈",  "grad": "linear-gradient(135deg,#F5AC37,#c07800)", "name": "Dai"},
    "WBTC":  {"icon": "₿",  "grad": "linear-gradient(135deg,#F7931A,#c06b00)", "name": "Wrapped BTC"},
    "CAKE":  {"icon": "🥞", "grad": "linear-gradient(135deg,#1FC7D4,#1493a8)", "name": "PancakeSwap"},
    "JUP":   {"icon": "🪐", "grad": "linear-gradient(135deg,#C7F284,#7ab830)", "name": "Jupiter"},
    "BONK":  {"icon": "🐶", "grad": "linear-gradient(135deg,#FF6B35,#c04010)", "name": "Bonk"},
    "RAY":   {"icon": "◉",  "grad": "linear-gradient(135deg,#4ABB96,#2a7a60)", "name": "Raydium"},
    "PYTH":  {"icon": "🔮", "grad": "linear-gradient(135deg,#E6DAFE,#9945FF)", "name": "Pyth Network"},
}
_DEFAULT_META: dict[str, str] = {"icon": "🪙", "grad": "linear-gradient(135deg,#555,#333)", "name": "Token"}
_STABLECOINS = {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD", "PYUSD"}

# CoinGecko IDs for tracked assets
_COINGECKO_IDS = {
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "MATICUSDT": "matic-network",
    "AVAXUSDT": "avalanche-2",
    "FTMUSDT": "fantom",
    "SOLUSDT": "solana",
    "CELOUSDT": "celo",
    "MNTUSDT": "mantle",
    "CROUSDT": "crypto-com-chain",
}

# Solana
_SOL_RPCS = ["https://api.mainnet-beta.solana.com", "https://solana-rpc.publicnode.com"]
_SOL_TOKENS = [
    ("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
    ("USDT", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_prices(client: httpx.AsyncClient) -> dict[str, float]:
    prices: dict[str, float] = {"DAIUSDT": 1.0}

    # Primary: CoinGecko (works in restricted Binance regions)
    try:
        ids = ",".join(_COINGECKO_IDS.values())
        cg = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=8,
        )
        if cg.status_code == 200:
            data = cg.json()
            for pair, cg_id in _COINGECKO_IDS.items():
                if cg_id in data and isinstance(data[cg_id], dict) and "usd" in data[cg_id]:
                    prices[pair] = data[cg_id]["usd"]
    except Exception as exc:
        logger.warning("CoinGecko price fetch failed: %s", exc)

    # Fallback: try Binance for any missing prices
    missing = [pair for pair in _COINGECKO_IDS if pair not in prices]
    if missing:
        tasks = [
            client.get("https://api.binance.com/api/v3/ticker/price",
                       params={"symbol": pair}, timeout=4)
            for pair in missing
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for pair, res in zip(missing, results):
            status_code = getattr(res, "status_code", None)
            if status_code == 200:
                json_loader = getattr(res, "json", None)
                if callable(json_loader):
                    prices[pair] = float(json_loader().get("price", 0))

    return prices


async def _rpc_with_fallback(client: httpx.AsyncClient, rpcs: list[str], payload: dict) -> dict:
    for rpc in rpcs:
        try:
            resp = await client.post(rpc, json=payload, timeout=8)
            data = resp.json()
            if "result" in data:
                return data
        except Exception:
            continue
    return {}


async def _scan_chain(
    client: httpx.AsyncClient,
    chain: dict[str, Any],
    address: str,
    padded: str,
    prices: dict[str, float],
) -> list[dict[str, Any]]:
    balanceof_data = f"0x70a08231{padded}"
    rpcs = chain["rpcs"]

    # Fire native + all token calls concurrently
    tasks = [
        _rpc_with_fallback(client, rpcs, {
            "jsonrpc": "2.0", "method": "eth_getBalance",
            "params": [address, "latest"], "id": 1,
        })
    ] + [
        _rpc_with_fallback(client, rpcs, {
            "jsonrpc": "2.0", "method": "eth_call",
            "params": [{"to": tok["address"], "data": balanceof_data}, "latest"], "id": i + 2,
        })
        for i, tok in enumerate(chain["tokens"])
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    native_data, *token_datas = results

    tokens: list[dict[str, Any]] = []
    price = prices.get(chain["pricePair"], 0.0)

    # Native
    if isinstance(native_data, dict):
        hex_val = native_data.get("result", "0x0") or "0x0"
        bal = int(hex_val, 16) / 1e18 if hex_val not in ("0x", "0x0") else 0.0
        if bal > 0.000001:
            tokens.append({
                "symbol":     chain["native"],
                "name":       chain["native"],
                "icon":       chain["icon"],
                "grad":       chain["grad"],
                "balance":    f"{bal:.6f}",
                "balanceRaw": bal,
                "price":      price,
                "valueUsd":   bal * price,
                "chainName":  chain["name"],
            })

    # ERC-20 tokens (USDC, USDT)
    for tok, data in zip(chain["tokens"], token_datas):
        if not isinstance(data, dict):
            continue
        hex_val = data.get("result", "0x0") or "0x0"
        bal = (
            int(hex_val, 16) / 10 ** tok["decimals"]
            if hex_val not in ("0x", "0x0", "0x" + "0" * 64) else 0.0
        )
        if bal > 0.01:
            is_usdc = tok["symbol"] == "USDC"
            tokens.append({
                "symbol":     tok["symbol"],
                "name":       "USD Coin" if is_usdc else "Tether USD",
                "icon":       "$",
                "grad":       _USDC_GRAD if is_usdc else _USDT_GRAD,
                "balance":    f"{bal:.2f}",
                "balanceRaw": bal,
                "price":      1.0,
                "valueUsd":   bal,
                "chainName":  chain["name"],
            })

    return tokens


# ---------------------------------------------------------------------------
# Solana scanner
# ---------------------------------------------------------------------------

async def _scan_solana(client: httpx.AsyncClient, address: str, prices: dict[str, float]) -> list[dict[str, Any]]:
    sol_price = prices.get("SOLUSDT", 0.0)
    tokens: list[dict[str, Any]] = []

    # Native SOL balance
    native_data = await _rpc_with_fallback(client, _SOL_RPCS, {
        "jsonrpc": "2.0", "method": "getBalance", "params": [address], "id": 1,
    })
    result = native_data.get("result", {})
    lamports = result.get("value", 0) if isinstance(result, dict) else (result or 0)
    bal = int(lamports) / 1e9
    if bal > 0.000001:
        tokens.append({
            "symbol": "SOL", "name": "Solana",
            "icon": "◎", "grad": "linear-gradient(135deg,#9945FF,#14F195)",
            "balance": f"{bal:.6f}", "balanceRaw": bal,
            "price": sol_price, "valueUsd": bal * sol_price,
            "chainName": "Solana",
        })

    # All SPL tokens via Moralis Solana Gateway (returns human-readable amounts, no decimals math needed)
    if MORALIS_API_KEY:
        try:
            spl_resp = await client.get(
                f"https://solana-gateway.moralis.io/account/mainnet/{address}/tokens",
                headers={"accept": "application/json", "X-API-Key": MORALIS_API_KEY},
                timeout=8,
            )
            if spl_resp.status_code == 200:
                for tok in spl_resp.json():
                    symbol = tok.get("symbol", "")
                    if not symbol or tok.get("possible_spam", False):
                        continue
                    ui_bal = float(tok.get("amount") or 0)  # already human-readable
                    if ui_bal <= 0.01:
                        continue
                    meta = _TOKEN_META.get(symbol, _DEFAULT_META)
                    is_stable = symbol in _STABLECOINS
                    token_price = 1.0 if is_stable else 0.0
                    tokens.append({
                        "symbol": symbol,
                        "name": tok.get("name") or meta["name"],
                        "icon": meta["icon"],
                        "grad": meta["grad"],
                        "balance": f"{ui_bal:.6f}", "balanceRaw": ui_bal,
                        "price": token_price, "valueUsd": ui_bal * token_price,
                        "chainName": "Solana",
                    })
            else:
                logger.warning("Moralis Solana SPL: HTTP %s", spl_resp.status_code)
        except Exception as exc:
            logger.warning("Moralis Solana SPL failed: %s", exc)

    return tokens


# ---------------------------------------------------------------------------
# Format converter: crypto_agent chain dicts → portfolio UI token list
# ---------------------------------------------------------------------------

def _to_portfolio_format(chain_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert _scan_single_address output into the flat token list the Portfolio UI expects."""
    result: list[dict[str, Any]] = []
    for chain in chain_dicts:
        chain_name = chain["chain"]
        nat_sym = chain["native_symbol"]
        nat_bal = chain["native_balance"]
        nat_usd = chain.get("native_usd", 0.0)
        if nat_bal > 0:
            meta = _TOKEN_META.get(nat_sym, _DEFAULT_META)
            nat_price = (nat_usd / nat_bal) if nat_bal > 0 else 0.0
            result.append({
                "symbol": nat_sym, "name": meta["name"],
                "icon": meta["icon"], "grad": meta["grad"],
                "balance": f"{nat_bal:.6f}", "balanceRaw": nat_bal,
                "price": round(nat_price, 2), "valueUsd": nat_usd,
                "chainName": chain_name,
            })
        for tok in chain.get("tokens", []):
            sym = tok["symbol"]
            bal = tok["balance"]
            usd = tok.get("usd_value", 0.0)
            meta = _TOKEN_META.get(sym, _DEFAULT_META)
            tok_price = (usd / bal) if bal > 0 and usd > 0 else 0.0
            result.append({
                "symbol": sym, "name": meta["name"],
                "icon": meta["icon"], "grad": meta["grad"],
                "balance": f"{bal:.6f}", "balanceRaw": bal,
                "price": round(tok_price, 4), "valueUsd": usd,
                "chainName": chain_name,
            })
    return result


# ---------------------------------------------------------------------------
# Open positions — liquid-staking (LST) holdings with live APY + earnings.
#
# SOL LSTs (jitoSOL/mSOL) already arrive via the Moralis SPL scan (priced $0 in
# the token list). EVM LSTs (stETH/rETH/...) are NOT in the USDC/USDT scan, so we
# scan their balanceOf here. Each position gets a real price, the live APY, a
# projected yearly yield, and a realized P&L computed from the user's recorded
# stake/unstake history (cost basis) when available.
# ---------------------------------------------------------------------------

_LST_CHAIN_RPCS: dict[int, list[str]] = {
    1:   ["https://rpc.ankr.com/eth", "https://eth.drpc.org", "https://1rpc.io/eth", "https://eth.llamarpc.com"],
    56:  ["https://bsc-dataseed.binance.org", "https://bsc-dataseed1.defibit.io", "https://bsc.drpc.org"],
    137: ["https://polygon-rpc.com", "https://polygon.drpc.org", "https://1rpc.io/matic"],
}

# CoinGecko ids for LST USD pricing. Missing/failed ids fall back to the
# underlying asset's price (stETH≈ETH; jitoSOL slightly under) so values stay sane.
_LST_COINGECKO: dict[str, str] = {
    "jitosol": "jito-staked-sol",
    "msol":    "msol",
    "steth":   "staked-ether",
    "reth":    "rocket-pool-eth",
    "cbeth":   "coinbase-wrapped-staked-eth",
    "sfrxeth": "staked-frax-ether",
    "meth":    "mantle-staked-ether",
    "stkbnb":  "pstake-staked-bnb",
    "ankrbnb": "ankr-staked-bnb",
    "stmatic": "lido-staked-matic",
}

_UNDERLYING_PAIR = {"SOL": "SOLUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT", "MATIC": "MATICUSDT"}


async def _fetch_lst_usd_prices(client: httpx.AsyncClient, symbols_lower: set[str]) -> dict[str, float]:
    """Batch CoinGecko price for the LST symbols actually held. Returns {sym_lower: usd}."""
    ids = {s: _LST_COINGECKO[s] for s in symbols_lower if s in _LST_COINGECKO}
    if not ids:
        return {}
    out: dict[str, float] = {}
    try:
        cg = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ",".join(sorted(set(ids.values()))), "vs_currencies": "usd"},
            timeout=8,
        )
        if cg.status_code == 200:
            data = cg.json()
            for sym, cg_id in ids.items():
                node = data.get(cg_id)
                if isinstance(node, dict) and "usd" in node:
                    out[sym] = float(node["usd"])
    except Exception as exc:
        logger.warning("LST price fetch failed: %s", exc)
    return out


async def _scan_evm_lst_balances(
    client: httpx.AsyncClient, evm_addresses: list[str], lst_tokens: dict[str, dict],
) -> list[dict[str, Any]]:
    """balanceOf each EVM LST contract for each EVM address. Returns raw holdings."""
    held: list[dict[str, Any]] = []
    evm_lsts = [v for v in lst_tokens.values() if v["chain_id"] in _LST_CHAIN_RPCS]
    for addr in evm_addresses:
        if not (addr.startswith("0x") and len(addr) == 42):
            continue
        padded = addr[2:].lower().rjust(64, "0")
        calldata = f"0x70a08231{padded}"
        tasks = [
            _rpc_with_fallback(client, _LST_CHAIN_RPCS[v["chain_id"]], {
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": v["address"], "data": calldata}, "latest"], "id": 1,
            })
            for v in evm_lsts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for v, data in zip(evm_lsts, results):
            if not isinstance(data, dict):
                continue
            hex_val = data.get("result", "0x0") or "0x0"
            if hex_val in ("0x", "0x0", "0x" + "0" * 64):
                continue
            try:
                bal = int(hex_val, 16) / 10 ** v["decimals"]
            except (ValueError, TypeError):
                continue
            if bal > 1e-6:
                held.append({"sym": v["symbol"], "balance": bal, "info": v})
    return held


async def _scan_sol_lst_balances(
    client: httpx.AsyncClient, sol_addresses: list[str], lst_tokens: dict[str, dict],
) -> list[dict[str, Any]]:
    """getTokenAccountsByOwner for each SOL LST mint (jitoSOL/mSOL) per SOL address."""
    held: list[dict[str, Any]] = []
    sol_lsts = [v for v in lst_tokens.values() if v["chain_id"] == 101]
    for addr in sol_addresses:
        for v in sol_lsts:
            data = await _rpc_with_fallback(client, _SOL_RPCS, {
                "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
                "params": [addr, {"mint": v["address"]}, {"encoding": "jsonParsed"}],
            })
            total = 0.0
            for item in (((data.get("result") or {}).get("value")) or []):
                amt = (((((item.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}).get("tokenAmount") or {})
                total += float(amt.get("uiAmount") or 0)
            if total > 1e-6:
                held.append({"sym": v["symbol"], "balance": total, "info": v})
    return held


def _staking_history(addresses: list[str]) -> dict[str, dict[str, float]]:
    """Per-LST-symbol cost basis from recorded stake/unstake turns:
    {lst_lower: {"staked_underlying": x, "unstaked_underlying": y}}.
    Best-effort — DB issues never break the portfolio."""
    out: dict[str, dict[str, float]] = {}
    try:
        from app.db.database import SessionLocal
        from app.db.models import Transaction
        db = SessionLocal()
        try:
            rows = (
                db.query(Transaction)
                .filter(Transaction.wallet.in_(addresses), Transaction.kind.in_(["stake", "unstake"]))
                .all()
            )
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("staking history query failed: %s", exc)
        return out

    def _f(v: Any) -> float:
        try:
            return float(str(v))
        except (TypeError, ValueError):
            return 0.0

    def _init() -> dict[str, float]:
        return {"staked_underlying": 0.0, "staked_lst": 0.0, "unstaked_underlying": 0.0}

    for r in rows:
        if r.kind == "stake":
            lst = (r.to_token or "").strip().lower()      # e.g. "jitoSOL"
            if not lst:
                continue
            out.setdefault(lst, _init())
            out[lst]["staked_underlying"] += _f(r.from_amount)   # underlying paid (SOL/ETH)
            out[lst]["staked_lst"] += _f(r.to_amount)            # LST received (jitoSOL/...)
        elif r.kind == "unstake":
            lst = (r.from_token or "").strip().lower()    # unstake: LST -> underlying
            if not lst:
                continue
            out.setdefault(lst, _init())
            out[lst]["unstaked_underlying"] += _f(r.to_amount)   # underlying out (SOL/ETH)
    return out


async def _build_positions(
    addresses: list[str],
    prices: dict[str, float],
    client: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Liquid-staking positions with value, live APY, projected + realized earnings."""
    try:
        from app.agents.crypto_agent import _get_lst_tokens, _get_lst_apy
    except Exception as exc:  # noqa: BLE001
        logger.warning("positions: cannot import LST helpers: %s", exc)
        return []

    lst_tokens = _get_lst_tokens()

    # Dedicated LST balance scans (independent of the USDC/USDT token list).
    holdings: list[dict[str, Any]] = []
    sol_addresses = [a for a in addresses if not a.startswith("0x") and 32 <= len(a) <= 44]
    if sol_addresses:
        holdings.extend(await _scan_sol_lst_balances(client, sol_addresses, lst_tokens))
    evm_addresses = [a for a in addresses if a.startswith("0x") and len(a) == 42]
    if evm_addresses:
        holdings.extend(await _scan_evm_lst_balances(client, evm_addresses, lst_tokens))

    if not holdings:
        return []

    # 3) Price the held LSTs (CoinGecko; fall back to underlying price).
    lst_prices = await _fetch_lst_usd_prices(client, {h["sym"].lower() for h in holdings})

    # 4) Cost basis from recorded stake/unstake history.
    history = _staking_history(addresses)

    positions: list[dict[str, Any]] = []
    for h in holdings:
        info = h["info"]
        sym = info["symbol"]
        sym_l = sym.lower()
        underlying = info["underlying"]
        bal = float(h["balance"] or 0)
        if bal <= 0:
            continue
        und_usd = prices.get(_UNDERLYING_PAIR.get(underlying, ""), 0.0)
        price_usd = lst_prices.get(sym_l) or und_usd  # fallback: ≈ underlying price
        value_usd = bal * price_usd

        apy = None
        if info.get("apy_key"):
            try:
                apy = _get_lst_apy(info["apy_key"])
            except Exception:
                apy = None

        projected_yearly_usd = round(value_usd * apy / 100.0, 2) if apy else None

        # Earned (realized yield) on the CURRENTLY held LST: how much its value has
        # grown above the rate you paid to enter. entry_rate = underlying paid per LST
        # (from your stake history); current_rate = underlying per LST now. Multiplying
        # by the held balance isolates the appreciation of what you still hold — robust
        # to unstake churn (the old net-staked subtraction went negative once you'd
        # unstaked more than you currently hold, leaving Earned blank).
        realized_underlying = None
        realized_usd = None
        hist = history.get(sym_l)
        if hist and und_usd > 0 and price_usd > 0 and hist.get("staked_lst", 0.0) > 1e-9:
            entry_rate = hist["staked_underlying"] / hist["staked_lst"]   # underlying per LST at entry
            current_rate = price_usd / und_usd                           # underlying per LST now
            realized_underlying = round(bal * (current_rate - entry_rate), 6)
            realized_usd = round(realized_underlying * und_usd, 2)
            # Clamp sub-cent pricing noise to a clean zero (a freshly-opened position
            # is ~break-even; show $0.00, not a confusing "-$0.00").
            if abs(realized_usd) < 0.005:
                realized_usd = 0.0
            if abs(realized_underlying) < 1e-5:
                realized_underlying = 0.0

        positions.append({
            "symbol": sym,
            "protocol": info["protocol"].title(),
            "chainName": {101: "Solana", 1: "Ethereum", 56: "BNB Chain", 137: "Polygon"}.get(info["chain_id"], "—"),
            "chainId": info["chain_id"],
            "underlying": underlying,
            "kind": "stake",
            "balance": bal,
            "balanceDisplay": f"{bal:.6f}",
            "priceUsd": round(price_usd, 4),
            "valueUsd": round(value_usd, 2),
            "underlyingPriceUsd": round(und_usd, 2),
            "apy": round(apy, 2) if apy is not None else None,
            "projectedYearlyUsd": projected_yearly_usd,
            "realizedUsd": realized_usd,
            "realizedUnderlying": realized_underlying,
        })

    positions.sort(key=lambda p: p["valueUsd"], reverse=True)
    return positions


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

async def _build_portfolio(wallet_address: str) -> dict[str, Any]:
    """Inner builder — the actual fan-out + format. Always returns a payload,
    never raises. Errors per-address are logged and skipped."""
    addresses = [part.strip() for part in wallet_address.split(",") if part.strip()]
    if not addresses:
        addresses = [wallet_address]

    chain_dicts: list[dict[str, Any]] = []
    bnb_price = 0.0
    sol_price = 0.0
    positions: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient() as client:
            prices = await _fetch_prices(client)
            bnb_price = prices.get("BNBUSDT", 0.0)
            sol_price = prices.get("SOLUSDT", 0.0)
            # Run the per-wallet token scans (all wallets in parallel) CONCURRENTLY
            # with the positions build — so liquid-staking positions don't wait behind
            # the slow 15-chain token scan. Total time ≈ max(), not sum().
            scan_results, positions_res = await asyncio.gather(
                asyncio.gather(
                    *[asyncio.to_thread(_scan_single_address, a, "") for a in addresses],
                    return_exceptions=True,
                ),
                _build_positions(addresses, prices, client),
                return_exceptions=True,
            )
            if isinstance(scan_results, list):
                for res in scan_results:
                    if isinstance(res, list):
                        chain_dicts.extend(res)
                    else:
                        logger.error("Portfolio scan error: %s", res)
            positions = positions_res if isinstance(positions_res, list) else []
    except Exception as exc:
        logger.warning("Portfolio build failed: %s", exc)

    tokens = _to_portfolio_format(chain_dicts)
    tokens.sort(key=lambda t: t["valueUsd"], reverse=True)
    total_usd = sum(t.get("valueUsd", 0.0) for t in tokens)

    return {
        "totalUsd": round(total_usd, 2),
        "bnbPrice": bnb_price,
        "solPrice": sol_price,
        "tokens": tokens,
        "positions": positions,
    }


@router.get("/portfolio/{wallet_address:path}")
async def get_portfolio(wallet_address: str) -> dict[str, Any]:
    """Cached + concurrency-deduped wrapper.

    Phase A revealed 5 concurrent requests for the same wallet ALL returned
    500 (RPC/Moralis/Binance fan-out overload). We:
      1. Serve from 30 s in-memory cache on a hit (no fan-out at all)
      2. On a miss, take an asyncio.Lock keyed by wallet_address so concurrent
         callers wait for the first one to populate the cache rather than
         all firing the fan-out in parallel
      3. Wrap the inner builder so a hard exception never returns 5xx —
         returns a zero-balance shape instead
    """
    cache_key = wallet_address.strip().lower()
    now = time.monotonic()
    cached = _PORTFOLIO_CACHE.get(cache_key)
    if cached and now - cached[0] < _PORTFOLIO_TTL:
        return cached[1]

    async with _portfolio_lock(cache_key):
        # Double-checked locking — another caller may have populated while
        # we waited.
        cached = _PORTFOLIO_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < _PORTFOLIO_TTL:
            return cached[1]
        try:
            payload = await _build_portfolio(wallet_address)
            # Only cache a result that actually found tokens. An empty result is
            # almost always a transient scan failure (RPC/Moralis throttle) — caching
            # it would serve "$0 / no tokens" for the next 30 s. On an empty result,
            # prefer the last good cached payload so the user keeps seeing real data.
            if payload.get("tokens"):
                _PORTFOLIO_CACHE[cache_key] = (time.monotonic(), payload)
                return payload
            if cached:
                return cached[1]
            return payload
        except Exception as exc:  # noqa: BLE001
            logger.error("Portfolio builder hard failure for %s: %s", cache_key, exc)
            # Serve a stale cache if any, else a zero-balance placeholder.
            if cached:
                return cached[1]
            return {
                "totalUsd": 0.0,
                "bnbPrice": 0.0,
                "solPrice": 0.0,
                "tokens": [],
                "partial": True,
                "error": "scan_failed",
            }
