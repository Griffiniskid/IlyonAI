"""
Crypto agent for the BNB Chain ecosystem.

Tools
-----
get_native_balance — native BNB balance on BNB Smart Chain via public RPC
simulate_swap      — token swap estimate via live price data
get_token_price    — real-time USD price via Binance REST, CoinGecko fallback
build_swap_tx      — full swap transaction via Enso (EVM) or Jupiter (Solana)
                     with platform fee; returns ready-to-sign JSON

Agent type: ZERO_SHOT_REACT_DESCRIPTION with ConversationBufferMemory
"""

import base64
import concurrent.futures
from difflib import get_close_matches
import json
import logging
import os
import re
import time
from typing import Any, Final, Optional

import httpx
import requests as _requests
from langchain.agents import AgentExecutor, AgentType, initialize_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from web3 import Web3

from app.core.config import settings

logger = logging.getLogger(__name__)

MORALIS_API_KEY: str = os.environ.get("MORALIS_API_KEY", "")

# Moralis chain IDs for ERC-20 token scanning (chains supported by Moralis)
_MORALIS_CHAINS: Final[dict[str, str]] = {
    "Ethereum": "eth",
    "BNB Chain": "bsc",
    "Polygon": "polygon",
    "Avalanche": "avalanche",
    "Arbitrum": "arbitrum",
    "Optimism": "optimism",
    "Base": "base",
}

# ---------------------------------------------------------------------------
# Chain constants
# ---------------------------------------------------------------------------

# Fallback RPC URLs when not present in settings.rpc_urls
_RPC_FALLBACK: Final[dict[int, str]] = {
    1:   "https://rpc.ankr.com/eth",
    56:  "https://rpc.ankr.com/bsc",
    137: "https://rpc.ankr.com/polygon",
}

# (1inch constants removed — using Enso for EVM swaps)

# ---------------------------------------------------------------------------
# Chain metadata — name, native symbol, native decimals
# ---------------------------------------------------------------------------

_CHAIN_META: Final[dict[int, dict[str, str]]] = {
    1:      {"name": "Ethereum",          "native": "ETH",  "native_name": "Ether"},
    56:     {"name": "BNB Smart Chain",   "native": "BNB",  "native_name": "BNB"},
    137:    {"name": "Polygon",           "native": "MATIC","native_name": "MATIC"},
    8453:   {"name": "Base",              "native": "ETH",  "native_name": "Ether"},
    10:     {"name": "Optimism",          "native": "ETH",  "native_name": "Ether"},
    43114:  {"name": "Avalanche",         "native": "AVAX", "native_name": "AVAX"},
    42161:  {"name": "Arbitrum One",      "native": "ETH",  "native_name": "Ether"},
    324:    {"name": "zkSync Era",        "native": "ETH",  "native_name": "Ether"},
    59144:  {"name": "Linea",             "native": "ETH",  "native_name": "Ether"},
    534352: {"name": "Scroll",            "native": "ETH",  "native_name": "Ether"},
    5000:   {"name": "Mantle",            "native": "MNT",  "native_name": "MNT"},
    250:    {"name": "Fantom",            "native": "FTM",  "native_name": "FTM"},
    100:    {"name": "Gnosis",            "native": "xDAI", "native_name": "xDAI"},
    42220:  {"name": "Celo",              "native": "CELO", "native_name": "CELO"},
    25:     {"name": "Cronos",            "native": "CRO",  "native_name": "CRO"},
}

# Maps a unique native symbol → canonical chain_id (for auto-detecting chain from token)
_NATIVE_SYMBOL_TO_CHAIN: Final[dict[str, int]] = {
    "bnb": 56, "matic": 137, "avax": 43114, "mnt": 5000,
    "ftm": 250, "xdai": 100, "celo": 42220, "cro": 25,
}

def _chain_name(chain_id: int) -> str:
    return _CHAIN_META.get(chain_id, {}).get("name", f"Chain {chain_id}")

def _native_symbol(chain_id: int) -> str:
    return _CHAIN_META.get(chain_id, {}).get("native", "ETH")

# ---------------------------------------------------------------------------
# Multi-chain token registry — indexed by chain_id
# Allows build_transfer_tx to resolve addresses without any external calls.
# ---------------------------------------------------------------------------

# Ethereum Mainnet — chain 1
_TOKENS_ETH: Final[dict[str, dict[str, Any]]] = {
    "usdt": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
    "usdc": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    "dai":  {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
    "wbtc": {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
    "weth": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
    "link": {"address": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "decimals": 18},
    "uni":  {"address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "decimals": 18},
    "aave": {"address": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9", "decimals": 18},
    "shib": {"address": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE", "decimals": 18},
}

# BNB Smart Chain (BSC) — chain 56
_TOKENS_BSC: Final[dict[str, dict[str, Any]]] = {
    "usdt":  {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
    "usdc":  {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
    "busd":  {"address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "decimals": 18},
    "dai":   {"address": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "decimals": 18},
    "tusd":  {"address": "0x14016E85a25aeb13065688cAFB43044C2ef86784", "decimals": 18},
    "cake":  {"address": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "decimals": 18},
    "wbnb":  {"address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "decimals": 18},
    "xvs":   {"address": "0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63", "decimals": 18},
    "bake":  {"address": "0xE02dF9e3e622DeBdD69fb838bB799E3F168902c5", "decimals": 18},
    "eth":   {"address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "decimals": 18},
    "btcb":  {"address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "decimals": 18},
    "wbtc":  {"address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "decimals": 18},
    "ada":   {"address": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47", "decimals": 18},
    "doge":  {"address": "0xbA2aE424d960c26247Dd6c32edC70B295c744C43", "decimals": 8},
    "dot":   {"address": "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402", "decimals": 18},
    "matic": {"address": "0xCC42724C6683B7E57334c4E856f4c9965ED682bD", "decimals": 18},
    "link":  {"address": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD", "decimals": 18},
    "uni":   {"address": "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1", "decimals": 18},
    "aave":  {"address": "0xfb6115445Bff7b52FeB98650C87f44907E58f802", "decimals": 18},
    "trx":   {"address": "0x85EAC5Ac2F758618dFa09bDbe0cf174e7d574D5B", "decimals": 6},
    "xrp":   {"address": "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE", "decimals": 18},
    "ltc":   {"address": "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94", "decimals": 18},
    "fdusd": {"address": "0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409", "decimals": 18},
}

# Polygon — chain 137
_TOKENS_POLYGON: Final[dict[str, dict[str, Any]]] = {
    "usdc":  {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
    "usdt":  {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
    "dai":   {"address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", "decimals": 18},
    "wbtc":  {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "decimals": 8},
    "weth":  {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18},
    "link":  {"address": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39", "decimals": 18},
    "aave":  {"address": "0xD6DF932A45C0f255f85145f286eA0b292B21C90B", "decimals": 18},
    "wmatic":{"address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
}

# Base — chain 8453
_TOKENS_BASE: Final[dict[str, dict[str, Any]]] = {
    "usdc":  {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6},
    "dai":   {"address": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "decimals": 18},
    "weth":  {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
}

# Optimism — chain 10
_TOKENS_OP: Final[dict[str, dict[str, Any]]] = {
    "usdc":  {"address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
    "usdt":  {"address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "decimals": 6},
    "dai":   {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
    "weth":  {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
    "op":    {"address": "0x4200000000000000000000000000000000000042", "decimals": 18},
}

# Arbitrum One — chain 42161
_TOKENS_ARB: Final[dict[str, dict[str, Any]]] = {
    "usdc":  {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
    "usdt":  {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
    "dai":   {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
    "wbtc":  {"address": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "decimals": 8},
    "weth":  {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
    "arb":   {"address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "decimals": 18},
}

# Chain-indexed registry
TOKENS_BY_CHAIN: Final[dict[int, dict[str, dict[str, Any]]]] = {
    1:     _TOKENS_ETH,
    56:    _TOKENS_BSC,
    137:   _TOKENS_POLYGON,
    8453:  _TOKENS_BASE,
    10:    _TOKENS_OP,
    42161: _TOKENS_ARB,
}

# Backwards-compatible alias for code that doesn't pass chain_id
POPULAR_TOKENS: Final[dict[str, dict[str, Any]]] = _TOKENS_BSC

# ---------------------------------------------------------------------------
# Per-wallet discovered token cache
# When Moralis finds tokens, we save their addresses so RPC fallback can scan them later
# Key: "wallet_address:chain_name" → dict of {symbol: {address, decimals}}
# ---------------------------------------------------------------------------
_discovered_tokens: dict[str, dict[str, dict[str, Any]]] = {}


def _save_discovered_tokens(wallet: str, chain_name: str, tokens: list[dict]) -> None:
    """Cache token addresses discovered for a wallet/chain for later wallet-first resolution."""
    key = f"{wallet.lower()}:{chain_name}"
    if key not in _discovered_tokens:
        _discovered_tokens[key] = {}
    for tok in tokens:
        sym = tok.get("symbol", "").lower()
        addr = tok.get("address") or tok.get("token_address", "")
        if sym and addr:
            _discovered_tokens[key][sym] = {
                "address": addr.lower(),
                "decimals": int(tok.get("decimals", 18) or 18),
            }


def _get_discovered_tokens(wallet: str, chain_name: str) -> dict[str, dict[str, Any]]:
    """Get previously discovered tokens for RPC scanning."""
    return _discovered_tokens.get(f"{wallet.lower()}:{chain_name}", {})


# ---------------------------------------------------------------------------
# Session memory store
# NOTE: process-scoped dict — replace with Redis + TTL in production
# ---------------------------------------------------------------------------

_session_memory: dict[str, ConversationBufferWindowMemory] = {}


def _get_or_create_memory(session_id: str) -> ConversationBufferWindowMemory:
    if session_id not in _session_memory:
        # k=6: keeps last 6 exchanges (12 messages) — enough context, minimal tokens
        _session_memory[session_id] = ConversationBufferWindowMemory(
            memory_key="chat_history",
            return_messages=True,
            k=6,
        )
    return _session_memory[session_id]


def clear_session_memory(session_id: str) -> None:
    """Explicitly drop a session's memory (e.g. on logout)."""
    _session_memory.pop(session_id, None)


# ---------------------------------------------------------------------------
# Step 1 — LLM
# Priority: OpenRouter → Groq → OpenAI
# ---------------------------------------------------------------------------

_OPENROUTER_MODELS = [
    "openai/gpt-4o-mini",
    "anthropic/claude-3-5-haiku",
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]


def _build_llm(openrouter_model: Optional[str] = None):
    # "__openai__" sentinel: use OpenAI API directly
    if openrouter_model == "__openai__":
        logger.info("Using OpenAI LLM (gpt-4.1-mini)")
        openai_key = settings.api_keys.get("openai", "")
        return ChatOpenAI(
            model="gpt-4.1-mini",
            temperature=0.1,
            timeout=90,
            api_key=SecretStr(openai_key) if openai_key else None,
        )

    # "__groq__" sentinel: skip OpenRouter and go straight to Groq
    if openrouter_model == "__groq__":
        groq_key = settings.api_keys.get("groq", "")
        from langchain_groq import ChatGroq
        logger.info("Using Groq LLM (llama-3.3-70b-versatile)")
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            api_key=SecretStr(groq_key) if groq_key else None,
            timeout=90,
            stop_sequences=None,
        )

    # Default: OpenRouter with the specified model
    openrouter_key = settings.api_keys.get("openrouter", "")
    model = openrouter_model or _OPENROUTER_MODELS[0]
    logger.info("Using OpenRouter LLM (%s)", model)
    return ChatOpenAI(
        model=model,
        temperature=0.1,
        api_key=SecretStr(openrouter_key) if openrouter_key else None,
        base_url="https://openrouter.ai/api/v1",
        timeout=90,
        default_headers={
            "HTTP-Referer": "https://agent-platform.local",
            "X-Title": "Agent Platform",
        },
    )


# ---------------------------------------------------------------------------
# Step 3 — Tool implementations
# ---------------------------------------------------------------------------

_BALANCE_CHAINS: Final[list[dict]] = [
    {
        "name": "Ethereum",
        "rpcs": ["https://eth.llamarpc.com", "https://ethereum.publicnode.com"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
            ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
        ],
    },
    {
        "name": "BNB Chain",
        "rpcs": ["https://bsc-dataseed.binance.org", "https://bsc.publicnode.com"],
        "native": "BNB",
        "tokens": [
            ("USDC", "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", 18),
            ("USDT", "0x55d398326f99059fF775485246999027B3197955", 18),
            ("CAKE", "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", 18),
            ("ABRA", "0x341c05c0E9b33C0E38d64de76516b2Ce970bB3BE", 18),
        ],
    },
    {
        "name": "Polygon",
        "rpcs": ["https://polygon-bor-rpc.publicnode.com", "https://1rpc.io/matic"],
        "native": "MATIC",
        "tokens": [
            ("USDC", "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", 6),
            ("USDT", "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", 6),
        ],
    },
    {
        "name": "Arbitrum",
        "rpcs": ["https://arb1.arbitrum.io/rpc", "https://arbitrum.publicnode.com"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", 6),
            ("USDT", "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", 6),
        ],
    },
    {
        "name": "Optimism",
        "rpcs": ["https://mainnet.optimism.io", "https://optimism.publicnode.com"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", 6),
            ("USDT", "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", 6),
        ],
    },
    {
        "name": "Base",
        "rpcs": ["https://mainnet.base.org", "https://base.llamarpc.com"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6),
            ("USDT", "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", 6),
        ],
    },
    {
        "name": "Avalanche",
        "rpcs": ["https://api.avax.network/ext/bc/C/rpc", "https://avalanche-c-chain-rpc.publicnode.com"],
        "native": "AVAX",
        "tokens": [
            ("USDC", "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", 6),
            ("USDT", "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", 6),
        ],
    },
    {
        "name": "zkSync Era",
        "rpcs": ["https://mainnet.era.zksync.io"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0x1d17CBcF0D6D143135aE902365D2E5e2A16538D4", 6),
            ("USDT", "0x493257fD37EFE3a9E3a304E4C8c71706d1eE41f7", 6),
        ],
    },
    {
        "name": "Linea",
        "rpcs": ["https://rpc.linea.build", "https://linea.publicnode.com"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0x176211869cA2b568f2A7D4EE941E073a821EE1ff", 6),
            ("USDT", "0xA219439258ca9da29E9Cc4cE5596924745e12B93", 6),
        ],
    },
    {
        "name": "Scroll",
        "rpcs": ["https://rpc.scroll.io", "https://scroll.publicnode.com"],
        "native": "ETH",
        "tokens": [
            ("USDC", "0x06eFdBFf2a14a7c8E15944D1F4A48F9F95F663A4", 6),
            ("USDT", "0xf55BEC9cafDbE8730f096Aa55dad6D22d44099Df", 6),
        ],
    },
    {
        "name": "Mantle",
        "rpcs": ["https://rpc.mantle.xyz", "https://mantle.publicnode.com"],
        "native": "MNT",
        "tokens": [
            ("USDC", "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9", 6),
            ("USDT", "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE", 6),
        ],
    },
    {
        "name": "Fantom",
        "rpcs": ["https://rpcapi.fantom.network", "https://fantom-mainnet.public.blastapi.io"],
        "native": "FTM",
        "tokens": [
            ("USDC", "0x04068DA6C83AFCFA0e13ba15A6696662335D5B75", 6),
            ("USDT", "0x049d68029688eAbF473097a2fC38ef61633A3C7A", 6),
        ],
    },
    {
        "name": "Gnosis",
        "rpcs": ["https://rpc.gnosischain.com", "https://gnosis.publicnode.com"],
        "native": "xDAI",
        "tokens": [
            ("USDC", "0xDDAfbb505ad214D7b80b1f830fcCc89B60fb7A83", 6),
            ("USDT", "0x4ECaBa5870353805a9F068101A40E0f32ed605C6", 6),
        ],
    },
    {
        "name": "Celo",
        "rpcs": ["https://forno.celo.org", "https://celo.publicnode.com"],
        "native": "CELO",
        "tokens": [
            ("USDC", "0xcebA9300f2b948710d2653dD7B07f33A8B32118C", 6),
            ("USDT", "0x48065fbBE25f71C9282ddf5e1cD6D6A887483D5e", 6),
        ],
    },
    {
        "name": "Cronos",
        "rpcs": ["https://evm.cronos.org", "https://cronos.publicnode.com"],
        "native": "CRO",
        "tokens": [
            ("USDC", "0xc21223249CA28397B4B6541dfFaEcC539BfF0c59", 6),
            ("USDT", "0x66e428c3f67a68878562e79A0234c1F83c208770", 6),
        ],
    },
    {
        "name": "Solana",
        "type": "solana",
        "rpcs": ["https://api.mainnet-beta.solana.com", "https://solana-rpc.publicnode.com", "https://rpc.ankr.com/solana"],
        "native": "SOL",
        "tokens": [
            ("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
            ("USDT", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
        ],
    },
]


_CHAIN_ALIASES: dict[str, str] = {
    "eth": "Ethereum", "ethereum": "Ethereum",
    "bnb": "BNB Chain", "bsc": "BNB Chain", "binance": "BNB Chain", "bnbchain": "BNB Chain",
    "polygon": "Polygon", "matic": "Polygon",
    "arbitrum": "Arbitrum", "arb": "Arbitrum",
    "optimism": "Optimism", "op": "Optimism",
    "base": "Base",
    "avalanche": "Avalanche", "avax": "Avalanche",
    "zksync": "zkSync Era", "zksyncera": "zkSync Era",
    "linea": "Linea",
    "scroll": "Scroll",
    "mantle": "Mantle", "mnt": "Mantle",
    "fantom": "Fantom", "ftm": "Fantom",
    "gnosis": "Gnosis", "xdai": "Gnosis",
    "celo": "Celo",
    "cronos": "Cronos", "cro": "Cronos",
    "solana": "Solana", "sol": "Solana",
}

_SOL_RPCS_AGENT = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
    "https://rpc.ankr.com/solana",
]
_SOL_SPL_TOKENS = [
    ("USDC", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"),
    ("USDT", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"),
]


_BINANCE_PAIRS: Final[dict[str, str]] = {
    "BNB": "BNBUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT",
    "AVAX": "AVAXUSDT", "MATIC": "MATICUSDT", "FTM": "FTMUSDT",
    "CRO": "CROUSDT", "MNT": "MNTUSDT", "xDAI": "DAIUSDT",
    "CELO": "CELOUSDT",
}


def _get_price_usd(symbol: str) -> float:
    """Fetch USD price from Binance REST; returns 0.0 on any error."""
    if symbol.upper() in {"USDT", "USDC", "DAI", "BUSD", "FDUSD"}:
        return 1.0
    pair = _BINANCE_PAIRS.get(symbol)
    if not pair:
        return 0.0
    try:
        r = _requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={pair}",
            timeout=3,
        )
        if r.status_code == 200:
            return float(r.json().get("price", 0))
    except Exception:
        pass
    return 0.0


def _scan_single_address(raw_addr: str, target_chain: str) -> list[dict]:
    """Scan one address and return a list of chain balance dicts."""
    is_solana_addr = not raw_addr.startswith("0x") and len(raw_addr) >= 32

    # ── Solana ───────────────────────────────────────────────────────────────
    if is_solana_addr:
        sol_native = 0.0
        sol_tokens: list[dict] = []
        sol_seen: set[str] = {"SOL"}  # pre-seed native
        print(f"[SOL] Scanning wallet: {raw_addr}")
        try:
            rpc_url = "https://api.mainnet-beta.solana.com"
            headers = {"Content-Type": "application/json"}

            # 1. Native SOL
            sol_resp = _requests.post(rpc_url, json={
                "jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [raw_addr]
            }, headers=headers, timeout=10)
            print(f"[SOL] SOL DATA: {sol_resp.text}")
            sol_bal = (sol_resp.json().get("result") or {}).get("value", 0) / 10 ** 9
            print(f"[SOL] SOL balance: {sol_bal}")
            if sol_bal > 0.0001:
                sol_native = round(sol_bal, 8)

            # 2. SPL tokens via Moralis Solana Gateway
            if MORALIS_API_KEY:
                moralis_headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
                spl_url = f"https://solana-gateway.moralis.io/account/mainnet/{raw_addr}/tokens"
                try:
                    spl_resp = _requests.get(spl_url, headers=moralis_headers, timeout=8)
                    print(f"[SOL] Moralis SPL status: {spl_resp.status_code}")
                    if spl_resp.status_code == 200:
                        for tok in spl_resp.json():
                            symbol = tok.get("symbol", "")
                            if not symbol or tok.get("possible_spam", False):
                                continue
                            # Moralis Solana API returns 'amount' already human-readable
                            ui_bal = float(tok.get("amount") or 0)
                            if ui_bal >= 0.00000001:
                                sym_up = symbol.upper()
                                if sym_up in sol_seen:
                                    continue
                                sol_seen.add(sym_up)
                                _STABLE = {"USDC", "USDT", "DAI", "BUSD", "FDUSD"}
                                tok_usd = round(ui_bal, 4) if symbol in _STABLE else 0.0
                                print(f"[SOL] SPL token: {symbol} bal={ui_bal}")
                                sol_tokens.append({"symbol": symbol, "balance": round(ui_bal, 6), "usd_value": tok_usd})
                    else:
                        print(f"[SOL] Moralis SPL error: {spl_resp.text[:200]}")
                except Exception as spl_exc:
                    print(f"[SOL] Moralis SPL failed: {spl_exc}")

        except Exception as exc:
            print(f"[SOL] Error: {exc}")

        if sol_native == 0.0 and not sol_tokens:
            return []
        # Post-process dedup for Solana SPL tokens
        unique_sol: dict[str, dict] = {}
        for t in sol_tokens:
            k = t["symbol"].upper()
            if k not in unique_sol:
                unique_sol[k] = t
        sol_tokens = list(unique_sol.values())
        sol_price = _get_price_usd("SOL")
        native_usd = round(sol_native * sol_price, 4)
        sol_usd = native_usd + sum(t.get("usd_value", 0.0) for t in sol_tokens)
        return [{"chain": "Solana", "native_symbol": "SOL",
                 "native_balance": sol_native, "native_usd": native_usd,
                 "tokens": sol_tokens, "usd_total": round(sol_usd, 2)}]

    # ── EVM chains (concurrent) ─────────────────────────────────────────────
    try:
        evm_address = Web3.to_checksum_address(raw_addr)
    except ValueError:
        return []

    evm_chains = [
        c for c in _BALANCE_CHAINS
        if c.get("type") != "solana"
        and (not target_chain or c["name"] == target_chain)
    ]
    logger.info("[BALANCE] Scanning %d chains, target=%s", len(evm_chains), target_chain)

    # Pre-fetch prices once for all unique native symbols
    unique_natives = {c["native"] for c in evm_chains}
    native_prices: dict[str, float] = {sym: _get_price_usd(sym) for sym in unique_natives}

    def check_evm(chain: dict) -> Optional[dict]:
        chain_name = chain["name"]
        native_sym = chain["native"]
        native_balance = 0.0
        usd_total_chain = 0.0
        tokens: list[dict] = []
        seen_symbols: set[str] = {native_sym.upper()}  # pre-seed with native to block duplicates

        def rpc_post(payload: dict) -> dict:
            for rpc in chain["rpcs"]:
                try:
                    r = _requests.post(rpc, json=payload, timeout=3)
                    data = r.json()
                    if "result" in data:
                        return data
                except Exception:
                    continue
            return {}

        # 1. Native balance via RPC
        try:
            d = rpc_post({"jsonrpc": "2.0", "method": "eth_getBalance",
                          "params": [evm_address, "latest"], "id": 1})
            h = d.get("result", "0x0") or "0x0"
            if h not in ("0x", "0x0", "0x00"):
                bal = int(h, 16) / 10 ** 18
                if bal > 0.0001:
                    native_balance = round(bal, 8)
                    usd_total_chain += native_balance * native_prices.get(native_sym, 0.0)
        except Exception:
            pass

        # 2. ERC-20 tokens via Moralis API
        # Only call Moralis for "important" chains to save API quota (free tier is limited)
        _MORALIS_PRIORITY = {"Ethereum", "BNB Chain", "Polygon", "Arbitrum", "Avalanche", "Base", "Optimism"}
        moralis_chain = _MORALIS_CHAINS.get(chain_name)
        if moralis_chain and MORALIS_API_KEY and (chain_name in _MORALIS_PRIORITY or native_balance > 0):
            url = f"https://deep-index.moralis.io/api/v2.2/wallets/{evm_address}/tokens?chain={moralis_chain}"
            headers = {"accept": "application/json", "X-API-Key": MORALIS_API_KEY}
            for attempt in range(2):
                try:
                    tok_resp = _requests.get(url, headers=headers, timeout=8)
                    if tok_resp.status_code == 429:
                        logger.info("[Moralis] %s: 429 rate limit, attempt %d/2", chain_name, attempt + 1)
                        time.sleep(1.0)
                        continue
                    if tok_resp.status_code == 200:
                        _SPAM_TICKERS = {"FL", "SIGN", "EC", "GPT", "XAI", "LP-USDT", "AWSAI", "C3 Coin", "MA", "毒王", "比特币", "Claude"}
                        tokens_to_verify: dict[str, dict] = {}

                        # 1. Primary collection + spam filter
                        for tok in tok_resp.json().get("result", []):
                            symbol = tok.get("symbol", "Unknown")
                            if symbol in _SPAM_TICKERS or tok.get("possible_spam", False):
                                continue
                            decimals = int(tok.get("decimals", 18))
                            ui_bal = float(tok.get("balance", 0)) / (10 ** decimals)
                            token_usd = float(tok.get("usd_value") or 0)
                            token_address = tok.get("token_address", "").lower()
                            if ui_bal >= 0.00000001:
                                tokens_to_verify[token_address] = {
                                    "symbol": symbol,
                                    "balance": ui_bal,
                                    "moralis_usd": token_usd,
                                    "decimals": decimals,
                                }

                        # 2. DexScreener liquidity check (batch, free, no key needed)
                        dex_data_map: dict[str, dict] = {}
                        if tokens_to_verify:
                            addresses_str = ",".join(list(tokens_to_verify.keys())[:30])
                            dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{addresses_str}"
                            try:
                                dex_resp = _requests.get(dex_url, timeout=5)
                                if dex_resp.status_code == 200:
                                    for pair in dex_resp.json().get("pairs") or []:
                                        t_addr = pair.get("baseToken", {}).get("address", "").lower()
                                        liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                                        vol = float((pair.get("volume") or {}).get("h24") or 0)
                                        price_usd = float(pair.get("priceUsd") or 0)
                                        if t_addr not in dex_data_map or liq > dex_data_map[t_addr]["liq"]:
                                            dex_data_map[t_addr] = {"liq": liq, "vol": vol, "price": price_usd}
                            except Exception as dex_exc:
                                print(f"[DexScreener] {chain_name}: {dex_exc}")

                        # 3. Build final token list with verified USD
                        _BLUECHIP = {"USDC", "USDT", "DAI", "WBTC", "WETH", "ETH", "BNB", "WBNB", "AVAX", "CAKE", "MATIC"}
                        for addr, t_data in tokens_to_verify.items():
                            symbol = t_data["symbol"]
                            ui_bal = t_data["balance"]
                            trusted_usd = t_data["moralis_usd"]
                            if symbol not in _BLUECHIP:
                                dex = dex_data_map.get(addr, {"liq": 0, "vol": 0, "price": 0.0})
                                # Use real DEX price instead of Moralis estimate
                                trusted_usd = ui_bal * dex["price"]
                                # Dead pool: insufficient liquidity or volume → zero out
                                if dex["liq"] < 2000 or dex["vol"] < 100:
                                    trusted_usd = 0.0
                            sym_up = symbol.upper()
                            if sym_up in seen_symbols:
                                continue
                            seen_symbols.add(sym_up)
                            if trusted_usd >= 0.01 or ui_bal >= 0.00000001:
                                tokens.append({
                                    "symbol": symbol,
                                    "balance": round(ui_bal, 6),
                                    "usd_value": round(trusted_usd, 4),
                                    "address": addr,
                                    "decimals": int(t_data.get("decimals", 18) or 18),
                                })
                                usd_total_chain += trusted_usd
                        # Cache discovered tokens for RPC fallback
                        if tokens_to_verify:
                            _save_discovered_tokens(evm_address, chain_name, [
                                {"symbol": d["symbol"], "token_address": a,
                                 "decimals": d.get("decimals", 18)}
                                for a, d in tokens_to_verify.items()
                            ])
                    else:
                        print(f"[Moralis] {chain_name}: HTTP {tok_resp.status_code}")
                    break
                except Exception as e:
                    print(f"[Moralis] Error on {chain_name} (attempt {attempt + 1}/3): {e}")
                    time.sleep(1.0)

        # 3. Fallback: RPC-based ERC-20 scan for known tokens (free, no API key)
        # Used when Moralis is unavailable, rate-limited, or returns no tokens
        # Merges registry tokens + previously discovered tokens for this wallet
        if not tokens:
            _CHAIN_ID_BY_NAME = {"Ethereum": 1, "BNB Chain": 56, "Polygon": 137,
                                  "Arbitrum": 42161, "Optimism": 10, "Base": 8453, "Avalanche": 43114}
            _cid = _CHAIN_ID_BY_NAME.get(chain_name)
            _known_tokens: dict[str, dict[str, Any]] = {}
            if _cid:
                _known_tokens.update(TOKENS_BY_CHAIN.get(_cid, {}))
            # Add previously discovered tokens (from earlier Moralis scans)
            discovered = _get_discovered_tokens(evm_address, chain_name)
            for sym, info in discovered.items():
                if sym not in _known_tokens:
                    _known_tokens[sym] = info
            if _known_tokens:
                for sym, info in _known_tokens.items():
                    sym_up = sym.upper()
                    if sym_up in seen_symbols:
                        continue
                    tok_addr = info.get("address", "")
                    if not tok_addr or tok_addr.lower() == _ENSO_NATIVE_TOKEN:
                        continue
                    decimals = int(info.get("decimals", 18) or 18)
                    # balanceOf(address) selector = 0x70a08231
                    call_data = "0x70a08231" + "0" * 24 + evm_address[2:].lower()
                    try:
                        d = rpc_post({"jsonrpc": "2.0", "method": "eth_call",
                                      "params": [{"to": tok_addr, "data": call_data}, "latest"], "id": 1})
                        h = d.get("result", "0x0") or "0x0"
                        if h in ("0x", "0x0", "0x00", "0x" + "0" * 64):
                            continue
                        raw_bal = int(h, 16)
                        if raw_bal <= 0:
                            continue
                        ui_bal = raw_bal / (10 ** decimals)
                        if ui_bal < 0.00000001:
                            continue
                        seen_symbols.add(sym_up)
                        # Estimate USD for stablecoins
                        _STABLES = {"USDC", "USDT", "DAI", "BUSD", "TUSD", "FDUSD"}
                        tok_usd = round(ui_bal, 4) if sym_up in _STABLES else 0.0
                        tokens.append({
                            "symbol": sym,
                            "balance": round(ui_bal, 6),
                            "usd_value": tok_usd,
                            "address": tok_addr.lower(),
                            "decimals": decimals,
                        })
                        usd_total_chain += tok_usd
                    except Exception:
                        continue
                # Get USD prices for non-stable tokens via DexScreener batch
                non_stable_addrs = [t["address"] for t in tokens if t["usd_value"] == 0.0 and t.get("address")]
                if non_stable_addrs:
                    try:
                        dex_url = f"https://api.dexscreener.com/latest/dex/tokens/{','.join(non_stable_addrs[:30])}"
                        dex_resp = _requests.get(dex_url, timeout=5)
                        if dex_resp.status_code == 200:
                            price_map: dict[str, float] = {}
                            for pair in dex_resp.json().get("pairs") or []:
                                ba = pair.get("baseToken", {}).get("address", "").lower()
                                price = float(pair.get("priceUsd") or 0)
                                if ba and price > 0 and (ba not in price_map or price > price_map[ba]):
                                    price_map[ba] = price
                            for t in tokens:
                                if t["usd_value"] == 0.0 and t.get("address") in price_map:
                                    t["usd_value"] = round(t["balance"] * price_map[t["address"]], 4)
                                    usd_total_chain += t["usd_value"]
                    except Exception:
                        pass

        if native_balance == 0.0 and not tokens:
            return None
        # Post-process dedup: keep first occurrence per symbol (native always wins, it was pre-seeded)
        unique: dict[str, dict] = {}
        for t in tokens:
            k = t["symbol"].upper()
            if k not in unique:
                unique[k] = t
        tokens = list(unique.values())
        if tokens:
            _save_discovered_tokens(evm_address, chain_name, tokens)
        native_usd = round(native_balance * native_prices.get(native_sym, 0.0), 4)
        return {"chain": chain_name, "native_symbol": native_sym,
                "native_balance": native_balance, "native_usd": native_usd,
                "tokens": tokens, "usd_total": round(usd_total_chain, 2)}

    # Scan EVM chains — prioritize chains likely to have balances
    # Move Ethereum, BNB Chain, Avalanche, Polygon, Arbitrum to the front
    priority_names = {"Ethereum", "BNB Chain", "Avalanche", "Polygon", "Arbitrum", "Optimism", "Base"}
    priority = [c for c in evm_chains if c["name"] in priority_names]
    others = [c for c in evm_chains if c["name"] not in priority_names]

    chain_dicts: list[dict] = []
    for chain in priority + others:
        try:
            res = check_evm(chain)
            if res:
                chain_dicts.append(res)
        except Exception:
            pass

    return chain_dicts


# Balance cache: avoids Moralis rate limits when called twice in quick succession
_balance_cache: dict[str, tuple[float, str]] = {}  # key → (timestamp, json_result)
_BALANCE_CACHE_TTL = 30  # seconds


def get_smart_wallet_balance(addr_input: str, user_address: str = "", solana_address: str = "") -> str:
    """
    Checks balances for one or more addresses (comma-separated).
    Phantom dual-chain wallets send "solAddr,evmAddr" — both are scanned.
    Supports 'address|chain' pipe filter (applied to all addresses).
    """
    # Check cache first (use full scan cache for filtered requests too)
    cache_key = addr_input.split("|")[0].strip().lower()  # cache by address only
    now = time.time()
    if cache_key in _balance_cache:
        cached_time, cached_result = _balance_cache[cache_key]
        if now - cached_time < _BALANCE_CACHE_TTL:
            # For filtered requests (e.g. "addr|bnb"), filter the cached full result
            if "|" in addr_input:
                chain_filter = addr_input.split("|", 1)[1].strip().lower()
                target = _CHAIN_ALIASES.get(chain_filter.replace(" ", ""), "") if chain_filter else ""
                if target:
                    try:
                        full = json.loads(cached_result)
                        filtered = [b for b in full.get("balances", []) if b.get("chain") == target]
                        if filtered:
                            total = round(sum(b.get("usd_total", 0) for b in filtered), 2)
                            return json.dumps({"type": "balance_report",
                                               "wallet_addresses": full.get("wallet_addresses", []),
                                               "balances": filtered, "total_usd": total})
                    except Exception:
                        pass
            else:
                return cached_result

    # Parse optional pipe chain filter
    if "|" in addr_input:
        addr_part, chain_filter = addr_input.split("|", 1)
        chain_filter = chain_filter.strip().lower()
    else:
        addr_part, chain_filter = addr_input, ""

    # Split by comma for multi-address (Phantom dual-chain)
    raw_addrs = [a.strip() for a in addr_part.split(",") if a.strip()]
    if not raw_addrs:
        # Fall back to injected user/solana addresses
        for fallback in [user_address, solana_address]:
            for a in fallback.split(","):
                a = a.strip()
                if a:
                    raw_addrs.append(a)
    if not raw_addrs:
        return "No wallet address provided."

    target_chain = _CHAIN_ALIASES.get(chain_filter.replace(" ", ""), "") if chain_filter else ""

    wallet_addresses: list[str] = []
    all_balances: list[dict] = []
    for addr in raw_addrs:
        wallet_addresses.append(addr)
        chain_entries = _scan_single_address(addr, target_chain)
        all_balances.extend(chain_entries)

    total_usd = round(sum(entry.get("usd_total", 0.0) for entry in all_balances), 2)
    result: dict = {
        "type": "balance_report",
        "wallet_addresses": wallet_addresses,
        "balances": all_balances,
        "total_usd": total_usd,
    }
    if not all_balances:
        result["message"] = "No balances found across any chain."
    result_json = json.dumps(result)

    # Cache the FULL (unfiltered) result for reuse
    if not chain_filter and all_balances:
        for addr in wallet_addresses:
            _balance_cache[addr.lower()] = (time.time(), result_json)

    return result_json


def _get_balance_via_portfolio(addr_input: str, user_address: str = "", solana_address: str = "") -> str:
    """
    Get wallet balance by calling the portfolio endpoint internally.
    This uses the same async code path that works in the Portfolio tab.
    """
    requested_addr = addr_input.strip().split("|")[0].strip()
    if requested_addr:
        addr = requested_addr
    elif user_address and solana_address:
        addr = f"{solana_address},{user_address}"
    else:
        addr = user_address or solana_address
    if not addr:
        return json.dumps({"type": "balance_report", "balances": [], "total_usd": 0,
                           "message": "No wallet address provided."})
    try:
        resp = httpx.get(f"http://127.0.0.1:8000/api/portfolio/{addr}", timeout=60)
        if resp.status_code != 200:
            # Fallback to direct scan
            return get_smart_wallet_balance(addr_input, user_address, solana_address)
        data = resp.json()
        # Convert portfolio format → balance_report format
        chains: dict[str, dict] = {}
        for tok in data.get("tokens", []):
            chain_name = tok.get("chainName", "Unknown")
            if chain_name not in chains:
                chains[chain_name] = {
                    "chain": chain_name,
                    "native_symbol": "",
                    "native_balance": 0,
                    "native_usd": 0,
                    "tokens": [],
                    "usd_total": 0,
                }
            c = chains[chain_name]
            bal = tok.get("balanceRaw", 0)
            usd = tok.get("valueUsd", 0)
            sym = tok.get("symbol", "")
            # Check if this is the native token for the chain
            _CHAIN_NATIVES = {"Ethereum": "ETH", "BNB Chain": "BNB", "Polygon": "MATIC",
                              "Arbitrum": "ETH", "Optimism": "ETH", "Base": "ETH",
                              "Avalanche": "AVAX", "Solana": "SOL", "Fantom": "FTM",
                              "Gnosis": "xDAI", "Celo": "CELO", "Cronos": "CRO",
                              "Mantle": "MNT", "zkSync Era": "ETH", "Linea": "ETH", "Scroll": "ETH"}
            native_sym = _CHAIN_NATIVES.get(chain_name, "")
            if sym == native_sym:
                c["native_symbol"] = sym
                c["native_balance"] = bal
                c["native_usd"] = usd
            else:
                c["tokens"].append({"symbol": sym, "balance": round(bal, 6), "usd_value": round(usd, 4)})
            c["usd_total"] = round(c["usd_total"] + usd, 2)
        balances = list(chains.values())
        total_usd = round(sum(c["usd_total"] for c in balances), 2)
        return json.dumps({
            "type": "balance_report",
            "wallet_addresses": [addr],
            "balances": balances,
            "total_usd": total_usd,
        })
    except Exception as exc:
        logger.warning("Portfolio balance fallback: %s", exc)
        return get_smart_wallet_balance(addr_input, user_address, solana_address)


def _simulate_swap(raw_input: str, chain_id: int) -> str:
    """
    Estimates swap output using token prices.

    Input format (space-separated):
        TOKEN_IN_SYMBOL TOKEN_OUT_SYMBOL AMOUNT
    Example: BNB USDT 0.01
    """
    parts = raw_input.strip().split()
    if len(parts) < 2:
        return "Usage: TOKEN_IN TOKEN_OUT [AMOUNT] — e.g. 'BNB USDT 0.01'"
    src_sym = parts[0].upper()
    dst_sym = parts[1].upper()
    amount = float(parts[2]) if len(parts) > 2 else 1.0

    src_price = _get_price_usd(src_sym)
    dst_price = _get_price_usd(dst_sym)
    if src_price <= 0:
        return f"Could not find price for {src_sym}"
    if dst_price <= 0:
        return f"Could not find price for {dst_sym}"

    out_amount = (amount * src_price) / dst_price
    return (
        f"Swap estimate: {amount} {src_sym} (${src_price:.4f}) → "
        f"{out_amount:.6f} {dst_sym} (${dst_price:.4f})"
    )


def _get_token_price(token_input: str) -> str:
    """
    Returns the current USD price.  Tries Binance first (fast, no key),
    falls back to CoinGecko (accepts both symbol and CoinGecko ID).
    """
    cleaned = token_input.strip().strip('"\'')
    symbol = cleaned.upper()
    coin_id = cleaned.lower()

    if symbol in {"USDT", "USDC", "DAI", "BUSD", "FDUSD"}:
        return f"{symbol}/USD = $1.0000 (stablecoin)"

    # --- Binance ---
    try:
        resp = httpx.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": f"{symbol}USDT"},
            timeout=5,
        )
        if resp.status_code == 200:
            price = resp.json().get("price", "N/A")
            return f"{symbol}/USDT = ${price} (Binance)"
    except Exception:
        pass

    # --- CoinGecko fallback ---
    try:
        resp = httpx.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if coin_id in data:
            price = data[coin_id]["usd"]
            return f"{coin_id} = ${price} USD (CoinGecko)"
        return (
            f"Token '{token_input}' not found. "
            "Try the CoinGecko ID (e.g. 'binancecoin' for BNB, 'bitcoin' for BTC)."
        )
    except Exception as exc:
        logger.warning("get_token_price error for %s: %s", token_input, exc)
        return f"Price lookup failed: {exc}"


# ---------------------------------------------------------------------------
# Platform fee configuration
# ---------------------------------------------------------------------------

# Enso: basis points (50 = 0.5 %)
PLATFORM_FEE_BPS: Final = 50

# Jupiter: basis points integer  (50 = 0.5 %)
_PLATFORM_FEE_BPS: Final = 50

_ENSO_BASE_URL: Final = "https://api.enso.build"
_ENSO_NATIVE_TOKEN: Final = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

# Enso-supported chains
_ENSO_SUPPORTED: Final = frozenset({1, 10, 56, 100, 137, 324, 8453, 42161, 43114, 59144})


def _enso_headers() -> dict[str, str]:
    api_key = (settings.enso_api_key or "").strip()
    return {
        "X-Api-Key": api_key,
        "Accept": "application/json",
    }


def _jupiter_fee_account() -> str:
    """Solana Associated Token Account that receives Jupiter platform fees."""
    return settings.api_keys.get("jupiter_fee_account", "")


# ---------------------------------------------------------------------------
# build_swap_tx helpers
# ---------------------------------------------------------------------------

def _resolve_token_address(symbol_or_addr: str, chain_id: int) -> str:
    """Resolve a token symbol like 'USDT' to its address, or return address as-is."""
    address, _, _ = _resolve_token_metadata(symbol_or_addr, chain_id)
    return address


def _resolve_token_metadata(
    symbol_or_addr: str,
    chain_id: int,
    wallet_addr: str = "",
    search_wallet_all_chains: bool = False,
) -> tuple[str, Optional[int], int]:
    """Resolve token symbol/address and best-effort decimals using registry, cache, DexScreener, and Moralis."""
    val = symbol_or_addr.strip()
    if not val:
        return "", None, chain_id

    chain_name_by_id = {
        1: "Ethereum",
        10: "Optimism",
        56: "BNB Chain",
        137: "Polygon",
        8453: "Base",
        42161: "Arbitrum",
        43114: "Avalanche",
    }
    dex_chain_by_id = {
        1: "ethereum",
        10: "optimism",
        56: "bsc",
        137: "polygon",
        8453: "base",
        42161: "arbitrum",
        43114: "avalanche",
    }

    # Already an address
    if val.startswith("0x") and len(val) == 42:
        try:
            return Web3.to_checksum_address(val), None, chain_id
        except Exception:
            return val, None, chain_id

    # Native token aliases
    if val.lower() in ("native", "eth", "bnb", "matic", "avax", "ftm"):
        return _ENSO_NATIVE_TOKEN, 18, chain_id

    # Look up in token registry on current chain
    chain_tokens = TOKENS_BY_CHAIN.get(chain_id, POPULAR_TOKENS)
    tok = chain_tokens.get(val.lower())
    if tok:
        return tok["address"], int(tok.get("decimals", 18) or 18), chain_id

    # Fallback: try all chains
    for other_chain_id, tokens in TOKENS_BY_CHAIN.items():
        tok = tokens.get(val.lower())
        if tok:
            return tok["address"], int(tok.get("decimals", 18) or 18), other_chain_id

    # Wallet-scoped cache from prior balance scans
    chain_name = chain_name_by_id.get(chain_id, "")
    if wallet_addr and chain_name:
        discovered = _get_discovered_tokens(wallet_addr, chain_name)
        disc = discovered.get(val.lower())
        disc_addr = (disc or {}).get("address", "")
        if disc_addr:
            try:
                return Web3.to_checksum_address(disc_addr), int((disc or {}).get("decimals", 18) or 18), chain_id
            except Exception:
                return disc_addr, int((disc or {}).get("decimals", 18) or 18), chain_id

    # If the user says "from my wallet", trust the wallet inventory before symbol search.
    if wallet_addr and chain_name:
        try:
            scanned = _scan_single_address(wallet_addr, chain_name)
            for entry in scanned:
                if entry.get("chain") != chain_name:
                    continue
                for tok in entry.get("tokens") or []:
                    if str(tok.get("symbol", "")).upper() != val.upper():
                        continue
                    tok_addr = str(tok.get("address", "") or "")
                    if not tok_addr:
                        continue
                    decimals = tok.get("decimals")
                    try:
                        tok_addr = Web3.to_checksum_address(tok_addr)
                    except Exception:
                        pass
                    _save_discovered_tokens(wallet_addr, chain_name, [{
                        "symbol": tok.get("symbol", val),
                        "address": tok_addr,
                        "decimals": int(decimals or 18),
                    }])
                    return tok_addr, int(decimals or 18), chain_id
        except Exception:
            pass

    # Fuzzy wallet-held token match for minor typos like MACRO -> MARCO.
    if wallet_addr and chain_name:
        discovered = _get_discovered_tokens(wallet_addr, chain_name)
        candidates = list(discovered.keys())
        if candidates and len(val) >= 3:
            matches = get_close_matches(val.lower(), candidates, n=1, cutoff=0.8)
            if matches:
                disc = discovered.get(matches[0]) or {}
                disc_addr = str(disc.get("address", "") or "")
                if disc_addr:
                    logger.info("Resolved wallet token typo %s -> %s on %s", val, matches[0], chain_name)
                    try:
                        return Web3.to_checksum_address(disc_addr), int(disc.get("decimals", 18) or 18), chain_id
                    except Exception:
                        return disc_addr, int(disc.get("decimals", 18) or 18), chain_id

    if wallet_addr and search_wallet_all_chains:
        for other_chain_id, other_chain_name in chain_name_by_id.items():
            if other_chain_id == chain_id:
                continue
            discovered = _get_discovered_tokens(wallet_addr, other_chain_name)
            direct = discovered.get(val.lower())
            if direct and direct.get("address"):
                try:
                    return Web3.to_checksum_address(str(direct["address"])), int(direct.get("decimals", 18) or 18), other_chain_id
                except Exception:
                    return str(direct["address"]), int(direct.get("decimals", 18) or 18), other_chain_id
            candidates = list(discovered.keys())
            if candidates and len(val) >= 3:
                matches = get_close_matches(val.lower(), candidates, n=1, cutoff=0.8)
                if matches:
                    disc = discovered.get(matches[0]) or {}
                    disc_addr = str(disc.get("address", "") or "")
                    if disc_addr:
                        logger.info("Resolved cross-chain wallet token typo %s -> %s on %s", val, matches[0], other_chain_name)
                        try:
                            return Web3.to_checksum_address(disc_addr), int(disc.get("decimals", 18) or 18), other_chain_id
                        except Exception:
                            return disc_addr, int(disc.get("decimals", 18) or 18), other_chain_id

        for other_chain_id, other_chain_name in chain_name_by_id.items():
            if other_chain_id == chain_id:
                continue
            try:
                scanned = _scan_single_address(wallet_addr, other_chain_name)
                for entry in scanned:
                    if entry.get("chain") != other_chain_name:
                        continue
                    symbols = {str(tok.get("symbol", "")).lower(): tok for tok in entry.get("tokens") or []}
                    chosen = symbols.get(val.lower())
                    if not chosen and len(val) >= 3 and symbols:
                        matches = get_close_matches(val.lower(), list(symbols.keys()), n=1, cutoff=0.8)
                        if matches:
                            chosen = symbols.get(matches[0])
                    if not chosen:
                        continue
                    tok_addr = str(chosen.get("address", "") or "")
                    if not tok_addr:
                        continue
                    decimals = int(chosen.get("decimals", 18) or 18)
                    _save_discovered_tokens(wallet_addr, other_chain_name, [{
                        "symbol": chosen.get("symbol", val),
                        "address": tok_addr,
                        "decimals": decimals,
                    }])
                    try:
                        tok_addr = Web3.to_checksum_address(tok_addr)
                    except Exception:
                        pass
                    logger.info("Resolved %s from wallet inventory on %s", val, other_chain_name)
                    return tok_addr, decimals, other_chain_id
            except Exception:
                pass

    # DexScreener search fallback, choose the most liquid exact-symbol match on target chain
    dex_chain = dex_chain_by_id.get(chain_id, "")
    if dex_chain:
        try:
            dex_resp = _requests.get(
                f"https://api.dexscreener.com/latest/dex/search?q={val}", timeout=8
            )
            if dex_resp.status_code == 200:
                best_addr = ""
                best_liq = -1.0
                for pair in dex_resp.json().get("pairs") or []:
                    if pair.get("chainId") != dex_chain:
                        continue
                    liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                    for side in ("baseToken", "quoteToken"):
                        token = pair.get(side) or {}
                        if token.get("symbol", "").upper() != val.upper():
                            continue
                        addr = token.get("address", "")
                        if addr and liq > best_liq:
                            best_addr = addr
                            best_liq = liq
                if best_addr:
                    logger.info("Resolved %s via DexScreener → %s", val, best_addr)
                    return Web3.to_checksum_address(best_addr), None, chain_id
        except Exception:
            pass

    # Last resort: wallet-scoped Moralis token scan
    if wallet_addr and MORALIS_API_KEY and chain_name:
        moralis_chain = _MORALIS_CHAINS.get(chain_name)
        if moralis_chain:
            try:
                url = f"https://deep-index.moralis.io/api/v2.2/wallets/{wallet_addr}/tokens?chain={moralis_chain}"
                resp = _requests.get(
                    url,
                    headers={"accept": "application/json", "X-API-Key": MORALIS_API_KEY},
                    timeout=8,
                )
                if resp.status_code == 200:
                    for tok in resp.json().get("result", []):
                        if tok.get("symbol", "").upper() != val.upper():
                            continue
                        addr = tok.get("token_address", "")
                        if addr:
                            decimals = int(tok.get("decimals", 18) or 18)
                            return Web3.to_checksum_address(addr), decimals, chain_id
            except Exception:
                pass

    return val, None, chain_id  # Return as-is, Enso will reject if invalid


def _build_enso_swap_tx(
    params: dict[str, Any],
    user_address: str,
    default_chain_id: int,
) -> str:
    """
    Calls Enso Finance /api/v1/shortcuts/route to build a ready-to-sign EVM swap tx.
    Returns ALL fields the frontend needs for the Swap Preview card.
    """
    chain_id = int(params.get("chain_id", default_chain_id))
    if chain_id not in _ENSO_SUPPORTED:
        return json.dumps({
            "status": "error",
            "message": f"Chain {chain_id} is not supported by Enso. Supported: {sorted(_ENSO_SUPPORTED)}",
        })

    token_in_raw = params.get("token_in", "")
    token_out_raw = params.get("token_out", "")
    from_addr = params.get("from", user_address).strip() or user_address
    src, discovered_src_decimals, resolved_chain_id = _resolve_token_metadata(
        token_in_raw,
        chain_id,
        from_addr,
        search_wallet_all_chains=True,
    )
    chain_id = resolved_chain_id
    dst, _, _ = _resolve_token_metadata(token_out_raw, chain_id, from_addr)
    amount = str(params.get("amount", ""))
    slippage_bps = int(params.get("slippage_bps", 100))

    # --- Handle "all" amount: look up on-chain balance automatically ---
    if amount.lower().strip() in ("all", "max", ""):
        in_sym = token_in_raw.strip().upper()
        native_sym = _CHAIN_META.get(chain_id, {}).get("native", "ETH").upper()
        is_native = in_sym in ("NATIVE", native_sym)

        if is_native:
            # Native balance via RPC — free, no Moralis needed
            _chain_rpcs = {
                56: ["https://bsc-dataseed1.binance.org", "https://bsc-dataseed2.binance.org"],
                1: ["https://eth.llamarpc.com", "https://rpc.ankr.com/eth"],
                137: ["https://polygon-rpc.com"],
                43114: ["https://api.avax.network/ext/bc/C/rpc"],
                42161: ["https://arb1.arbitrum.io/rpc"],
                10: ["https://mainnet.optimism.io"],
                8453: ["https://mainnet.base.org"],
            }
            rpcs = _chain_rpcs.get(chain_id, [])
            found_amount = 0.0
            for rpc in rpcs:
                try:
                    r = _requests.post(rpc, json={"jsonrpc": "2.0", "method": "eth_getBalance",
                                                   "params": [from_addr, "latest"], "id": 1}, timeout=5)
                    h = r.json().get("result", "0x0") or "0x0"
                    if h not in ("0x", "0x0", "0x00"):
                        found_amount = int(h, 16) / 10 ** 18
                    break
                except Exception:
                    continue
            if found_amount <= 0.0001:
                return json.dumps({"status": "error",
                                   "message": f"No {in_sym} balance found in your wallet."})
            # Leave a small amount for gas
            gas_reserve = 0.002 if chain_id == 56 else 0.005
            found_amount = max(0, found_amount - gas_reserve)
            amount = str(int(found_amount * (10 ** 18)))
        else:
            # ERC-20 balance via direct balanceOf RPC call — no Moralis needed
            # If src was not resolved to an address, try cache + DexScreener + Moralis before failing.
            if not (src.startswith("0x") and len(src) == 42) or src == _ENSO_NATIVE_TOKEN:
                src, discovered_src_decimals, chain_id = _resolve_token_metadata(
                    in_sym,
                    chain_id,
                    from_addr,
                    search_wallet_all_chains=True,
                )
                if not (src.startswith("0x") and len(src) == 42) or src == _ENSO_NATIVE_TOKEN:
                    return json.dumps({
                        "status": "error",
                        "message": f"Cannot resolve token address for {in_sym}. Try using the contract address.",
                    })

            # Get decimals from registry or default to 18
            _chain_tokens = TOKENS_BY_CHAIN.get(chain_id, POPULAR_TOKENS)
            decimals = discovered_src_decimals or 18
            for sym, info in _chain_tokens.items():
                if sym.upper() == in_sym or info.get("address", "").lower() == src.lower():
                    decimals = int(info.get("decimals", 18) or 18)
                    break
            # Call balanceOf(address) on the token contract
            balance_of_data = "0x70a08231" + "0" * 24 + from_addr[2:].lower()
            _chain_rpcs = {
                56: ["https://bsc-dataseed1.binance.org", "https://bsc-dataseed2.binance.org"],
                1: ["https://eth.llamarpc.com", "https://rpc.ankr.com/eth"],
                137: ["https://polygon-rpc.com"],
                43114: ["https://api.avax.network/ext/bc/C/rpc"],
                42161: ["https://arb1.arbitrum.io/rpc"],
                10: ["https://mainnet.optimism.io"],
                8453: ["https://mainnet.base.org"],
            }
            rpcs = _chain_rpcs.get(chain_id, [])
            raw_balance = 0
            for rpc in rpcs:
                try:
                    r = _requests.post(rpc, json={
                        "jsonrpc": "2.0", "method": "eth_call",
                        "params": [{"to": src, "data": balance_of_data}, "latest"], "id": 1
                    }, timeout=5)
                    h = r.json().get("result", "0x0") or "0x0"
                    if h not in ("0x", "0x0", "0x00", "0x" + "0" * 64):
                        raw_balance = int(h, 16)
                    break
                except Exception:
                    continue
            if raw_balance <= 0:
                return json.dumps({"status": "error",
                                   "message": f"No {in_sym} balance found in your wallet."})
            amount = str(raw_balance)

    if not (src and dst and amount):
        return json.dumps(
            {"status": "error", "message": "token_in, token_out and amount are required"}
        )

    # Determine display symbols
    chain_meta = _CHAIN_META.get(chain_id, {})
    native_sym = chain_meta.get("native", "ETH")

    def _symbol_for(raw: str, addr: str) -> str:
        r = raw.strip().upper()
        if r in ("NATIVE", native_sym):
            return native_sym
        chain_tokens = TOKENS_BY_CHAIN.get(chain_id, POPULAR_TOKENS)
        for sym, info in chain_tokens.items():
            if info.get("address", "").lower() == addr.lower():
                return sym.upper()
            if r == sym.upper():
                return sym.upper()
        for tokens in TOKENS_BY_CHAIN.values():
            for sym, info in tokens.items():
                if info.get("address", "").lower() == addr.lower():
                    return sym.upper()
        wallet_chain_name = {
            1: "Ethereum",
            10: "Optimism",
            56: "BNB Chain",
            137: "Polygon",
            8453: "Base",
            42161: "Arbitrum",
            43114: "Avalanche",
        }.get(chain_id, "")
        if wallet_chain_name and from_addr:
            discovered = _get_discovered_tokens(from_addr, wallet_chain_name)
            for sym, info in discovered.items():
                if str(info.get("address", "")).lower() == addr.lower():
                    return sym.upper()
        return r if r and not r.startswith("0X") else "Token"

    from_symbol = _symbol_for(token_in_raw, src)
    to_symbol = _symbol_for(token_out_raw, dst)

    def _decimals_for(addr: str, default: int = 18) -> int:
        chain_tokens = TOKENS_BY_CHAIN.get(chain_id, POPULAR_TOKENS)
        for info in chain_tokens.values():
            if info.get("address", "").lower() == addr.lower():
                return int(info.get("decimals", default) or default)
        if addr.lower() == _ENSO_NATIVE_TOKEN:
            return 18
        return default

    in_decimals = _decimals_for(src)

    query: dict[str, Any] = {
        "chainId": chain_id,
        "fromAddress": from_addr,
        "amountIn": amount,
        "tokenIn": src,
        "tokenOut": dst,
        "slippage": slippage_bps,
    }

    url = f"{_ENSO_BASE_URL}/api/v1/shortcuts/route"

    try:
        resp = httpx.get(url, params=query, headers=_enso_headers(), timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        return json.dumps({
            "status": "error",
            "message": f"Enso API {exc.response.status_code}: {exc.response.text[:300]}",
        })
    except Exception as exc:
        logger.warning("build_swap_tx / Enso error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})

    raw_tx: dict[str, Any] = data if isinstance(data, dict) else {}
    tx_obj = raw_tx.get("tx") or raw_tx

    raw_value = tx_obj.get("value", "0x0")
    if isinstance(raw_value, str) and raw_value.isdigit():
        tx_value = hex(int(raw_value))
    elif isinstance(raw_value, int):
        tx_value = hex(raw_value)
    else:
        tx_value = raw_value or "0x0"

    # Calculate display amounts
    try:
        amount_in_display = int(amount) / (10 ** in_decimals)
    except (ValueError, TypeError):
        amount_in_display = 0

    dst_amount_raw = raw_tx.get("amountOut", "0")
    out_decimals = _decimals_for(dst)
    try:
        dst_amount_display = int(dst_amount_raw) / (10 ** out_decimals)
    except (ValueError, TypeError):
        dst_amount_display = 0

    # Calculate price impact (cap at 15% — anything higher is likely a data issue)
    price_impact = 0.0
    if amount_in_display > 0 and dst_amount_display > 0:
        in_price = _get_price_usd(from_symbol)
        out_price = _get_price_usd(to_symbol)
        if in_price > 0 and out_price > 0:
            expected_out = (amount_in_display * in_price) / out_price
            if expected_out > 0:
                price_impact = abs(1 - dst_amount_display / expected_out) * 100
                if price_impact > 15:
                    # Likely wrong decimals or missing amountOut — show conservative estimate
                    price_impact = 0.5

    action = params.get("action", "swap")

    result: dict[str, Any] = {
        "status": "ok",
        "type": "evm_action_proposal",
        "chain_type": "evm",
        "chain_id": chain_id,
        "action": action,
        "from_token_symbol": from_symbol,
        "to_token_symbol": to_symbol,
        "amount_in_display": round(amount_in_display, 8),
        "dst_amount_display": round(dst_amount_display, 6),
        "route_summary": "Enso Aggregator",
        "price_impact_pct": round(price_impact, 2),
        "platform_fee_bps": PLATFORM_FEE_BPS,
        "tx": {
            "from": tx_obj.get("from", from_addr),
            "to": tx_obj.get("to", ""),
            "data": tx_obj.get("data", ""),
            "value": tx_value,
        },
        "approval_tx": None,
    }
    if tx_obj.get("gas"):
        result["tx"]["gas"] = tx_obj["gas"]
    return json.dumps(result)


def _build_jupiter_swap_tx(params: dict[str, Any]) -> str:
    """
    Calls Jupiter Aggregator v6 (quote → swap) to build a ready-to-sign
    Solana transaction with platform fee.

    Required keys in `params`: token_in (inputMint), token_out (outputMint),
                                amount (in base units), from (userPublicKey)
    Optional keys:  slippage_bps (default 50)
    """
    input_mint = params.get("token_in", "")
    output_mint = params.get("token_out", "")
    amount = params.get("amount", "")
    user_pubkey = params.get("from", "")
    slippage_bps = int(params.get("slippage_bps", 50))
    fee_account = _jupiter_fee_account()

    if not (input_mint and output_mint and amount and user_pubkey):
        return json.dumps(
            {
                "status": "error",
                "message": "token_in, token_out, amount and from (Solana pubkey) are required",
            }
        )

    # --- Step 1: Quote ---
    quote_params: dict[str, Any] = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": int(amount),
        "slippageBps": slippage_bps,
        "platformFeeBps": _PLATFORM_FEE_BPS,
    }

    try:
        quote_resp = httpx.get(
            "https://public.jupiterapi.com/quote",
            params=quote_params,
            timeout=10,
        )
        quote_resp.raise_for_status()
        quote_data: dict[str, Any] = quote_resp.json()
    except httpx.HTTPStatusError as exc:
        return json.dumps(
            {
                "status": "error",
                "message": f"Jupiter quote error {exc.response.status_code}: {exc.response.text[:300]}",
            }
        )
    except Exception as exc:
        logger.warning("build_swap_tx / Jupiter quote error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})

    # --- Step 2: Serialised swap transaction ---
    swap_body: dict[str, Any] = {
        "quoteResponse": quote_data,
        "userPublicKey": user_pubkey,
        "wrapAndUnwrapSol": True,   # handle native SOL transparently
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
    }
    # feeAccount must be an existing ATA for outputMint owned by the platform
    if fee_account:
        swap_body["feeAccount"] = fee_account

    try:
        swap_resp = httpx.post(
            "https://public.jupiterapi.com/swap",
            json=swap_body,
            timeout=15,
        )
        swap_resp.raise_for_status()
        swap_data: dict[str, Any] = swap_resp.json()
    except httpx.HTTPStatusError as exc:
        return json.dumps(
            {
                "status": "error",
                "message": f"Jupiter swap error {exc.response.status_code}: {exc.response.text[:300]}",
            }
        )
    except Exception as exc:
        logger.warning("build_swap_tx / Jupiter swap error: %s", exc)
        return json.dumps({"status": "error", "message": str(exc)})

    result: dict[str, Any] = {
        "status": "ok",
        "chain_type": "solana",
        "out_amount": quote_data.get("outAmount"),
        # minimum received after slippage — use for UI display
        "out_amount_min": quote_data.get("otherAmountThreshold"),
        "price_impact_pct": quote_data.get("priceImpactPct"),
        "platform_fee_bps": _PLATFORM_FEE_BPS,
        "fee_account": fee_account,
        # tx.serialized is a base64 VersionedTransaction ready for
        # signTransaction / sendRawTransaction via a Solana wallet adapter
        "tx": {
            "serialized": swap_data.get("swapTransaction"),
            "last_valid_block_height": swap_data.get("lastValidBlockHeight"),
        },
    }
    return json.dumps(result)


def _build_swap_tx(raw_input: str, user_address: str, chain_id: int, solana_address: str = "") -> str:
    """
    Dispatcher: routes to Enso (EVM) or Jupiter (Solana) based on `chain`.

    Input: JSON string with keys:
        chain        "evm" | "solana"  (default "evm")
        token_in     token address / mint
        token_out    token address / mint
        amount       amount in wei (EVM) or base units (Solana)
        from         sender wallet — omit to use the session user's address
        chain_id     EVM chain ID (default = session chain_id, ignored for Solana)
        slippage_bps slippage tolerance in basis points (default 100 EVM / 50 SOL)
    """
    try:
        params: dict[str, Any] = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        return json.dumps({"status": "error", "message": f"JSON parse error: {exc}"})

    chain = str(params.get("chain", "evm")).lower()
    if chain == "solana":
        if not params.get("from") and solana_address:
            params["from"] = str(solana_address).split(",")[0].strip()
        return _build_jupiter_swap_tx(params)
    return _build_enso_swap_tx(params, user_address, chain_id)


# ---------------------------------------------------------------------------
# build_transfer_transaction
# ---------------------------------------------------------------------------

def _is_native(symbol_lower: str, chain_id: int) -> bool:
    """Return True if the symbol is the native coin for the given chain."""
    native = _native_symbol(chain_id).lower()
    return symbol_lower in {native, "native"} or (symbol_lower == "sol" and chain_id == 0)


def _build_transfer_transaction(raw_input: str, chain_id: int = 56) -> str:
    """
    Builds a ready-to-sign transfer transaction (native coin or ERC-20).

    Automatically resolves contract address and decimals using the per-chain
    TOKENS_BY_CHAIN registry — no external calls needed.

    Input: JSON string with keys:
        token_symbol   required — e.g. "BNB", "USDT", "USDC"
        amount         required — float, e.g. 0.5
        to_address     required — recipient wallet address (0x…)
        token_address  optional — ERC-20 contract; auto-resolved for known tokens;
                       omit or set to "native" for BNB
        decimals       optional — auto-resolved for known tokens (default 18)
    """
    try:
        params: dict[str, Any] = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        return json.dumps({"status": "error", "message": f"JSON parse error: {exc}"})

    token_symbol: str = str(params.get("token_symbol", "")).strip()
    amount_raw = params.get("amount")
    to_address: str = str(params.get("to_address", "")).strip()
    token_address: Optional[str] = params.get("token_address")
    decimals: Optional[int] = params.get("decimals")

    if not to_address or amount_raw is None:
        return json.dumps(
            {"status": "error", "message": "to_address and amount are required"}
        )

    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return json.dumps({"status": "error", "message": "amount must be a number"})

    if amount <= 0:
        return json.dumps({"status": "error", "message": "amount must be greater than 0"})

    symbol_lower = token_symbol.lower()

    # Allow agent to override chain_id via JSON (e.g. AVAX → chain 43114)
    if "chain_id" in params:
        try:
            chain_id = int(params["chain_id"])
        except (TypeError, ValueError):
            pass

    # Auto-detect chain from unique native symbol (e.g. "avax" → 43114, "ftm" → 250)
    if symbol_lower in _NATIVE_SYMBOL_TO_CHAIN and chain_id not in _NATIVE_SYMBOL_TO_CHAIN.values():
        detected = _NATIVE_SYMBOL_TO_CHAIN[symbol_lower]
        if _native_symbol(detected).lower() == symbol_lower:
            chain_id = detected

    # Pick the right token registry for the resolved chain
    token_registry = TOKENS_BY_CHAIN.get(chain_id, {})
    chain_label = _chain_name(chain_id)

    # ── Auto-resolve from registry if token_address not provided ────────────
    if not token_address or str(token_address).lower() in ("native", ""):
        if _is_native(symbol_lower, chain_id):
            token_address = None  # native coin transfer
        elif symbol_lower in token_registry:
            entry = token_registry[symbol_lower]
            token_address = entry["address"]
            if decimals is None:
                decimals = entry["decimals"]
        else:
            # Check if the token exists on any other supported chain
            found_on = [_chain_name(cid) for cid, reg in TOKENS_BY_CHAIN.items() if symbol_lower in reg]
            if found_on:
                return json.dumps({
                    "status": "error",
                    "message": (
                        f"Token '{token_symbol}' is not available on {chain_label} (chain {chain_id}). "
                        f"It is supported on: {', '.join(found_on)}. "
                        "Switch the network in MetaMask or provide token_address + decimals manually."
                    ),
                })
            return json.dumps({
                "status": "error",
                "message": (
                    f"Unknown token '{token_symbol}' on {chain_label}. "
                    "Please provide token_address and decimals explicitly."
                ),
            })
    else:
        # token_address was explicitly provided — just normalise decimals
        if decimals is None:
            decimals = token_registry.get(symbol_lower, {}).get("decimals", 18)

    # ── Native coin transfer (BNB / ETH / MATIC …) ──────────────────────────
    if not token_address:
        wei_amount = hex(int(amount * (10 ** 18)))
        result: dict[str, Any] = {
            "status": "ok",
            "type": "transaction",
            "chain_id": chain_id,           # network where tx must be sent
            "token_symbol": token_symbol,
            "amount": amount,
            "to": to_address,               # recipient (native: directly to recipient)
            "ui_to": to_address,            # human-readable recipient for UI display
            "data": "0x",
            "value": wei_amount,
        }
        return json.dumps(result)

    # ── ERC-20 transfer: transfer(address,uint256) selector = 0xa9059cbb ────
    effective_decimals: int = decimals if decimals is not None else 18
    method_id = "a9059cbb"
    clean_to = to_address.replace("0x", "").lower().zfill(64)
    wei_amount_int = int(amount * (10 ** effective_decimals))
    hex_amount = hex(wei_amount_int).replace("0x", "").zfill(64)
    calldata = f"0x{method_id}{clean_to}{hex_amount}"

    result = {
        "status": "ok",
        "type": "transaction",
        "chain_id": chain_id,           # network where tx must be sent
        "token_symbol": token_symbol,
        "amount": amount,
        "to": token_address,            # ERC-20 contract address (call target)
        "ui_to": to_address,            # human-readable recipient for UI display
        "data": calldata,               # encoded transfer(to, amount)
        "value": "0x0",
    }
    return json.dumps(result)


# ---------------------------------------------------------------------------
# System prompt — dynamic, includes chain context
# ---------------------------------------------------------------------------

def _build_system_prompt(chain_id: int, user_address: str = "", solana_address: str = "") -> str:
    """Return a system prompt tailored to the user's current network."""
    chain_label = _chain_name(chain_id)
    native = _native_symbol(chain_id)

    wallet_line = (
        f"Connected EVM wallet: {user_address}"
        if user_address
        else "Connected EVM wallet: none"
    )
    solana_line = (
        f"Connected Solana wallet (Phantom): {solana_address}"
        if solana_address
        else ""
    )
    if user_address and solana_address:
        my_balance_line = f'  - "my balance" or "all chains" → input: "{solana_address},{user_address}"'
    elif user_address:
        my_balance_line = f'  - "my balance" or "all chains" (EVM) → input: "{user_address}"'
    else:
        my_balance_line = f'  - "my balance" → input: "{solana_address}" (Solana-only wallet, use Solana address directly)'

    return f"""\
You are a Senior DeFi Advisor — an expert in crypto, DeFi protocols, and Web3. \
You are both a smart conversationalist and a precise technical executor. \
You respond in English by default. Only switch to another language if the user clearly asks in that language.

Active network: {chain_label} (chain ID {chain_id}). Native coin: {native}.
{wallet_line}
{solana_line}

━━━ YOUR TOOLS ━━━

Choose tools based on intent — you are an intelligent advisor, not a router. Chain tools when needed.

• get_wallet_balance — Check wallet token balances.{my_balance_line}
  To check a specific chain: input "{user_address or solana_address}|<chain>"
  Chain keywords: eth, bnb, polygon, arbitrum, optimism, base, avalanche, zksync,
  linea, scroll, mantle, fantom, gnosis, celo, cronos, solana
  NEVER call this before a swap — build_swap_tx handles balance lookup automatically.

• get_token_price — Current USD price of any token. Input: symbol like "BNB" or "bitcoin".

• get_defi_market_overview — Macro DeFi market data (TVL, top chains). Input: empty string.

• get_defi_analytics — USE THIS for ANY question about APY, APR, yield, best pools, or earning.
  Searches DefiLlama for yield-bearing pools. Returns APY, TVL, volume, fee tier when available, and protocol links.
  Input: token symbol(s), chain, protocol. Add "sort:apr" for highest APR, "sort:apy" for highest APY.
  Examples: "USDC polygon", "SOL solana sort:apy", "USDT USDC sort:apr".
  CRITICAL: If user asks "highest APR pool for X/Y" → use "sort:apr".
  If user asks "highest APY", "best yield", or "where to earn on X" → use "sort:apy".
  Do NOT use this for native staking protocol links like "where can I stake BNB".
  IMPORTANT: Do NOT add a chain filter unless the user explicitly names a chain.
  IMPORTANT: Never invent pool names, APRs, fee tiers, or addresses. Only repeat values returned by the tool.
  Prefer supported EVM/Solana chains unless the user explicitly asks for all chains or a specific unsupported chain.

• search_dexscreener_pairs — Search any token or pair on DexScreener. Best for meme coins,
  newly launched tokens, and contract address lookups. Returns price, liquidity, volume.

• find_liquidity_pool — USE THIS only to find a specific pool's CONTRACT ADDRESS for trading.
  NOT for yield/APR queries. Use when user asks "what is the pool address for X/Y" or
  "find the WBNB/CAKE pool on BSC". Input: JSON with "query" and optional "chain_id".

• build_swap_tx — Build an EVM swap transaction via Enso. Use for all EVM swaps.
  Enso is a DEX aggregator that automatically finds the cheapest route across 100+ DEXs.
  When user asks about "lowest fees" or "cheapest swap" — Enso already optimizes this.
  Input: JSON with chain, token_in, token_out, amount ("all" for full balance), chain_id.
  Example: {{{{"chain":"evm","token_in":"BNB","token_out":"USDT","amount":"all","chain_id":56}}}}
  When user says "swap all X" or "swap my X": set amount="all" — do NOT check balance first.
  If token is unknown: first use search_dexscreener_pairs to find its contract address,
  then use that address as token_in in build_swap_tx.

• build_solana_swap — Build a Solana swap via Jupiter. Use when a Solana wallet is connected.
  Input: JSON with sell_token, buy_token, sell_amount (lamports), user_pubkey.

• build_stake_tx — Stake tokens to earn yield (ETH→stETH, BNB→stkBNB, etc).
  Input: JSON with token, protocol (optional), amount ("all" or wei), chain_id.
  Example: {{{{"token":"ETH","protocol":"lido","amount":"all","chain_id":1}}}}
  Supported: ETH (Lido, Rocket Pool, Coinbase, Frax), BNB (Binance, Ankr), MATIC (Lido).
  IMPORTANT: Native staking uses the token's native chain automatically: ETH→1, BNB→56, MATIC→137.

• get_staking_options — Use this for informational staking questions and direct protocol links.
  Examples: "where can I stake BNB", "give me a staking link for ETH", "what staking protocols do you support".
  Returns direct staking protocol links. Do NOT use get_defi_analytics for these native staking-link questions.

• build_deposit_lp_tx — Add liquidity to a pool. Requires pool_address from find_liquidity_pool.
  Steps: 1) Use find_liquidity_pool to get pool address, 2) Call this tool with the address.
  Input: JSON with token_in, pool_address, amount, chain_id.
  Example: {{{{"token_in":"USDC","pool_address":"0xABC...","amount":"5000000","chain_id":1}}}}

• build_bridge_tx — Bridge tokens between chains via deBridge DLN.
  Input: JSON with token_in, amount, src_chain_id, dst_chain_id, token_out (optional).
  Chain IDs: Ethereum=1, BSC=56, Polygon=137, Arbitrum=42161, Base=8453, Optimism=10, Solana=7565164.
  For Phantom/Solana bridge requests, use Solana as the source chain when the user is bridging SOL.
  Example: {{{{"token_in":"USDC","amount":"5000000","src_chain_id":1,"dst_chain_id":42161}}}}

• build_transfer_tx — Build a token transfer/send transaction.
  Input: JSON with token_symbol, amount, to_address, chain_id.

━━━ MULTI-STEP REASONING ━━━

When one tool call isn't enough, chain them. Examples:
- Unknown memecoin swap: search_dexscreener_pairs → get contract address → build_swap_tx with that address
- Swap error: if build_swap_tx returns an error, explain what went wrong and suggest alternatives
- APR/APY pool search: ALWAYS use get_defi_analytics (sort:apr for APR, sort:apy for APY), never find_liquidity_pool
- Pool address lookup: use find_liquidity_pool only when user needs a contract address, not yield data
- Add liquidity: find_liquidity_pool → get pool_address → build_deposit_lp_tx with that address
- Informational staking / staking links: use get_staking_options
- Staking transaction: directly call build_stake_tx (no need to find anything first)
- Bridging: directly call build_bridge_tx with source and destination chain IDs

IMPORTANT: For greetings and casual conversation, respond directly without calling any tool.

━━━ ACTIONS YOU CANNOT PERFORM ━━━
You do NOT have tools to:
- Unstake tokens (withdraw from staking — only staking IN is supported)
- Remove liquidity from a pool (only depositing IN is supported)
- Claim rewards or harvest yield
- Deploy contracts or interact with arbitrary contracts

When the user asks for any of these, IMMEDIATELY respond with a helpful explanation:
1. Acknowledge exactly what they want to do
2. Explain that this action is not available yet in your toolkit
3. Suggest what you CAN do instead (e.g. "I can find the best pool and give you the direct link to add liquidity on the protocol's website")
NEVER loop trying different tools when the action is not supported — answer directly.

━━━ RESPONSE FORMAT RULES (CRITICAL) ━━━

A. TRANSACTIONS (build_solana_swap / build_swap_tx / build_transfer_tx / build_stake_tx / build_deposit_lp_tx / build_bridge_tx):
   If the tool returns JSON with "status":"ok", copy the ENTIRE JSON object verbatim as your Final Answer.
   No markdown, no text before or after — just the raw JSON.
   Example: Final Answer: {{{{"type":"solana_swap_proposal","swapTransaction":"...",...}}}}
   If the tool returns an error (status:"error"), explain the issue in plain text and suggest alternatives
   (e.g. search DexScreener for the token address, try a different chain, ask user to confirm the symbol).

B. LISTS WITH DATA (search_dexscreener_pairs, find_liquidity_pool, get_defi_analytics — any list of entities):
   You MUST return a JSON object with type "universal_cards". Never use Markdown lists!
   Exact format (escape quotes inside strings):
   Final Answer: {{{{"type":"universal_cards","message":"Short message for the user","cards":[{{{{"title":"TOKEN/SOL","subtitle":"Raydium · Solana","details":{{{{"Price":"$0.01","Liquidity":"$50,000","Volume 24h":"$120,000"}}}},"url":"https://dexscreener.com/...","button_text":"Trade"}}}}]}}}}

C. SIMPLE QUESTIONS & ANALYTICS (no lists of entities):
   Final Answer is plain text in English by default. Use another language only if the user clearly writes in that language. You may use **bold** and emoji.

━━━ GENERAL RULES ━━━
- Never give personalized financial investment advice.
- Always include units ({native}, USDT, etc.) with numeric values.
- Be empathetic, professional, and engaging — like an experienced crypto-native advisor.
- For greetings and casual messages, NEVER call any tool. Respond conversationally and warmly.
- If no tool is needed, answer immediately with Final Answer.
- When using tools, Action must be exactly the tool name and Action Input must contain only the
  raw string or JSON payload. Never use function-call syntax like tool("x") or similar wrappers.
- CRITICAL: Never output raw ReAct format (Question:/Thought:/Action:/Action Input:) in your
  Final Answer. The Final Answer must always be clean, readable text or valid JSON — never
  the internal reasoning trace.
- CRITICAL JSON PASSTHROUGH: When a tool returns JSON with a "type" field (like "balance_report", \
  "universal_cards", "evm_action_proposal", "bridge_proposal", "liquidity_pool_report", "solana_swap_proposal"), \
  and the user's request is fully answered by that JSON, you MUST copy the ENTIRE JSON object \
  exactly as-is into your Final Answer. Do NOT summarize it into text — the frontend renders \
  these JSON types as visual cards. Rewriting them as text BREAKS the UI.
- CRITICAL: If no tool returned a pool or APR figure, say you could not verify it. Never guess missing data.

Conversation so far:
{{chat_history}}"""


# ---------------------------------------------------------------------------
# Step 3.5 — DeFi analytics via DefiLlama (no API key required)
# ---------------------------------------------------------------------------

_CHAIN_ALIASES_LLAMA: dict[str, str] = {
    "bnb": "bsc", "bsc": "bsc", "bnbchain": "bsc",
    "eth": "ethereum", "ethereum": "ethereum",
    "polygon": "polygon", "matic": "polygon",
    "arbitrum": "arbitrum", "arb": "arbitrum",
    "optimism": "optimism", "op": "optimism",
    "base": "base",
    "avalanche": "avalanche", "avax": "avalanche",
    "solana": "solana", "sol": "solana",
    "fantom": "fantom", "ftm": "fantom",
    "gnosis": "gnosis",
}

_STAKING_NATIVE_CHAIN: Final[dict[str, int]] = {
    "ETH": 1,
    "BNB": 56,
    "MATIC": 137,
}

_STAKING_PROTOCOL_URLS: Final[dict[tuple[int, str, str], str]] = {
    (1, "ETH", "lido"): "https://stake.lido.fi/",
    (1, "ETH", "rocketpool"): "https://stake.rocketpool.net/",
    (1, "ETH", "coinbase"): "https://www.coinbase.com/staking",
    (1, "ETH", "frax"): "https://app.frax.finance/",
    (1, "ETH", "mantle"): "https://www.mantle.xyz/staking",
    (56, "BNB", "binance"): "https://www.binance.com/en/staked-bnb",
    (56, "BNB", "ankr"): "https://www.ankr.com/staking/stake/bnb/",
    (137, "MATIC", "lido"): "https://polygon.lido.fi/",
}

_CHAIN_LABELS: Final[dict[int, str]] = {
    1: "Ethereum",
    10: "Optimism",
    56: "BNB Chain",
    137: "Polygon",
    8453: "Base",
    42161: "Arbitrum",
    43114: "Avalanche",
    59144: "Linea",
    250: "Fantom",
    100: "Gnosis",
    324: "zkSync Era",
    5000: "Mantle",
    25: "Cronos",
}

_DEBRIDGE_SOLANA_CHAIN_ID: Final[int] = 7_565_164
_APP_SOLANA_CHAIN_IDS: Final[set[int]] = {0, 101, _DEBRIDGE_SOLANA_CHAIN_ID}
_DEBRIDGE_CHAIN_IDS: dict[int, int] = {
    1: 1,
    10: 10,
    56: 56,
    100: 100000002,
    137: 137,
    250: 250,
    324: 324,
    8453: 8453,
    42161: 42161,
    43114: 43114,
    59144: 59144,
    _DEBRIDGE_SOLANA_CHAIN_ID: _DEBRIDGE_SOLANA_CHAIN_ID,
}

_DEBRIDGE_NATIVE: dict[int, str] = {
    1: "0x0000000000000000000000000000000000000000",
    10: "0x0000000000000000000000000000000000000000",
    56: "0x0000000000000000000000000000000000000000",
    100: "0x0000000000000000000000000000000000000000",
    137: "0x0000000000000000000000000000000000000000",
    250: "0x0000000000000000000000000000000000000000",
    324: "0x0000000000000000000000000000000000000000",
    8453: "0x0000000000000000000000000000000000000000",
    42161: "0x0000000000000000000000000000000000000000",
    43114: "0x0000000000000000000000000000000000000000",
    59144: "0x0000000000000000000000000000000000000000",
    _DEBRIDGE_SOLANA_CHAIN_ID: "11111111111111111111111111111111",
}

_SOL_BRIDGE_TOKEN_DECIMALS: Final[dict[str, int]] = {
    "11111111111111111111111111111111": 9,
    "So11111111111111111111111111111111111111112": 9,
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": 9,
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": 9,
}

_BRIDGE_CHAIN_ALIAS_TO_ID: Final[dict[str, int]] = {
    "ethereum": 1,
    "eth": 1,
    "mainnet": 1,
    "eth chain": 1,
    "bsc": 56,
    "bnb": 56,
    "bnb chain": 56,
    "binance smart chain": 56,
    "polygon": 137,
    "matic": 137,
    "arbitrum": 42161,
    "arb": 42161,
    "optimism": 10,
    "op": 10,
    "base": 8453,
    "avalanche": 43114,
    "avax": 43114,
    "solana": 101,
    "sol": 101,
    "solana chain": 101,
    "sol chain": 101,
}


def _coerce_bridge_chain_id(value: Any, *, default: int = 0) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if not cleaned:
            return default
        if cleaned.isdigit():
            return int(cleaned)
        return _BRIDGE_CHAIN_ALIAS_TO_ID.get(cleaned, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_staking_chain(token: str, chain_id: int) -> int:
    token_upper = (token or "").strip().upper()
    native_chain = _STAKING_NATIVE_CHAIN.get(token_upper)
    if native_chain is None:
        return chain_id
    if (chain_id, token_upper) in _DEFAULT_STAKING:
        return chain_id
    return native_chain


def _staking_cards_for_token(token: str) -> list[dict[str, Any]]:
    token_upper = (token or "").strip().upper()
    cards: list[dict[str, Any]] = []

    for (chain_id, asset, protocol), info in _STAKING_PROTOCOLS.items():
        if token_upper and asset != token_upper:
            continue
        url = _STAKING_PROTOCOL_URLS.get((chain_id, asset, protocol), "")
        details = {
            "Asset": asset,
            "Chain": _CHAIN_LABELS.get(chain_id, f"Chain {chain_id}"),
            "Receipt Token": info["name"],
        }
        if (chain_id, asset) in _DEFAULT_STAKING and _DEFAULT_STAKING[(chain_id, asset)] == protocol:
            details["Default"] = "Yes"
        cards.append({
            "title": f"Stake {asset} on {_format_protocol_name(protocol)}",
            "subtitle": f"{_format_protocol_name(protocol)} · {_CHAIN_LABELS.get(chain_id, f'Chain {chain_id}')}",
            "details": details,
            "url": url,
            "button_text": "Open Protocol",
        })

    return cards


def get_staking_options(query: str = "") -> str:
    q = (query or "").strip()
    upper = q.upper()
    token = ""
    for candidate in _STAKING_NATIVE_CHAIN:
        if re.search(rf"\b{re.escape(candidate)}\b", upper):
            token = candidate
            break

    cards = _staking_cards_for_token(token)
    if not cards:
        supported = ", ".join(sorted(_STAKING_NATIVE_CHAIN.keys()))
        return f"Supported staking assets right now: {supported}."

    if token:
        message = f"Here are the supported staking protocols for {token}, with direct protocol links."
    else:
        message = "Here are the supported native staking protocols, with direct protocol links."

    return json.dumps({
        "type": "universal_cards",
        "message": message,
        "cards": cards,
    })


def _split_connected_wallets(user_address: str = "", solana_address: str = "") -> tuple[str, str]:
    evm_wallet = ""
    sol_wallet = ""
    for raw in (user_address or "", solana_address or ""):
        for part in [p.strip() for p in str(raw).split(",") if p.strip()]:
            if part.startswith("0x") and len(part) == 42 and not evm_wallet:
                evm_wallet = part
            elif not part.startswith("0x") and len(part) >= 32 and not sol_wallet:
                sol_wallet = part
    return evm_wallet, sol_wallet


def _normalize_bridge_chain_id(chain_id: int, *, token_in: str = "", solana_wallet: str = "") -> int:
    if chain_id in _APP_SOLANA_CHAIN_IDS:
        return _DEBRIDGE_SOLANA_CHAIN_ID
    token_lower = (token_in or "").strip().lower()
    if solana_wallet and token_lower in {"sol", "native"}:
        return _DEBRIDGE_SOLANA_CHAIN_ID
    return chain_id


def _bridge_chain_label(chain_id: int) -> str:
    if chain_id == _DEBRIDGE_SOLANA_CHAIN_ID:
        return "Solana"
    return _CHAIN_META.get(chain_id, {}).get("name", _CHAIN_LABELS.get(chain_id, f"Chain {chain_id}"))


def _resolve_bridge_token_metadata(token_symbol: str, chain_id: int, wallet_addr: str = "") -> tuple[str, int, str]:
    token = (token_symbol or "").strip()
    if chain_id == _DEBRIDGE_SOLANA_CHAIN_ID:
        if token.lower() in {"sol", "native"}:
            return _DEBRIDGE_NATIVE[_DEBRIDGE_SOLANA_CHAIN_ID], 9, "SOL"
        mint = _resolve_sol_mint(token)
        decimals = _SOL_BRIDGE_TOKEN_DECIMALS.get(mint, 9)
        symbol = token.upper() if token and not token.startswith("So111") else "SOL"
        return mint, decimals, symbol

    addr, decimals, _ = _resolve_token_metadata(token, chain_id, wallet_addr)
    if addr.lower() == _ENSO_NATIVE_TOKEN.lower():
        native_symbol = _native_symbol(chain_id).upper()
        return _DEBRIDGE_NATIVE.get(chain_id, _DEBRIDGE_NATIVE[1]), 18, native_symbol
    return addr, int(decimals or 18), token.upper()


def _bridge_default_output_token(token_in: str, src_chain: int, dst_chain: int) -> str:
    token_upper = (token_in or "").strip().upper()
    src_native = "SOL" if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID else _native_symbol(src_chain).upper()
    if token_upper in {"NATIVE", src_native}:
        if dst_chain == _DEBRIDGE_SOLANA_CHAIN_ID:
            return "SOL"
        return _native_symbol(dst_chain).upper()
    return token_upper


def _build_stake_tx(raw: str, user_address: str, default_chain_id: int) -> str:
    """
    Build a staking transaction via Enso routing.
    Staking = swap tokenIn for receipt token (e.g. ETH -> stETH via Lido).
    Input JSON keys: token (str), protocol (str, optional), amount (str in wei or "all"), chain_id (int, optional).
    """
    try:
        params = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return json.dumps({"status": "error", "message": f"Invalid JSON input: {raw}"})

    token = params.get("token", "").strip().upper()
    protocol = params.get("protocol", "").strip().lower()
    amount = str(params.get("amount", "all"))
    chain_id = _resolve_staking_chain(token, int(params.get("chain_id", default_chain_id)))

    if not token:
        return json.dumps({"status": "error", "message": "Missing 'token' field. Example: {\"token\": \"ETH\", \"protocol\": \"lido\", \"amount\": \"all\"}"})

    # If no protocol specified, use the default for this chain+token
    if not protocol:
        protocol = _DEFAULT_STAKING.get((chain_id, token), "")
    if not protocol:
        available = [f"{p} ({info['name']})" for (c, t, p), info in _STAKING_PROTOCOLS.items() if c == chain_id and t == token]
        if available:
            return json.dumps({"status": "error", "message": f"Please specify a staking protocol for {token}. Available: {', '.join(available)}"})
        return json.dumps({"status": "error", "message": f"No staking protocols available for {token} on chain {chain_id}. Staking is supported for ETH (Lido, Rocket Pool), BNB (Binance), MATIC (Lido)."})

    # Look up the receipt token
    key = (chain_id, token, protocol)
    staking_info = _STAKING_PROTOCOLS.get(key)
    if not staking_info:
        return json.dumps({"status": "error", "message": f"Staking protocol '{protocol}' not found for {token} on chain {chain_id}."})

    receipt_token = staking_info["receipt"]
    protocol_name = staking_info["name"]

    # Route through Enso: tokenIn -> receiptToken (Enso handles the staking contract interaction)
    swap_params = {
        "token_in": token,
        "token_out": receipt_token,
        "amount": amount,
        "chain_id": chain_id,
        "action": "stake",
    }
    result_json = _build_enso_swap_tx(swap_params, user_address, chain_id)

    # Update the response to show staking context instead of swap context
    try:
        result = json.loads(result_json)
        if result.get("status") == "ok":
            result["action"] = "stake"
            result["to_token_symbol"] = protocol_name
            result["route_summary"] = f"Stake via {protocol_name}"
            result["protocol_url"] = _STAKING_PROTOCOL_URLS.get(key, "")
        return json.dumps(result)
    except json.JSONDecodeError:
        return result_json


def _build_deposit_lp_tx(raw: str, user_address: str, default_chain_id: int) -> str:
    """
    Build a liquidity deposit transaction via Enso routing.
    Enso routes tokenIn -> LP token address (handles splitting, approval, and deposit).
    Input JSON keys: token_in (str), pool_address (str - LP token/pool contract), amount (str in wei or "all"), chain_id (int, optional).
    """
    try:
        params = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return json.dumps({"status": "error", "message": f"Invalid JSON input: {raw}"})

    token_in = params.get("token_in", "").strip()
    pool_address = params.get("pool_address", "").strip()
    amount = str(params.get("amount", ""))
    requested_amount_raw = amount
    chain_id = int(params.get("chain_id", default_chain_id))
    protocol_name = params.get("protocol", "Liquidity Pool")

    if not token_in:
        return json.dumps({"status": "error", "message": "Missing 'token_in' field. Specify which token to deposit."})
    if not pool_address:
        return json.dumps({"status": "error", "message": "Missing 'pool_address' field. Use find_liquidity_pool to get the pool address first."})
    if not (pool_address.startswith("0x") and len(pool_address) == 42):
        return json.dumps({"status": "error", "message": f"Invalid pool address: '{pool_address}'. Must be a 0x-prefixed EVM address (42 chars)."})

    # Route through Enso: tokenIn -> pool/LP token (Enso handles split + deposit)
    swap_params = {
        "token_in": token_in,
        "token_out": pool_address,
        "amount": amount if amount else "all",
        "chain_id": chain_id,
        "action": "deposit",
    }
    result_json = _build_enso_swap_tx(swap_params, user_address, chain_id)

    # Update the response to show deposit context
    try:
        result = json.loads(result_json)
        if result.get("status") == "ok":
            result["action"] = "deposit"
            result["route_summary"] = f"Deposit into {protocol_name} via Enso"
        return json.dumps(result)
    except json.JSONDecodeError:
        return result_json


# ---------------------------------------------------------------------------
# deBridge DLN bridging
# ---------------------------------------------------------------------------


def _build_bridge_tx(raw: str, user_address: str, default_chain_id: int, solana_address: str = "") -> str:
    """
    Build a cross-chain bridge transaction via deBridge DLN API.
    Input JSON keys: token_in (str), amount (str in wei), src_chain_id (int),
                     dst_chain_id (int), recipient (str, optional - defaults to user_address).
    """
    try:
        params = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return json.dumps({"status": "error", "message": f"Invalid JSON input: {raw}"})

    evm_wallet, sol_wallet = _split_connected_wallets(user_address, solana_address)
    token_in = params.get("token_in", "").strip()
    token_out = params.get("token_out", "").strip()
    amount = str(params.get("amount", ""))
    requested_amount_raw = amount
    src_chain = _normalize_bridge_chain_id(
        _coerce_bridge_chain_id(params.get("src_chain_id"), default=default_chain_id),
        token_in=token_in,
        solana_wallet=sol_wallet,
    )
    dst_chain = _normalize_bridge_chain_id(_coerce_bridge_chain_id(params.get("dst_chain_id"), default=0))
    sender = sol_wallet if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID else evm_wallet
    if not sender:
        sender = user_address.strip() if src_chain != _DEBRIDGE_SOLANA_CHAIN_ID else sol_wallet
    recipient = params.get("recipient", "").strip()
    if not recipient:
        recipient = sol_wallet if dst_chain == _DEBRIDGE_SOLANA_CHAIN_ID else evm_wallet

    if not token_in:
        return json.dumps({"status": "error", "message": "Missing 'token_in'. Specify the token to bridge."})
    if not amount or amount == "0":
        return json.dumps({"status": "error", "message": "Missing 'amount'. Specify amount in smallest units (wei)."})
    if not dst_chain:
        return json.dumps({"status": "error", "message": "Missing 'dst_chain_id'. Specify destination chain (e.g. 42161 for Arbitrum, 8453 for Base)."})
    if src_chain == dst_chain:
        return json.dumps({"status": "error", "message": "Source and destination chains are the same. Use build_swap_tx for same-chain operations."})
    if not sender:
        return json.dumps({"status": "error", "message": "No source wallet connected for this bridge. Connect the correct MetaMask or Phantom wallet first."})
    if not recipient:
        return json.dumps({"status": "error", "message": "No destination recipient is available for this bridge. Connect a wallet on the destination side or provide a recipient address explicitly."})

    if src_chain not in _DEBRIDGE_CHAIN_IDS or dst_chain not in _DEBRIDGE_CHAIN_IDS:
        return json.dumps({"status": "error", "message": f"deBridge does not support bridging between chain {src_chain} and chain {dst_chain}."})

    src_addr, src_decimals, src_symbol = _resolve_bridge_token_metadata(token_in, src_chain, sender)
    if not src_addr:
        return json.dumps({"status": "error", "message": f"Cannot resolve '{token_in}' on chain {src_chain}."})

    target_token = token_out or _bridge_default_output_token(src_symbol, src_chain, dst_chain)
    try:
        dst_addr, dst_decimals, dst_symbol = _resolve_bridge_token_metadata(target_token, dst_chain, recipient)
    except Exception:
        dst_addr = ""
        dst_decimals = 0
        dst_symbol = target_token.upper()

    if not dst_addr and target_token == (token_out or ""):
        return json.dumps({"status": "error", "message": f"Cannot resolve destination token '{target_token}' on chain {dst_chain}."})
    if not dst_addr:
        fallback_token = _bridge_default_output_token(token_in, src_chain, dst_chain)
        dst_addr, dst_decimals, dst_symbol = _resolve_bridge_token_metadata(fallback_token, dst_chain, recipient)
    if not dst_addr:
        return json.dumps({"status": "error", "message": f"Cannot resolve destination token '{target_token}' on chain {dst_chain}."})

    # Handle "all" amount
    if amount.lower().strip() in ("all", "max"):
        native_sym = "SOL" if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID else _CHAIN_META.get(src_chain, {}).get("native", "ETH").upper()
        is_native = src_symbol.upper() in ("NATIVE", native_sym)
        if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID and is_native:
            for rpc in _SOL_RPCS_AGENT:
                try:
                    r = _requests.post(
                        rpc,
                        json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [sender, {"commitment": "processed"}]},
                        timeout=5,
                    )
                    balance = int((((r.json() or {}).get("result") or {}).get("value")) or 0)
                    amount = str(max(0, balance - 5000))
                    break
                except Exception:
                    continue
        elif src_chain == _DEBRIDGE_SOLANA_CHAIN_ID:
            return json.dumps({"status": "error", "message": "Bridging the full balance is currently supported only for native SOL. Please enter an exact SPL token amount."})
        else:
            _chain_rpcs = {
                56: ["https://bsc-dataseed1.binance.org"],
                1: ["https://eth.llamarpc.com"],
                137: ["https://polygon-rpc.com"],
                43114: ["https://api.avax.network/ext/bc/C/rpc"],
                42161: ["https://arb1.arbitrum.io/rpc"],
                10: ["https://mainnet.optimism.io"],
                8453: ["https://mainnet.base.org"],
            }
            rpcs = _chain_rpcs.get(src_chain, [])
            if is_native:
                for rpc in rpcs:
                    try:
                        r = _requests.post(rpc, json={"jsonrpc": "2.0", "method": "eth_getBalance",
                                                       "params": [sender, "latest"], "id": 1}, timeout=5)
                        h = r.json().get("result", "0x0") or "0x0"
                        if h not in ("0x", "0x0"):
                            bal = int(h, 16)
                            gas_reserve = int(0.005 * 10**18)
                            amount = str(max(0, bal - gas_reserve))
                        break
                    except Exception:
                        continue
            else:
                balance_of_data = "0x70a08231" + "0" * 24 + sender[2:].lower()
                for rpc in rpcs:
                    try:
                        r = _requests.post(rpc, json={"jsonrpc": "2.0", "method": "eth_call",
                                                       "params": [{"to": src_addr, "data": balance_of_data}, "latest"], "id": 1}, timeout=5)
                        h = r.json().get("result", "0x0") or "0x0"
                        if h not in ("0x", "0x0", "0x" + "0" * 64):
                            amount = str(int(h, 16))
                        break
                    except Exception:
                        continue
        if not amount or amount == "0":
            return json.dumps({"status": "error", "message": f"No {token_in} balance found on chain {src_chain}."})

    if "." in amount:
        try:
            amount = str(int(float(amount) * (10 ** int(src_decimals or 18))))
        except Exception:
            return json.dumps({"status": "error", "message": "Bridge amount must be in the token's smallest units, or use 'all'."})

    # Call deBridge DLN API -> create-tx endpoint
    referral_code = (settings.debridge_referral_code or "").strip()
    debridge_params: dict[str, Any] = {
        "srcChainId": _DEBRIDGE_CHAIN_IDS[src_chain],
        "srcChainTokenIn": src_addr,
        "srcChainTokenInAmount": amount,
        "dstChainId": _DEBRIDGE_CHAIN_IDS[dst_chain],
        "dstChainTokenOut": dst_addr,
        "dstChainTokenOutRecipient": recipient,
        "srcChainOrderAuthorityAddress": sender,
        "dstChainOrderAuthorityAddress": recipient,
        "prependOperatingExpenses": "true",
    }
    if sender:
        debridge_params["senderAddress"] = sender
    if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID:
        debridge_params["skipSolanaRecipientValidation"] = "true"
    if referral_code:
        debridge_params["referralCode"] = referral_code

    try:
        resp = _requests.get(
            "https://api.dln.trade/v1.0/dln/order/create-tx",
            params=debridge_params,
            timeout=15,
        )
        if resp.status_code != 200:
            error_detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
            return json.dumps({"status": "error", "message": f"deBridge API error: {error_detail}"})
        data = resp.json()
    except Exception as exc:
        return json.dumps({"status": "error", "message": f"deBridge API request failed: {exc}"})

    tx_data = data.get("tx", {})
    if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID:
        if not tx_data.get("data"):
            error_msg = data.get("error", data.get("message", "Unknown error from deBridge"))
            return json.dumps({"status": "error", "message": f"deBridge could not build bridge transaction: {error_msg}"})
    elif not tx_data.get("to"):
        error_msg = data.get("error", data.get("message", "Unknown error from deBridge"))
        return json.dumps({"status": "error", "message": f"deBridge could not build bridge transaction: {error_msg}"})

    estimation = data.get("estimation") or {}
    src_chain_name = _bridge_chain_label(src_chain)
    dst_chain_name = _bridge_chain_label(dst_chain)

    # Parse display amounts
    decimals = src_decimals or 18
    requested_amount_display = 0.0
    try:
        if requested_amount_raw.lower().strip() not in ("all", "max"):
            requested_amount_display = int(requested_amount_raw) / (10 ** decimals)
    except (ValueError, TypeError, AttributeError):
        requested_amount_display = 0.0

    src_chain_token_in = estimation.get("srcChainTokenIn") or {}
    src_chain_token_out = estimation.get("srcChainTokenOut") or {}
    dst_chain_token_out = estimation.get("dstChainTokenOut") or {}

    actual_src_amount_raw = str(src_chain_token_in.get("amount") or amount)
    actual_src_decimals = int(src_chain_token_in.get("decimals") or decimals or 18)
    try:
        amount_in_display = int(actual_src_amount_raw) / (10 ** actual_src_decimals)
    except (ValueError, TypeError):
        amount_in_display = 0

    dst_amount_raw = dst_chain_token_out.get("amount", "0")
    dst_decimals = int(dst_chain_token_out.get("decimals") or dst_decimals or src_decimals or 18)
    try:
        dst_amount_display = int(dst_amount_raw) / (10 ** dst_decimals)
    except (ValueError, TypeError):
        dst_amount_display = 0

    intermediary_symbol = str(src_chain_token_out.get("symbol") or "")
    intermediary_amount_display = 0.0
    intermediary_amount_raw = str(src_chain_token_out.get("amount") or "0")
    intermediary_decimals = int(src_chain_token_out.get("decimals") or 18)
    if intermediary_symbol and intermediary_amount_raw and intermediary_amount_raw != "0":
        try:
            intermediary_amount_display = int(intermediary_amount_raw) / (10 ** intermediary_decimals)
        except (ValueError, TypeError):
            intermediary_amount_display = 0.0

    warnings: list[str] = []
    if requested_amount_display and abs(amount_in_display - requested_amount_display) > (10 ** (-min(actual_src_decimals, 6))):
        warnings.append(
            f"Phantom will show the total source-chain spend ({amount_in_display:.6f} {src_symbol.upper()}) because deBridge prepends operating expenses. Your requested bridge amount is {requested_amount_display:.6f} {src_symbol.upper()}."
        )
    if intermediary_symbol and intermediary_symbol.upper() != src_symbol.upper():
        warnings.append(
            f"Phantom may show a temporary source-chain swap into {intermediary_symbol.upper()} before bridging. Final destination asset remains {dst_symbol.upper()} on {dst_chain_name}."
        )

    source_execution_summary = ""
    if intermediary_symbol and intermediary_amount_display:
        source_execution_summary = (
            f"{src_symbol.upper()} on {src_chain_name} is first converted into ~{intermediary_amount_display:.6f} {intermediary_symbol.upper()} before the cross-chain fill."
        )

    estimated_transaction_fee = data.get("estimatedTransactionFee") or {}
    fee_total_raw = str(estimated_transaction_fee.get("total") or "0")
    estimated_fee_display = "—"
    if fee_total_raw.isdigit():
        fee_decimals = 9 if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID else 18
        try:
            estimated_fee_display = f"~{int(fee_total_raw) / (10 ** fee_decimals):.6f} {src_symbol.upper()}"
        except (ValueError, TypeError):
            estimated_fee_display = "—"

    estimated_fill_time_seconds = int((data.get("order") or {}).get("approximateFulfillmentDelay") or 0)
    usd_price_impact = data.get("usdPriceImpact")

    # Build approval tx if deBridge requires token approval
    approval_tx = None
    allowance_target = tx_data.get("allowanceTarget") or tx_data.get("to", "")
    if src_chain != _DEBRIDGE_SOLANA_CHAIN_ID and src_addr != "0x0000000000000000000000000000000000000000" and allowance_target:
        # ERC-20: build approve(spender, maxUint256)
        max_uint = "f" * 64
        approve_data = "0x095ea7b3" + allowance_target.replace("0x", "").lower().zfill(64) + max_uint
        approval_tx = {
            "from": sender,
            "to": src_addr,
            "data": approve_data,
            "value": "0x0",
            "chain_id": src_chain,
        }

    if src_chain == _DEBRIDGE_SOLANA_CHAIN_ID:
        tx_hex = str(tx_data.get("data") or "")
        tx_hex = tx_hex[2:] if tx_hex.startswith("0x") else tx_hex
        try:
            tx_serialized = base64.b64encode(bytes.fromhex(tx_hex)).decode()
        except ValueError:
            tx_serialized = ""
        if not tx_serialized:
            return json.dumps({"status": "error", "message": "deBridge returned an invalid Solana transaction payload."})

        result = {
            "status": "ok",
            "type": "bridge_proposal",
            "chain_type": "solana",
            "src_chain_id": 101,
            "dst_chain_id": dst_chain,
            "src_chain_name": src_chain_name,
            "dst_chain_name": dst_chain_name,
            "action": "bridge",
            "from_token_symbol": src_symbol.upper(),
            "to_token_symbol": dst_symbol.upper(),
            "amount_in_display": round(amount_in_display, 8),
            "requested_amount_display": round(requested_amount_display, 8) if requested_amount_display else None,
            "dst_amount_display": round(dst_amount_display, 6),
            "route_summary": "deBridge DLN",
            "platform_fee_bps": 0,
            "order_id": data.get("orderId", ""),
            "estimated_fill_time_seconds": estimated_fill_time_seconds,
            "estimated_fee_display": estimated_fee_display,
            "usd_price_impact": usd_price_impact,
            "source_execution_symbol": intermediary_symbol.upper() if intermediary_symbol else "",
            "source_execution_amount_display": round(intermediary_amount_display, 6) if intermediary_amount_display else None,
            "source_execution_summary": source_execution_summary,
            "warnings": warnings,
            "tx": {
                "serialized": tx_serialized,
                "chain_id": 101,
            },
            "approval_tx": None,
        }
        return json.dumps(result)

    raw_value = tx_data.get("value", "0")
    if isinstance(raw_value, str) and raw_value.isdigit():
        tx_value = hex(int(raw_value))
    elif isinstance(raw_value, int):
        tx_value = hex(raw_value)
    else:
        tx_value = raw_value or "0x0"

    result = {
        "status": "ok",
        "type": "bridge_proposal",
        "chain_type": "evm",
        "src_chain_id": src_chain,
        "dst_chain_id": dst_chain,
        "src_chain_name": src_chain_name,
        "dst_chain_name": dst_chain_name,
        "action": "bridge",
        "from_token_symbol": src_symbol.upper(),
        "to_token_symbol": dst_symbol.upper(),
        "amount_in_display": round(amount_in_display, 8),
        "requested_amount_display": round(requested_amount_display, 8) if requested_amount_display else None,
        "dst_amount_display": round(dst_amount_display, 6),
        "route_summary": "deBridge DLN",
        "platform_fee_bps": 0,
        "order_id": data.get("orderId", ""),
        "estimated_fill_time_seconds": estimated_fill_time_seconds,
        "estimated_fee_display": estimated_fee_display,
        "usd_price_impact": usd_price_impact,
        "source_execution_symbol": intermediary_symbol.upper() if intermediary_symbol else "",
        "source_execution_amount_display": round(intermediary_amount_display, 6) if intermediary_amount_display else None,
        "source_execution_summary": source_execution_summary,
        "warnings": warnings,
        "tx": {
            "from": sender,
            "to": tx_data.get("to", ""),
            "data": tx_data.get("data", ""),
            "value": tx_value,
            "chain_id": src_chain,
        },
        "approval_tx": approval_tx,
    }
    return json.dumps(result)


def get_defi_market_overview(_: str = "") -> str:
    """
    Fetches a live macro overview of the DeFi market from DefiLlama:
    top blockchains by TVL, total market TVL, and dominance breakdown.
    Use this for general questions about the DeFi market state, trends, or outlook.
    No input required — pass an empty string or any value.
    """
    try:
        resp = _requests.get("https://api.llama.fi/v2/chains", timeout=12)
        if resp.status_code != 200:
            return f"DefiLlama API error: HTTP {resp.status_code}"

        chains: list[dict] = resp.json()
        chains.sort(key=lambda c: c.get("tvl") or 0, reverse=True)
        top = chains[:10]

        total_tvl = sum(c.get("tvl") or 0 for c in chains)
        top_tvl   = sum(c.get("tvl") or 0 for c in top)

        lines = [
            f"DeFi Market Overview (live data from DefiLlama):",
            f"Total DeFi TVL across all chains: ${total_tvl:,.0f}",
            f"",
            f"Top 10 blockchains by TVL:",
        ]
        for i, c in enumerate(top, 1):
            name   = c.get("name", "—")
            tvl    = c.get("tvl") or 0
            share  = tvl / total_tvl * 100 if total_tvl else 0
            lines.append(f"  {i}. {name}: ${tvl:,.0f} ({share:.1f}% dominance)")

        lines += [
            f"",
            f"Top 10 chains hold ${top_tvl:,.0f} ({top_tvl/total_tvl*100:.1f}% of total TVL).",
        ]
        return "\n".join(lines)

    except Exception as exc:
        return f"DefiLlama error: {exc}"


# ---------------------------------------------------------------------------
# Staking protocol registry: (chain_id, token_symbol, protocol) -> receipt token
# The receipt token is what the user gets back (e.g. stETH for staking ETH on Lido)
# Enso can route tokenIn -> receiptToken automatically via /shortcuts/route
# ---------------------------------------------------------------------------
_STAKING_PROTOCOLS: dict[tuple[int, str, str], dict[str, Any]] = {
    # Ethereum (chain_id=1)
    (1, "ETH", "lido"):       {"receipt": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84", "name": "Lido stETH", "decimals": 18},
    (1, "ETH", "rocketpool"):  {"receipt": "0xae78736Cd615f374D3085123A210448E74Fc6393", "name": "Rocket Pool rETH", "decimals": 18},
    (1, "ETH", "coinbase"):    {"receipt": "0xBe9895146f7AF43049ca1c1AE358B0541Ea49704", "name": "Coinbase cbETH", "decimals": 18},
    (1, "ETH", "frax"):        {"receipt": "0x5E8422345238F34275888049021821E8E08CAa1f", "name": "Frax sfrxETH", "decimals": 18},
    (1, "ETH", "mantle"):      {"receipt": "0xd5F7838F5C461fefF7FE49ea5ebaF7728bB0ADfa", "name": "Mantle mETH", "decimals": 18},
    # BNB Smart Chain (chain_id=56)
    (56, "BNB", "binance"):    {"receipt": "0x1bdd3Cf7F79cfB8EdbB955f20ad99211551BA275", "name": "Binance stkBNB", "decimals": 18},
    (56, "BNB", "ankr"):       {"receipt": "0x52F24a5e03aee338Da5fd9Df68D2b6FAe1178827", "name": "Ankr ankrBNB", "decimals": 18},
    # Polygon (chain_id=137)
    (137, "MATIC", "lido"):    {"receipt": "0x3A58a54C066FdC0f2D55FC9C89F0415C92eBf3C4", "name": "Lido stMATIC", "decimals": 18},
}

# Default staking protocol per token (used when user doesn't specify a protocol)
_DEFAULT_STAKING: dict[tuple[int, str], str] = {
    (1, "ETH"): "lido",
    (56, "BNB"): "binance",
    (137, "MATIC"): "lido",
}


_KNOWN_PROTOCOLS = {
    "uniswap", "pancakeswap", "aave", "curve", "compound", "sushiswap",
    "balancer", "raydium", "orca", "aerodrome", "camelot", "quickswap",
    "yearn", "beefy", "gmx", "morpho", "pendle", "lido", "rocket",
    "convex", "frax", "maker", "venus", "benqi", "trader", "meteora",
    "kamino", "drift", "mango", "ellipsis", "stargate", "synapse",
}

_SUPPORTED_YIELD_CHAINS: Final[set[str]] = {
    "ethereum", "bsc", "polygon", "arbitrum", "optimism", "base", "avalanche", "solana",
}

_TRUSTED_YIELD_PROTOCOLS: Final[tuple[str, ...]] = (
    "uniswap", "pancakeswap", "curve", "raydium", "orca", "aerodrome",
    "velodrome", "camelot", "quickswap", "sushiswap", "balancer",
    "trader", "joe", "lfj", "fluid", "meteora", "thena",
)

_UNISWAP_V3_FACTORY: Final[str] = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

_UNISWAP_V3_FACTORY_ABI: Final[list[dict[str, Any]]] = [{
    "inputs": [
        {"internalType": "address", "name": "tokenA", "type": "address"},
        {"internalType": "address", "name": "tokenB", "type": "address"},
        {"internalType": "uint24", "name": "fee", "type": "uint24"},
    ],
    "name": "getPool",
    "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
    "stateMutability": "view",
    "type": "function",
}]

_UNISWAP_V2_FACTORY: Final[str] = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"

_UNISWAP_V2_FACTORY_ABI: Final[list[dict[str, Any]]] = [{
    "inputs": [
        {"internalType": "address", "name": "tokenA", "type": "address"},
        {"internalType": "address", "name": "tokenB", "type": "address"},
    ],
    "name": "getPair",
    "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
    "stateMutability": "view",
    "type": "function",
}]

_UUID_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", re.I)

_POOL_EXPLORERS: Final[dict[str, str]] = {
    "bsc": "https://bscscan.com/address/{}",
    "ethereum": "https://etherscan.io/address/{}",
    "polygon": "https://polygonscan.com/address/{}",
    "arbitrum": "https://arbiscan.io/address/{}",
    "optimism": "https://optimistic.etherscan.io/address/{}",
    "base": "https://basescan.org/address/{}",
    "avalanche": "https://snowtrace.io/address/{}",
    "solana": "https://solscan.io/account/{}",
    "fantom": "https://ftmscan.com/address/{}",
    "cronos": "https://cronoscan.com/address/{}",
    "celo": "https://celoscan.io/address/{}",
}

_IGNORE_DEFI_QUERY_PARTS: Final[set[str]] = {
    "best", "top", "highest", "liquidity", "pool", "pools", "apr", "apy", "yield",
    "for", "on", "across", "cross-chain", "crosschain", "all", "chain", "chains",
    "find", "show", "give", "me", "the", "a", "an", "with", "return", "returns",
    "earn", "earning",
}

_POOL_TOKEN_EQUIVALENTS: Final[dict[str, set[str]]] = {
    "SOL": {"WSOL"},
    "WSOL": {"SOL"},
    "ETH": {"WETH"},
    "WETH": {"ETH"},
    "BNB": {"WBNB"},
    "WBNB": {"BNB"},
    "MATIC": {"WMATIC"},
    "WMATIC": {"MATIC"},
    "AVAX": {"WAVAX"},
    "WAVAX": {"AVAX"},
}


def _format_protocol_name(slug: str) -> str:
    parts = [part for part in re.split(r"[-_]", slug or "") if part]
    formatted: list[str] = []
    for part in parts:
        if part.lower() in {"v2", "v3", "v4", "amm", "cl"}:
            formatted.append(part.upper())
        else:
            formatted.append(part.capitalize())
    return " ".join(formatted) or "Unknown Protocol"


def _split_pool_symbol(symbol: str) -> list[str]:
    cleaned = (symbol or "").upper().replace(" POOL", "").replace(" LP", "")
    return [part.strip() for part in re.split(r"[-+/]", cleaned) if part.strip()]


def _pool_token_matches(filter_token: str, pool_tokens: list[str]) -> bool:
    aliases = {filter_token.upper()}
    aliases.update(_POOL_TOKEN_EQUIVALENTS.get(filter_token.upper(), set()))
    pool_token_set = {token.upper() for token in pool_tokens}
    return any(alias in pool_token_set for alias in aliases)


def _parse_defi_analytics_query(query: str) -> dict[str, Any]:
    query = (query or "").strip().strip('"\'')
    parts = [part.strip('"\' ,') for part in query.split() if part.strip('"\' ,')]
    token_filters: list[str] = []
    chain_filter = ""
    protocol_filter = ""
    sort_by = "tvl"

    idx = 0
    while idx < len(parts):
        part = parts[idx]
        lower = part.lower()

        if lower.startswith("sort:"):
            sort_by = lower.split(":", 1)[1]
            idx += 1
            continue

        if lower in _IGNORE_DEFI_QUERY_PARTS:
            idx += 1
            continue

        if "/" in part:
            token_filters.extend(token.upper() for token in part.split("/") if token.strip())
            idx += 1
            continue

        mapped_chain = _CHAIN_ALIASES_LLAMA.get(lower, "")
        if mapped_chain:
            chain_filter = mapped_chain
        elif lower in _KNOWN_PROTOCOLS or any(lower in trusted for trusted in _TRUSTED_YIELD_PROTOCOLS):
            protocol_filter = lower
        else:
            token_filters.append(part.upper())

        idx += 1

    return {
        "query": query,
        "token_filters": token_filters,
        "chain_filter": chain_filter,
        "protocol_filter": protocol_filter,
        "sort_by": sort_by,
    }


def _parse_fee_tier(pool_meta: str) -> tuple[str, Optional[float]]:
    pool_meta = (pool_meta or "").strip()
    if not pool_meta:
        return "", None

    match = re.search(r"(\d+(?:\.\d+)?)\s*%", pool_meta)
    if not match:
        return pool_meta, None

    pct = float(match.group(1))
    return f"{match.group(1)}%", pct / 100.0


def _apy_to_apr(apy_pct: Optional[float]) -> Optional[float]:
    if apy_pct is None:
        return None
    apy = float(apy_pct)
    if apy <= -100:
        return None
    annual_factor = 1 + (apy / 100.0)
    if annual_factor <= 0:
        return None
    daily_rate = annual_factor ** (1 / 365.0) - 1
    return daily_rate * 365.0 * 100.0


def _average_daily_volume(pool: dict[str, Any]) -> tuple[Optional[float], str]:
    volume_7d = pool.get("volumeUsd7d")
    if volume_7d is not None:
        volume_7d_f = float(volume_7d or 0)
        if volume_7d_f > 0:
            return volume_7d_f / 7.0, "7d avg"

    volume_1d = pool.get("volumeUsd1d")
    if volume_1d is not None:
        volume_1d_f = float(volume_1d or 0)
        if volume_1d_f > 0:
            return volume_1d_f, "24h extrap."

    return None, ""


def _display_apy_value(pool: dict[str, Any]) -> tuple[Optional[float], str]:
    apy_30d = pool.get("apyMean30d")
    if apy_30d is not None:
        apy_30d_f = float(apy_30d or 0)
        if apy_30d_f > 0:
            return apy_30d_f, "APY (30d avg)"

    apy_current = pool.get("apy")
    if apy_current is not None:
        apy_current_f = float(apy_current or 0)
        return apy_current_f, "APY (current)"

    return None, "APY"


def _chain_rpc_candidates(chain: str) -> list[str]:
    chain_lower = (chain or "").lower()
    name_map = {
        "ethereum": "Ethereum",
        "bsc": "BNB Chain",
        "polygon": "Polygon",
        "arbitrum": "Arbitrum",
        "optimism": "Optimism",
        "base": "Base",
        "avalanche": "Avalanche",
    }
    chain_name = name_map.get(chain_lower, "")
    configured = []
    for chain_id, rpc_url in settings.rpc_urls.items():
        try:
            if _chain_name(int(chain_id)).lower().startswith(chain_lower) and rpc_url:
                configured.append(rpc_url)
        except Exception:
            continue

    if chain_name:
        for cfg in _BALANCE_CHAINS:
            if cfg.get("name", "").lower() == chain_name.lower():
                return configured + [rpc for rpc in cfg.get("rpcs", []) if rpc not in configured]

    return configured


def _resolve_uniswap_v3_pool_address(chain: str, underlying_tokens: list[str], pool_meta: str) -> str:
    if len(underlying_tokens) < 2:
        return ""

    fee_label, fee_decimal = _parse_fee_tier(pool_meta)
    if fee_decimal is None:
        return ""

    fee_tier = int(round(fee_decimal * 1_000_000))
    if fee_tier <= 0:
        return ""

    token_a, token_b = underlying_tokens[0], underlying_tokens[1]
    rpc_candidates = _chain_rpc_candidates(chain)
    if not rpc_candidates:
        logger.info("[Uniswap] no RPC candidates for chain=%s fee=%s", chain, fee_label)
        return ""

    for rpc_url in rpc_candidates:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 8}))
            if not w3.is_connected():
                continue
            factory = w3.eth.contract(
                address=Web3.to_checksum_address(_UNISWAP_V3_FACTORY),
                abi=_UNISWAP_V3_FACTORY_ABI,
            )
            pool = factory.functions.getPool(
                Web3.to_checksum_address(token_a),
                Web3.to_checksum_address(token_b),
                fee_tier,
            ).call()
            if pool and pool != "0x0000000000000000000000000000000000000000":
                return Web3.to_checksum_address(pool)
        except Exception as exc:
            logger.info("[Uniswap] pool lookup failed on %s: %s", rpc_url, exc)

    return ""


def _resolve_uniswap_v2_pool_address(chain: str, underlying_tokens: list[str]) -> str:
    if len(underlying_tokens) < 2:
        return ""

    token_a, token_b = underlying_tokens[0], underlying_tokens[1]
    rpc_candidates = _chain_rpc_candidates(chain)
    if not rpc_candidates:
        logger.info("[Uniswap V2] no RPC candidates for chain=%s", chain)
        return ""

    for rpc_url in rpc_candidates:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 8}))
            if not w3.is_connected():
                continue
            factory = w3.eth.contract(
                address=Web3.to_checksum_address(_UNISWAP_V2_FACTORY),
                abi=_UNISWAP_V2_FACTORY_ABI,
            )
            pair = factory.functions.getPair(
                Web3.to_checksum_address(token_a),
                Web3.to_checksum_address(token_b),
            ).call()
            if pair and pair != "0x0000000000000000000000000000000000000000":
                return Web3.to_checksum_address(pair)
        except Exception as exc:
            logger.info("[Uniswap V2] pair lookup failed on %s: %s", rpc_url, exc)

    return ""


def _native_pool_address(pool_id: str) -> str:
    if not pool_id or _UUID_RE.match(pool_id):
        return ""
    return pool_id.split("-")[0] if "-" in pool_id else pool_id


def _pool_explorer_url(chain: str, address: str) -> str:
    template = _POOL_EXPLORERS.get((chain or "").lower())
    return template.format(address) if template and address else ""


def _project_dex_aliases(project: str) -> set[str]:
    lower = (project or "").lower()
    aliases = {lower}

    mapped = {
        "uniswap-v3": {"uniswap"},
        "uniswap-v2": {"uniswap"},
        "pancakeswap-amm": {"pancakeswap"},
        "pancakeswap-amm-v3": {"pancakeswap"},
        "curve-dex": {"curve"},
        "balancer-v2": {"balancer"},
        "camelot-v3": {"camelot"},
        "velodrome-v2": {"velodrome"},
        "aerodrome-slipstream": {"aerodrome"},
        "quickswap-dex": {"quickswap"},
        "trader-joe-dex": {"traderjoe", "lfj"},
    }
    aliases.update(mapped.get(lower, set()))

    heuristics = (
        "uniswap",
        "pancake",
        "sushi",
        "curve",
        "balancer",
        "camelot",
        "aerodrome",
        "velodrome",
        "quickswap",
        "trader",
        "lfj",
        "raydium",
        "orca",
        "thena",
    )
    for name in heuristics:
        if name in lower:
            aliases.add("pancakeswap" if name == "pancake" else ("sushiswap" if name == "sushi" else name))

    return {alias for alias in aliases if alias}


def _resolve_dexscreener_pool_address(chain: str, project: str, underlying_tokens: list[str]) -> str:
    if len(underlying_tokens) < 2:
        return ""

    chain_id = _DEXSCREENER_CHAIN.get((chain or "").lower(), (chain or "").lower())
    token_a = str(underlying_tokens[0] or "").lower()
    token_b = str(underlying_tokens[1] or "").lower()
    if not chain_id or not token_a or not token_b:
        return ""

    dex_aliases = _project_dex_aliases(project)

    try:
        resp = _requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token_a}", timeout=8)
        resp.raise_for_status()
        pairs = resp.json().get("pairs") or []
    except Exception as exc:
        logger.info("[DexScreener] pool lookup failed for %s on %s: %s", project, chain, exc)
        return ""

    best_address = ""
    best_liquidity = -1.0

    for pair in pairs:
        pair_chain = str(pair.get("chainId") or "").lower()
        if pair_chain != chain_id:
            continue

        dex_id = str(pair.get("dexId") or "").lower()
        if dex_aliases and not any(alias == dex_id or alias in dex_id or dex_id in alias for alias in dex_aliases):
            continue

        base = str((pair.get("baseToken") or {}).get("address") or "").lower()
        quote = str((pair.get("quoteToken") or {}).get("address") or "").lower()
        if {base, quote} != {token_a, token_b}:
            continue

        pair_address = str(pair.get("pairAddress") or "")
        if not pair_address:
            continue

        liquidity = float(((pair.get("liquidity") or {}).get("usd")) or 0)
        if liquidity > best_liquidity:
            best_address = pair_address
            best_liquidity = liquidity

    return best_address


def _resolve_pool_address(pool: dict[str, Any]) -> str:
    pool_id = str(pool.get("pool") or "")
    native_address = _native_pool_address(pool_id)
    if native_address:
        return native_address

    chain = str(pool.get("chain") or "").lower()
    project = str(pool.get("project") or "").lower()
    underlying = [str(token) for token in (pool.get("underlyingTokens") or []) if token]

    if project == "uniswap-v3":
        resolved = _resolve_uniswap_v3_pool_address(chain, underlying, str(pool.get("poolMeta") or ""))
        if resolved:
            return resolved

    if project == "uniswap-v2":
        resolved = _resolve_uniswap_v2_pool_address(chain, underlying)
        if resolved:
            return resolved

    if len(underlying) >= 2:
        resolved = _resolve_dexscreener_pool_address(chain, project, underlying)
        if resolved:
            return resolved

    if len(underlying) == 1:
        return underlying[0]

    return ""


def _estimate_fee_apr(pool: dict[str, Any]) -> Optional[float]:
    _label, fee_decimal = _parse_fee_tier(str(pool.get("poolMeta") or ""))
    tvl = float(pool.get("tvlUsd") or 0)
    avg_daily_volume, _window = _average_daily_volume(pool)
    if fee_decimal is None or fee_decimal <= 0 or tvl <= 0 or not avg_daily_volume or avg_daily_volume <= 0:
        return None
    return (avg_daily_volume * fee_decimal * 365.0 / tvl) * 100.0


def _sort_metric_label(sort_by: str) -> str:
    if sort_by == "apr":
        return "highest APY (30d avg when available)"
    if sort_by == "apy":
        return "highest APY (30d avg when available)"
    return "largest TVL"


def _yield_confidence(pool: dict[str, Any], *, explicit_protocol: bool = False) -> str:
    chain = str(pool.get("chain") or "").lower()
    project = str(pool.get("project") or "").lower()
    tvl = float(pool.get("tvlUsd") or 0)
    volume_1d = float(pool.get("volumeUsd1d") or 0)
    estimated_fee_apr = _estimate_fee_apr(pool)
    apy_base_7d = pool.get("apyBase7d")
    apy_base = pool.get("apyBase")
    reference_fee_apr = _apy_to_apr(apy_base_7d if apy_base_7d is not None else apy_base)
    trusted_protocol = explicit_protocol or any(name in project for name in _TRUSTED_YIELD_PROTOCOLS)
    supported_chain = chain in _SUPPORTED_YIELD_CHAINS

    if estimated_fee_apr is not None and reference_fee_apr is not None and reference_fee_apr > 0:
        tolerance = max(1.0, estimated_fee_apr * 0.35)
        if supported_chain and trusted_protocol and abs(estimated_fee_apr - reference_fee_apr) <= tolerance:
            return "high"

    if supported_chain and trusted_protocol and tvl >= 500_000 and volume_1d >= 10_000:
        return "medium"

    if supported_chain and tvl >= 100_000 and volume_1d >= 10_000:
        return "low"

    return "unverified"


def _protocol_url(
    dex: str,
    chain: str,
    pool_id: str = "",
    pair_address: str = "",
    token0: str = "",
    token1: str = "",
) -> str:
    d = (dex or "").lower()
    ch = (chain or "").lower()
    uni_chain = "mainnet" if ch == "ethereum" else ch
    dex_ch = {
        "solana": "solana", "bsc": "bsc", "ethereum": "ethereum", "polygon": "polygon",
        "arbitrum": "arbitrum", "optimism": "optimism", "base": "base", "avalanche": "avalanche",
        "fantom": "fantom", "cronos": "cronos", "celo": "celo",
    }.get(ch, ch)

    if "uniswap" in d:
        if pair_address:
            return f"https://app.uniswap.org/explore/pools/{uni_chain}/{pair_address}"
        return f"https://app.uniswap.org/explore/pools/{uni_chain}"
    if "pancake" in d:
        return "https://pancakeswap.finance/liquidity"
    if "raydium" in d:
        if pair_address and "-" not in pair_address:
            return f"https://raydium.io/liquidity/add/?ammId={pair_address}"
        return "https://raydium.io/liquidity/"
    if "orca" in d:
        return "https://www.orca.so/pools"
    if "meteora" in d:
        return "https://app.meteora.ag/"
    if "curve" in d or "convex" in d or "conic" in d or "ellipsis" in d:
        return f"https://curve.fi/#/{ch}/pools"
    if "aerodrome" in d:
        return "https://aerodrome.finance/pools"
    if "velodrome" in d:
        return "https://velodrome.finance/pools"
    if "camelot" in d:
        return "https://app.camelot.exchange/pools"
    if ("trader" in d and "joe" in d) or "lfj" in d:
        return f"https://lfj.gg/{ch}/pool"
    if "sushi" in d:
        return "https://www.sushi.com/pools"
    if "quickswap" in d:
        return "https://quickswap.exchange/#/pools"
    if "balancer" in d or "beethoven" in d:
        return f"https://app.balancer.fi/#/{ch}/pools"
    if "kyber" in d:
        return f"https://kyberswap.com/{ch}/pools"
    if "thena" in d:
        return "https://www.thena.fi/pools"
    if "fluid" in d:
        return "https://fluid.instadapp.io/liquidity"
    if "morpho" in d:
        return "https://app.morpho.org/"
    if "pendle" in d:
        return "https://app.pendle.finance/trade/pools"
    if "aave" in d:
        return "https://app.aave.com/"
    if "compound" in d:
        return "https://app.compound.finance/"
    if "spark" in d:
        return "https://app.spark.fi/"
    if "frax" in d:
        return "https://app.frax.finance/"
    if "lido" in d:
        return "https://stake.lido.fi/"
    if "gmx" in d:
        return "https://app.gmx.io/#/pools"
    if "maverick" in d:
        return f"https://app.mav.xyz/?chain={ch}"
    if "dodo" in d:
        return "https://app.dodoex.io/pools"
    if "wombat" in d:
        return "https://app.wombat.exchange/pool"
    if "yearn" in d:
        return f"https://yearn.fi/vaults/{ch}"
    if "beefy" in d:
        return "https://app.beefy.com/"

    if pair_address and "-" not in pair_address:
        return f"https://dexscreener.com/{dex_ch}/{pair_address}"
    return f"https://dexscreener.com/{dex_ch}"


def get_defi_analytics(query: str, *, supported_only: bool = False, verified_only: bool = False) -> str:
    """
    Fetches live yield/pool data from DefiLlama and returns top-5 pools
    filtered by token symbol, chain, and/or protocol.
    Returns structured universal_cards JSON with protocol URLs.

    Input examples:
      "USDC"                   – best USDC pools across all chains (by TVL)
      "USDC polygon"           – best USDC pools on Polygon (by TVL)
      "aave"                   – best pools in Aave protocol (by TVL)
      "ETH arbitrum"           – ETH pools on Arbitrum (by TVL)
      "RAY solana"             – RAY pools on Solana (by TVL)
      "SOL solana sort:apy"    – highest-APY SOL pools on Solana
      "solana sort:apy"        – highest-APY pools on Solana (any token)
    """
    try:
        parsed_query = _parse_defi_analytics_query(query)
        query = parsed_query["query"]
        token_filters = parsed_query["token_filters"]
        chain_filter = parsed_query["chain_filter"]
        protocol_filter = parsed_query["protocol_filter"]
        sort_by = parsed_query["sort_by"]

        resp = _requests.get("https://yields.llama.fi/pools", timeout=12)
        if resp.status_code != 200:
            return f"DefiLlama API error: HTTP {resp.status_code}"

        all_pools: list[dict] = resp.json().get("data", [])

        # Stablecoin detection — pairs of stable assets have much lower realistic APY ceilings
        _STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "FRAX", "TUSD", "LUSD", "USDP",
                        "GUSD", "USDD", "CRVUSD", "PYUSD", "USDB", "USDE", "SUSD",
                        "ZUSD", "ZUSDC", "ZUSDT", "IDAI", "IUSDC", "IUSDT"}
        is_stablecoin_query = bool(token_filters) and all(
            any(s in t for s in _STABLECOINS) for t in token_filters
        )

        # TVL floors: always at least $100K for APR/APY sorts (prevents tiny anomalies),
        # $500K for stablecoin pairs (real pools are large), $50K default.
        if is_stablecoin_query:
            tvl_floor = 500_000
        elif sort_by in {"apy", "apr"}:
            tvl_floor = 100_000
        else:
            tvl_floor = 50_000

        # APY ceiling: stablecoin-to-stablecoin pools realistically max out around 50%.
        # Anything higher is almost certainly a DefiLlama data anomaly / outlier.
        apy_ceiling = 50.0 if is_stablecoin_query else float("inf")

        filtered: list[dict] = []
        for pool in all_pools:
            apy = pool.get("apy") or 0
            tvl = pool.get("tvlUsd") or 0
            if apy <= 0 or tvl < tvl_floor:
                continue
            # Skip DefiLlama-flagged outliers and unrealistic APY values
            if pool.get("outlier") is True:
                continue
            if apy > apy_ceiling:
                continue

            sym = pool.get("symbol", "").upper()
            chain = pool.get("chain", "").lower()
            project = pool.get("project", "").lower()
            volume_1d = float(pool.get("volumeUsd1d") or 0)

            if token_filters:
                pool_tokens = _split_pool_symbol(sym)
                if len(token_filters) >= 2 and len(pool_tokens) != len(token_filters):
                    continue
                if not all(_pool_token_matches(t, pool_tokens) for t in token_filters):
                    continue
            if chain_filter and chain_filter != chain:
                continue
            if protocol_filter and protocol_filter not in project:
                continue

            if supported_only and not chain_filter and chain not in _SUPPORTED_YIELD_CHAINS:
                continue

            if is_stablecoin_query and not protocol_filter:
                trusted_protocol = any(name in project for name in _TRUSTED_YIELD_PROTOCOLS)
                if volume_1d < 10_000:
                    continue
                if not trusted_protocol and tvl < 2_000_000:
                    continue

            confidence = _yield_confidence(pool, explicit_protocol=bool(protocol_filter))
            if verified_only and confidence == "unverified":
                continue

            display_apy, display_apy_label = _display_apy_value(pool)
            if sort_by in {"apr", "apy"} and display_apy is None:
                continue

            pool["_confidence"] = confidence
            pool["_display_apy"] = display_apy
            pool["_display_apy_label"] = display_apy_label

            filtered.append(pool)

        # Sort by user-requested metric
        confidence_rank = {"high": 3, "medium": 2, "low": 1, "unverified": 0}
        if sort_by == "apr":
            filtered.sort(
                key=lambda p: (
                    confidence_rank.get(str(p.get("_confidence") or "unverified"), 0),
                    float(p.get("_display_apy") or 0),
                    float(p.get("volumeUsd1d") or 0),
                    float(p.get("tvlUsd") or 0),
                    float(p.get("apy") or 0),
                ),
                reverse=True,
            )
        elif sort_by == "apy":
            filtered.sort(
                key=lambda p: (
                    confidence_rank.get(str(p.get("_confidence") or "unverified"), 0),
                    float(p.get("_display_apy") or 0),
                    float(p.get("volumeUsd1d") or 0),
                    float(p.get("tvlUsd") or 0),
                ),
                reverse=True,
            )
        else:
            filtered.sort(
                key=lambda p: (
                    confidence_rank.get(str(p.get("_confidence") or "unverified"), 0),
                    float(p.get("tvlUsd") or 0),
                    float(p.get("volumeUsd1d") or 0),
                    float(p.get("apy") or 0),
                ),
                reverse=True,
            )
        if not filtered:
            return f"No active pools found for '{query}'. Try a different token symbol, chain, or protocol name."

        cards = []
        seen_pool_addresses: set[str] = set()
        for p in filtered:
            symbol  = p.get("symbol", "—")
            chain   = p.get("chain", "").lower()
            project = p.get("project", "—")
            apy_current = float(p.get("apy") or 0)
            apy_reward = p.get("apyReward") or 0
            tvl     = p.get("tvlUsd") or 0
            volume_1d = p.get("volumeUsd1d") or 0
            pool_id = p.get("pool", "")
            pool_meta = str(p.get("poolMeta") or "").strip()
            confidence = str(p.get("_confidence") or "unverified")
            display_apy = p.get("_display_apy")
            display_apy_label = str(p.get("_display_apy_label") or "APY")

            pair_address = _resolve_pool_address(p)
            if not pair_address:
                continue
            if pair_address.lower() in seen_pool_addresses:
                continue

            defillama_url = f"https://defillama.com/yields/pool/{pool_id}" if pool_id else ""
            explorer_url = _pool_explorer_url(chain, pair_address)

            protocol_url = _protocol_url(
                project,
                chain,
                pool_id=pool_id,
                pair_address=pair_address,
            )

            primary_url = protocol_url or defillama_url
            primary_label = "View Pool"
            secondary_url = defillama_url if defillama_url and defillama_url != primary_url else ""
            secondary_label = "View in DefiLlama"

            details_dict = {}

            if display_apy is not None:
                details_dict[display_apy_label] = f"{float(display_apy):.2f}%"
            if apy_current > 0 and (display_apy is None or abs(float(display_apy) - apy_current) > 0.005):
                details_dict["APY (current)"] = f"{apy_current:.2f}%"
            details_dict["TVL"] = f"${tvl:,.0f}"
            details_dict["24h Volume"] = f"${volume_1d:,.0f}"

            if pool_meta:
                details_dict["Pool Meta"] = pool_meta

            if apy_reward:
                details_dict["Rewards APY"] = f"{float(apy_reward):.2f}%"

            if confidence != "unverified":
                details_dict["Confidence"] = confidence.capitalize()
            else:
                details_dict["Confidence"] = "Needs manual check"

            if pair_address:
                details_dict["Pool Address"] = pair_address

            cards.append({
                "title": f"{symbol} Pool",
                "subtitle": f"{_format_protocol_name(project)} · {chain.capitalize()}",
                "details": details_dict,
                "url": primary_url,
                "button_text": primary_label,
                "defillama_url": secondary_url,
                "defillama_button_text": secondary_label,
                "explorer_url": explorer_url,
            })
            seen_pool_addresses.add(pair_address.lower())

            if len(cards) >= 5:
                break

        if not cards:
            return f"No verified pools with a resolvable pool address found for '{query}'. Try a different token symbol, chain, or protocol name."

        sort_label = _sort_metric_label(sort_by)
        chain_label = chain_filter.capitalize() if chain_filter else ("supported chains" if supported_only else "all chains")
        token_label = "/".join(token_filters) if token_filters else ""
        msg_parts = ["Here are the best verified liquidity pools"]
        if token_label:
            msg_parts.append(f"for {token_label}")
        msg_parts.append(f"on {chain_label}" if chain_filter else f"across {chain_label}")
        msg_parts.append(f"(sorted by {sort_label}).")
        if sort_by == "apr":
            msg_parts.append("APR is omitted because we cannot verify a protocol-consistent APR for these pools. Showing DefiLlama APY instead, using the 30-day average when available.")
        elif sort_by == "apy":
            msg_parts.append("APY uses DefiLlama's 30-day average when available, with the current APY shown separately for context.")
        else:
            msg_parts.append("APY values come from DefiLlama, and every result includes a resolvable pool address plus direct protocol and DefiLlama links.")
        message = " ".join(msg_parts)

        return json.dumps({
            "type": "universal_cards",
            "message": message,
            "cards": cards,
        })

    except Exception as exc:
        logger.exception("get_defi_analytics error")
        return f"DefiLlama error: {exc}"


# ---------------------------------------------------------------------------
# Step 3.6 — Solana swap via Jupiter API v6 (no platform fee, no API key)
# ---------------------------------------------------------------------------

# Well-known Solana token mint addresses for symbol resolution
_SOL_MINTS: Final[dict[str, str]] = {
    "sol":    "So11111111111111111111111111111111111111112",
    "usdc":   "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "usdt":   "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "bonk":   "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "wen":    "WENWENvqqNya429ubCdR81ZmD69brwQaaBYY6p3LCpk",
    "jup":    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "ray":    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "orca":   "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "msol":   "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    "jito":   "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "wbtc":   "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
    "weth":   "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs",
    "pyth":   "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "jto":    "jtojtomepa8b1As4vcmvBmLQMRMRMRHMDDFQPVXq4TfY",
}


def _resolve_sol_mint(token: str) -> str:
    """Return the Solana mint address for a symbol or passthrough if already a mint."""
    lower = token.strip().lower()
    if lower in _SOL_MINTS:
        return _SOL_MINTS[lower]
    # If it looks like a base58 mint address (32–44 chars, no spaces), use as-is
    if 32 <= len(token) <= 44 and token.isalnum():
        return token
    raise ValueError(f"Unknown Solana token '{token}'. Pass the mint address directly or use a known symbol.")


def build_solana_swap(raw: str) -> str:
    """
    Build a ready-to-sign Solana swap transaction via Jupiter API v6.

    Input (JSON string):
        sell_token   – mint address or symbol (e.g. "SOL", "USDC")
        buy_token    – mint address or symbol
        sell_amount  – amount to sell; may be a human-readable float (e.g. 0.5 SOL)
                       OR already in lamports (e.g. 500000000). The function converts
                       floats to the correct integer units automatically:
                         SOL / WSOL   → × 10^9
                         USDC / USDT  → × 10^6
                         everything else → × 10^9 (safe default for most SPL tokens)
        user_pubkey  – Solana wallet public key (Phantom); must not be empty

    Returns JSON with:
        status           "ok"
        chain_type       "solana"
        swapTransaction  base64-encoded serialised VersionedTransaction
        out_amount       expected output in raw units (integer)
        out_symbol       output token symbol (best-effort)
        in_symbol        input token symbol (best-effort)
    """
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON input: {exc}"})

    try:
        sell_token  = str(params["sell_token"])
        buy_token   = str(params["buy_token"])
        raw_amount  = params["sell_amount"]   # may be float or int string
        user_pubkey = str(params.get("user_pubkey") or "").strip()
    except (KeyError, ValueError) as exc:
        return json.dumps({"error": f"Missing or invalid parameter: {exc}"})

    # ── Validate user_pubkey ─────────────────────────────────────────────────
    if not user_pubkey or len(user_pubkey) < 32:
        return json.dumps({
            "error": (
                "user_pubkey is missing or invalid. "
                "The Phantom wallet public key must be provided to build the transaction."
            )
        })

    # ── Resolve mint addresses ───────────────────────────────────────────────
    try:
        input_mint  = _resolve_sol_mint(sell_token)
        output_mint = _resolve_sol_mint(buy_token)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    # ── Convert sell_amount to integer lamports ──────────────────────────────
    # Jupiter requires amount as a plain integer in the token's smallest unit.
    # The LLM might pass a human-readable float (e.g. 0.01156 SOL), so we
    # detect the token's decimals and multiply accordingly.
    _6_DECIMAL_MINTS = {
        _SOL_MINTS["usdc"],
        _SOL_MINTS["usdt"],
    }
    _9_DECIMAL_MINTS = {
        _SOL_MINTS["sol"],
        _SOL_MINTS["msol"],
        _SOL_MINTS["jito"],
    }

    try:
        amount_raw = float(raw_amount)
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"sell_amount must be a number, got: {raw_amount!r} ({exc})"})

    if input_mint in _6_DECIMAL_MINTS:
        token_decimals = 6
    else:
        # SOL, mSOL, JitoSOL, and most SPL tokens use 9 decimals
        token_decimals = 9

    # If the value is already an integer >= 1000 it is likely already in base units
    # (e.g. the LLM passed 1000000000 for 1 SOL).  If it is a float or < 1000,
    # treat it as a human-readable amount and scale up.
    if amount_raw == int(amount_raw) and amount_raw >= 1000:
        sell_amount = int(amount_raw)
    else:
        sell_amount = int(round(amount_raw * (10 ** token_decimals)))

    if sell_amount <= 0:
        return json.dumps({"error": f"sell_amount resolved to {sell_amount} — must be > 0"})

    logger.info(
        "[Jupiter] sell %s → buy %s | raw_amount=%s decimals=%d → lamports=%d | pubkey=%s…",
        sell_token, buy_token, raw_amount, token_decimals, sell_amount, user_pubkey[:8],
    )

    jup_base = "https://public.jupiterapi.com"

    # ── Step 1: Quote ────────────────────────────────────────────────────────
    try:
        quote_resp = _requests.get(
            f"{jup_base}/quote",
            params={
                "inputMint":   input_mint,
                "outputMint":  output_mint,
                "amount":      sell_amount,
                "slippageBps": 50,   # 0.5 % slippage
            },
            timeout=15,
        )
        if not quote_resp.ok:
            err_text = quote_resp.text[:500]
            logger.error("[Jupiter] Quote HTTP %d: %s", quote_resp.status_code, err_text)
            return json.dumps({
                "error": f"Jupiter quote HTTP {quote_resp.status_code}: {err_text}"
            })
        quote = quote_resp.json()
    except Exception as exc:
        logger.exception("[Jupiter] Quote request failed")
        return json.dumps({"error": f"Jupiter quote request failed: {exc}"})

    if "error" in quote:
        err_msg = quote["error"]
        logger.error("[Jupiter] Quote API error: %s", err_msg)
        return json.dumps({"error": f"Jupiter quote error: {err_msg}"})

    raw_out_amount = int(quote.get("outAmount", 0))
    _SOL_MINT_ADDR = "So11111111111111111111111111111111111111112"
    out_decimals   = 9 if output_mint == _SOL_MINT_ADDR else 6
    ui_out_amount  = round(raw_out_amount / (10 ** out_decimals), 5)

    # ── Step 2: Swap transaction ─────────────────────────────────────────────
    try:
        swap_resp = _requests.post(
            f"{jup_base}/swap",
            json={
                "quoteResponse":    quote,
                "userPublicKey":    user_pubkey,
                "wrapAndUnwrapSol": True,
            },
            timeout=20,
        )
        if not swap_resp.ok:
            err_text = swap_resp.text[:500]
            logger.error("[Jupiter] Swap HTTP %d: %s", swap_resp.status_code, err_text)
            return json.dumps({
                "error": f"Jupiter swap HTTP {swap_resp.status_code}: {err_text}"
            })
        swap_data = swap_resp.json()
    except Exception as exc:
        logger.exception("[Jupiter] Swap request failed")
        return json.dumps({"error": f"Jupiter swap request failed: {exc}"})

    if "error" in swap_data:
        err_msg = swap_data["error"]
        logger.error("[Jupiter] Swap API error: %s", err_msg)
        return json.dumps({"error": f"Jupiter swap error: {err_msg}"})

    swap_tx_b64 = swap_data.get("swapTransaction")
    if not swap_tx_b64:
        logger.error("[Jupiter] Swap response missing swapTransaction: %s", swap_data)
        return json.dumps({"error": "Jupiter returned no swapTransaction field"})

    # Best-effort human-readable symbols (reverse-lookup from mint)
    _mint_to_sym = {v: k.upper() for k, v in _SOL_MINTS.items()}
    in_sym  = _mint_to_sym.get(input_mint,  input_mint[:8] + "…")
    out_sym = _mint_to_sym.get(output_mint, output_mint[:8] + "…")

    logger.info("[Jupiter] Swap tx built OK — outAmount=%d (%s %s)", raw_out_amount, ui_out_amount, out_sym)

    return json.dumps({
        "status":          "ok",
        "type":            "solana_swap_proposal",
        "chain_type":      "solana",
        "swapTransaction": swap_tx_b64,
        "out_amount":      str(raw_out_amount),
        "ui_out_amount":   ui_out_amount,
        "in_symbol":       in_sym,
        "out_symbol":      out_sym,
    })


# ---------------------------------------------------------------------------
# Step 3.7 — Liquidity pool search via DexScreener (free, no API key)
# ---------------------------------------------------------------------------

# Normalises user/LLM chain names → DexScreener chainId strings
_DEXSCREENER_CHAIN: Final[dict[str, str]] = {
    # BNB Smart Chain
    "bsc": "bsc", "bnb": "bsc", "56": "bsc",
    "bnb chain": "bsc", "bnb smart chain": "bsc", "binance": "bsc",
    "binance smart chain": "bsc",
    # Ethereum
    "eth": "ethereum", "ethereum": "ethereum", "1": "ethereum",
    # Polygon
    "polygon": "polygon", "matic": "polygon", "137": "polygon",
    # Arbitrum
    "arbitrum": "arbitrum", "arb": "arbitrum", "42161": "arbitrum",
    # Optimism
    "optimism": "optimism", "op": "optimism", "10": "optimism",
    # Base
    "base": "base", "8453": "base",
    # Avalanche
    "avalanche": "avalanche", "avax": "avalanche", "43114": "avalanche",
    # Solana
    "solana": "solana", "sol": "solana",
    # Other
    "fantom": "fantom", "ftm": "fantom",
    "cronos": "cronos",
    "celo": "celo",
}


def find_liquidity_pool(raw: str) -> str:
    """
    Hybrid pool search: DefiLlama first (deep TVL data), DexScreener fallback (meme coins).

    Input: JSON string with keys —
        query     – token pair, e.g. "USDC USDT" or "WBNB CAKE" or "PEPE"
        chain_id  – optional: "bsc", "bnb", "56", "ethereum", "polygon", etc.

    Strategy:
        1. DefiLlama /pools — best for established/stablecoin pairs (accurate TVL).
        2. DexScreener search — fallback for new tokens / meme coins not in DefiLlama.
    """
    try:
        params   = json.loads(raw)
        query    = str(params.get("query", "")).strip()
        chain_raw = str(params.get("chain_id", "")).strip().lower()
    except (json.JSONDecodeError, AttributeError):
        query     = str(raw).strip()
        chain_raw = ""

    if not query:
        return json.dumps({"error": "query is required (e.g. 'USDC USDT' or 'WBNB CAKE')"})

    # Normalise chain to DexScreener chainId string
    chain_filter = _DEXSCREENER_CHAIN.get(chain_raw, chain_raw)

    search_tokens = [t for t in query.upper().split() if t]

    # ── Explorer URLs (shared by both paths) ─────────────────────────────────
    _EXPLORER: Final[dict[str, str]] = {
        "bsc":       "https://bscscan.com/address/{}",
        "ethereum":  "https://etherscan.io/address/{}",
        "polygon":   "https://polygonscan.com/address/{}",
        "arbitrum":  "https://arbiscan.io/address/{}",
        "optimism":  "https://optimistic.etherscan.io/address/{}",
        "base":      "https://basescan.org/address/{}",
        "avalanche": "https://snowtrace.io/address/{}",
        "solana":    "https://solscan.io/account/{}",
        "fantom":    "https://ftmscan.com/address/{}",
        "cronos":    "https://cronoscan.com/address/{}",
        "celo":      "https://celoscan.io/address/{}",
    }

    def _explorer_url(chain: str, address: str) -> str:
        tmpl = _EXPLORER.get(chain.lower(), "https://blockscan.com/address/{}")
        return tmpl.format(address) if address else ""

    # UUID v4 pattern used by DefiLlama for internal pool IDs
    _UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-', re.I)

    def _is_uuid(pool_id: str) -> bool:
        """True if pool_id is a DefiLlama UUID, not a native chain address."""
        return bool(_UUID_RE.match(pool_id))

    def _native_address(pool_id: str, is_uuid_pool: bool) -> str:
        """
        Strip the '-chain' suffix that DefiLlama appends to native addresses.
        e.g. '0xABC-ethereum' → '0xABC'
             'EPjFW...-solana'  → 'EPjFW...'
        UUID pool IDs are returned as-is (full UUID).
        """
        if is_uuid_pool:
            return pool_id
        return pool_id.split("-")[0]

    def _protocol_url(
        dex: str, chain: str,
        pool_id: str = "", pair_address: str = "",
        token0: str = "", token1: str = "",
    ) -> str:
        """Route to the DEX liquidity hub page for known protocols.

        Falls back to DefiLlama (pool page) for DefiLlama-sourced pools, or
        DexScreener for DexScreener-sourced pools.
        """
        d  = dex.lower()
        ch = chain.lower()
        uni_chain  = "mainnet" if ch == "ethereum" else ch
        dex_ch     = _DEXSCREENER_CHAIN.get(ch, ch)

        logger.info(
            "[protocol_url] dex=%r chain=%r pool_id=%r pair=%r tok0=%r tok1=%r",
            dex, chain, pool_id, pair_address,
            token0[:8] if token0 else "", token1[:8] if token1 else "",
        )

        # ── Known protocol hubs ────────────────────────────────────────────
        if "uniswap" in d:
            return f"https://app.uniswap.org/explore/pools/{uni_chain}"
        if "pancake" in d:
            return "https://pancakeswap.finance/liquidity"
        if "raydium" in d:
            is_uuid = "-" in pair_address
            if not is_uuid and pair_address:
                return f"https://raydium.io/liquidity/add/?ammId={pair_address}"
            return "https://raydium.io/liquidity/"
        if "orca" in d:
            return "https://www.orca.so/liquidity"
        if "meteora" in d:
            return "https://app.meteora.ag/"
        if "curve" in d or "convex" in d or "conic" in d or "ellipsis" in d:
            return f"https://curve.fi/#/{ch}/pools"
        if "aerodrome" in d:
            return "https://aerodrome.finance/pools"
        if "velodrome" in d:
            return "https://velodrome.finance/pools"
        if "camelot" in d:
            return "https://app.camelot.exchange/pools"
        if "trader" in d and "joe" in d or "lfj" in d:
            return f"https://lfj.gg/{ch}/pool"
        if "sushi" in d:
            return "https://www.sushi.com/pools"
        if "quickswap" in d:
            return "https://quickswap.exchange/#/pools"
        if "balancer" in d or "beethoven" in d:
            return f"https://app.balancer.fi/#/{ch}/pools"
        if "kyber" in d:
            return f"https://kyberswap.com/{ch}/pools"
        if "thena" in d:
            return "https://www.thena.fi/pools"
        if "fluid" in d:
            return "https://fluid.instadapp.io/liquidity"
        if "morpho" in d:
            return "https://app.morpho.org/"
        if "pendle" in d:
            return "https://app.pendle.finance/trade/pools"
        if "aave" in d:
            return "https://app.aave.com/"
        if "compound" in d:
            return "https://app.compound.finance/"
        if "spark" in d:
            return "https://app.spark.fi/"
        if "frax" in d:
            return "https://app.frax.finance/"
        if "lido" in d:
            return "https://stake.lido.fi/"
        if "gmx" in d:
            return "https://app.gmx.io/#/pools"
        if "maverick" in d:
            return f"https://app.mav.xyz/?chain={ch}"
        if "dodo" in d:
            return "https://app.dodoex.io/pools"
        if "wombat" in d:
            return "https://app.wombat.exchange/pool"
        if "yearn" in d:
            return f"https://yearn.fi/vaults/{ch}"
        if "beefy" in d:
            return "https://app.beefy.com/"

        # ── Universal fallback ─────────────────────────────────────────────
        # Avoid direct DefiLlama pool links — their frontend often returns 404.
        # DexScreener pair page for native addresses; chain hub for everything else.
        if pair_address and "-" not in pair_address:
            return f"https://dexscreener.com/{dex_ch}/{pair_address}"
        return f"https://dexscreener.com/{dex_ch}"

    def _pool_result(
        *,
        dex: str, pair_address: str, pool_symbol: str,
        base: str, quote: str,
        chain: str, liquidity: float, volume: float, apr: float,
        url: str, explorer: str, protocol_url: str = "",
        defillama_url: str = "",
    ) -> str:
        # The "url" field is what the AI uses for the "View Pool" button.
        # Always prefer protocol_url (direct link to DEX) over defillama.
        best_url = protocol_url if protocol_url else url
        result = {
            "type":           "liquidity_pool_report",
            "dexId":          dex,
            "pairAddress":    pair_address or "—",
            "poolSymbol":     pool_symbol,
            "baseToken":      base,
            "quoteToken":     quote,
            "chainId":        chain,
            "liquidity_usd":  round(liquidity, 2),
            "volume_24h_usd": round(volume, 2),
            "apr":            round(apr, 2),
            "url":            best_url,
            "explorer_url":   explorer,
            "protocol_url":   protocol_url,
            "defillama_url":  defillama_url,
        }
        logger.info(
            "[Pool] dex=%r chain=%r symbol=%r liq=$%,.0f apr=%.2f%% protocol_url=%r",
            dex, chain, pool_symbol, liquidity, apr, protocol_url,
        )
        return json.dumps(result, indent=2)

    # ── DefiLlama chain name mapping ─────────────────────────────────────────
    # Values must match DefiLlama's "chain" field exactly (case-sensitive).
    # Includes short-form aliases users might pass.
    _LLAMA_CHAIN: dict[str, str] = {
        # Ethereum
        "eth": "Ethereum", "ethereum": "Ethereum",
        # BNB / BSC
        "bsc": "BSC", "bnb": "BSC", "56": "BSC",
        # Polygon
        "polygon": "Polygon", "matic": "Polygon",
        # Others
        "arbitrum": "Arbitrum", "arb": "Arbitrum",
        "optimism": "Optimism", "op": "Optimism",
        "base": "Base",
        "avalanche": "Avalanche", "avax": "Avalanche",
        "solana": "Solana", "sol": "Solana",
        "fantom": "Fantom", "ftm": "Fantom",
        "cronos": "Cronos",
        "celo": "Celo",
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Step 1 — DefiLlama (primary, best TVL accuracy)
    # ─────────────────────────────────────────────────────────────────────────
    pool_found: Optional[str] = None

    try:
        llama_resp = _requests.get("https://yields.llama.fi/pools", timeout=12)
        if llama_resp.ok:
            llama_chain = _LLAMA_CHAIN.get(chain_filter, "")
            pools = llama_resp.json().get("data") or []

            logger.info("[DefiLlama] total pools=%d llama_chain='%s' tokens=%s",
                        len(pools), llama_chain, search_tokens)

            # Filter: chain match + all tokens present in symbol.
            # Skip UUID-addressed pools with zero activity (dead trackers).
            candidates = []
            for pool in pools:
                if llama_chain and pool.get("chain", "") != llama_chain:
                    continue
                sym = pool.get("symbol", "").upper()
                # Exact token-count match: split on both '-' and '/' separators.
                # Prevents 3pool (DAI-USDC-USDT) from matching a 2-token query.
                pool_tokens = sym.replace("/", "-").split("-")
                if len(pool_tokens) != len(search_tokens):
                    continue
                if not all(any(req in pt for pt in pool_tokens) for req in search_tokens):
                    continue
                pool_id = pool.get("pool", "")
                if _is_uuid(pool_id):
                    apr_val = pool.get("apy") or 0
                    vol_val = pool.get("volumeUsd1d") or 0
                    if apr_val == 0 and vol_val == 0:
                        continue  # dead UUID tracker — no yield, no volume
                candidates.append(pool)

            logger.info("[DefiLlama] candidates after filter: %d", len(candidates))

            if candidates:
                # Assign tier-1 trust weight to well-known DEXes (guards against volume wash)
                _TIER1 = {"uniswap", "pancakeswap", "curve", "raydium", "orca",
                           "aerodrome", "camelot", "quickswap", "sushiswap", "balancer"}
                for p in candidates:
                    dex_slug = p.get("project", "").lower()
                    p["_tier1"] = 1 if any(t in dex_slug for t in _TIER1) else 0

                # Anti-scam floor: require at least $100k TVL
                legit = [p for p in candidates if float(p.get("tvlUsd") or 0) >= 100_000]
                if not legit:
                    legit = candidates  # all below floor — still show best

                # Sort: tier-1 DEXes first, then by TVL within each tier
                legit.sort(key=lambda p: (p.get("_tier1", 0), float(p.get("tvlUsd") or 0)), reverse=True)
                best = legit[0]

                # pool field: "0xABC-ethereum", "EPjFW...-solana", or UUID
                raw_pool_id  = best.get("pool", "")
                is_uuid_pool = _is_uuid(raw_pool_id)
                pair_address = _native_address(raw_pool_id, is_uuid_pool)

                pool_sym  = best.get("symbol", "")
                parts     = pool_sym.split("-")
                base_tok  = parts[0].upper() if parts else pool_sym
                quote_tok = "-".join(p.upper() for p in parts[1:]) if len(parts) >= 2 else "—"

                chain_out = chain_filter or best.get("chain", "").lower()
                dex_name  = best.get("project", "—")

                underlying = best.get("underlyingTokens") or []
                tok0 = underlying[0] if len(underlying) > 0 else ""
                tok1 = underlying[1] if len(underlying) > 1 else ""

                dex_chain_id = _DEXSCREENER_CHAIN.get(chain_out, chain_out)
                if not is_uuid_pool and pair_address:
                    explorer = _explorer_url(chain_out, pair_address)
                else:
                    explorer = ""

                # url = direct link to the specific pool on DefiLlama (yellow button)
                defillama_pool_url = (
                    f"https://defillama.com/yields/pool/{raw_pool_id}"
                    if raw_pool_id else "https://defillama.com/yields"
                )

                if not is_uuid_pool:
                    pool_found = _pool_result(
                        dex=dex_name,
                        pair_address=pair_address,
                        pool_symbol=pool_sym,
                        base=base_tok,
                        quote=quote_tok,
                        chain=chain_out,
                        liquidity=float(best.get("tvlUsd") or 0),
                        volume=float(best.get("volumeUsd1d") or 0),
                        apr=float(best.get("apy") or 0),
                        url=defillama_pool_url,
                        explorer=explorer,
                        defillama_url=defillama_pool_url,
                        protocol_url=_protocol_url(
                            dex_name, chain_out,
                            pool_id=raw_pool_id,
                            pair_address=pair_address,
                            token0=tok0,
                            token1=tok1,
                        ),
                    )
                else:
                    logger.info("[DefiLlama] best pool uses UUID id; falling back to DexScreener for native pool address")
        if not pool_found:
            logger.info("[DefiLlama] No matching pools — falling back to DexScreener")
    except Exception as llama_exc:
        logger.warning("[DefiLlama] Error (%s) — falling back to DexScreener", llama_exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Step 2 — DexScreener fallback (meme coins, new tokens)
    # ─────────────────────────────────────────────────────────────────────────
    if not pool_found:
        if len(search_tokens) >= 2:
            anchor_query = f"{search_tokens[0]}/{search_tokens[1]}"
        else:
            anchor_query = search_tokens[0]
        api_query = f"{anchor_query} {chain_filter}" if chain_filter else anchor_query

        logger.info("[DexScreener] query='%s' tokens=%s", api_query, search_tokens)

        try:
            dex_resp = _requests.get(
                "https://api.dexscreener.com/latest/dex/search",
                params={"q": api_query},
                timeout=10,
            )
            if not dex_resp.ok:
                err = dex_resp.text[:300]
                logger.error("[DexScreener] HTTP %d: %s", dex_resp.status_code, err)
            else:
                pairs = dex_resp.json().get("pairs") or []

                # Chain filter
                if chain_filter:
                    pairs = [p for p in pairs if p.get("chainId", "").lower() == chain_filter]

                # Token match filter (substring, handles USDC.e / WBNB variants)
                valid: list = []
                for p in pairs:
                    base_sym  = p.get("baseToken",  {}).get("symbol", "").upper()
                    quote_sym = p.get("quoteToken", {}).get("symbol", "").upper()
                    if all(tok in f"{base_sym} {quote_sym}" for tok in search_tokens):
                        valid.append(p)

                # Sort by liquidity
                valid.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0), reverse=True)

                logger.info("[DexScreener] valid pairs after filter: %d", len(valid))

                if valid:
                    p            = valid[0]
                    chain_out    = p.get("chainId", chain_filter or "—").lower()
                    pair_address = p.get("pairAddress", "")
                    dex_id       = p.get("dexId", "—")
                    base_sym     = p.get("baseToken",  {}).get("symbol", "—")
                    quote_sym    = p.get("quoteToken", {}).get("symbol", "—")
                    pool_found   = _pool_result(
                        dex=dex_id,
                        pair_address=pair_address,
                        pool_symbol=f"{base_sym}-{quote_sym}",
                        base=base_sym,
                        quote=quote_sym,
                        chain=chain_out,
                        liquidity=float((p.get("liquidity") or {}).get("usd") or 0),
                        volume=float((p.get("volume") or {}).get("h24") or 0),
                        apr=0.0,
                        url=p.get("url", ""),
                        explorer=_explorer_url(chain_out, pair_address),
                        protocol_url=_protocol_url(
                            dex_id, chain_out,
                            pair_address=pair_address,
                        ),
                    )
        except Exception as exc:
            logger.exception("[DexScreener] Request failed: %s", exc)

    # ── Final result ─────────────────────────────────────────────────────────
    if pool_found:
        return pool_found

    chain_note = f" on '{chain_filter}'" if chain_filter else ""
    return json.dumps({"error": f"No matching pools found for '{query}'{chain_note}"})


# ---------------------------------------------------------------------------
# Step 3.8 — Universal DexScreener pair search (contract address / token name)
# ---------------------------------------------------------------------------

def search_dexscreener_pairs(query: str) -> str:
    """
    Universal market radar via DexScreener API.

    Input: token contract address (any chain) OR token name/symbol.
    Returns: top-3 trading pairs ranked by 24h volume, with DEX, price, liquidity, and link.
    """
    query = query.strip().strip('"\'')
    if not query:
        return "Error: query is required (contract address or token name)."

    # Smart endpoint routing: contract addresses use /tokens/, text search uses /search
    if query.startswith("0x") or len(query) > 30:
        endpoint = f"https://api.dexscreener.com/latest/dex/tokens/{query}"
    else:
        endpoint = f"https://api.dexscreener.com/latest/dex/search?q={query}"

    try:
        resp = _requests.get(endpoint, timeout=10)
        resp.raise_for_status()
        pairs = resp.json().get("pairs") or []
    except Exception as exc:
        logger.exception("[DexScreener Search] Request failed: %s", exc)
        return f"Error fetching DexScreener data: {exc}"

    if not pairs:
        return f"No trading pairs found for '{query}' on DexScreener."

    # Sort by 24h volume descending, take top-3
    pairs.sort(key=lambda p: float((p.get("volume") or {}).get("h24") or 0), reverse=True)
    top = pairs[:3]

    def _trade_url(dex_id: str, token_address: str, fallback: str) -> str:
        d = dex_id.lower()
        if "raydium" in d:
            return f"https://raydium.io/swap/?outputMint={token_address}"
        if "pump" in d:
            return f"https://pump.fun/{token_address}"
        if "uniswap" in d:
            return f"https://app.uniswap.org/swap?outputCurrency={token_address}"
        if "pancakeswap" in d:
            return f"https://pancakeswap.finance/swap?outputCurrency={token_address}"
        if "meteora" in d:
            return "https://app.meteora.ag/"
        if "orca" in d:
            return "https://www.orca.so/"
        return fallback

    cards = []
    for p in top:
        dex_id       = p.get("dexId", "")
        chain        = p.get("chainId", "")
        base_token   = p.get("baseToken") or {}
        quote_token  = p.get("quoteToken") or {}
        base_sym     = base_token.get("symbol", "?")
        quote_sym    = quote_token.get("symbol", "?")
        base_addr    = base_token.get("address", "")
        ds_url       = p.get("url", "")
        try:
            price_str = f"${float(p.get('priceUsd') or 0):.6f}"
        except (ValueError, TypeError):
            price_str = "N/A"
        liq = float((p.get("liquidity") or {}).get("usd") or 0)
        vol = float((p.get("volume") or {}).get("h24") or 0)

        cards.append({
            "title":       f"{base_sym}/{quote_sym}",
            "subtitle":    f"{dex_id.capitalize()} · {chain.upper()}",
            "details":     {
                "Price":      price_str,
                "Liquidity":  f"${liq:,.0f}",
                "Volume 24h": f"${vol:,.0f}",
            },
            "url":         _trade_url(dex_id, base_addr, ds_url),
            "button_text": "Trade Now",
        })

    return json.dumps({
        "type":    "universal_cards",
        "message": f"🔍 Top {len(cards)} trading pair(s) for **{query}**:",
        "cards":   cards,
    })


# ---------------------------------------------------------------------------
# Step 4 — Agent factory
# ---------------------------------------------------------------------------

def build_agent(
    session_id: str,
    user_address: str,
    chain_id: int,
    openrouter_model: Optional[str] = None,
    solana_address: str = "",
) -> AgentExecutor:
    """
    Returns a ZERO_SHOT_REACT_DESCRIPTION AgentExecutor bound to `session_id`.

    The agent's system prompt injects {chat_history} from ConversationBufferMemory,
    giving the LLM context across turns within the same session.
    """
    llm = _build_llm(openrouter_model)
    memory = _get_or_create_memory(session_id)

    tools = [
        Tool(
            name="get_wallet_balance",
            func=lambda addr: _get_balance_via_portfolio(addr, user_address, solana_address),
            return_direct=True,
            description=(
                "Returns native coin and stablecoin (USDC, USDT) balances. "
                "ONLY use this when user asks for balance. NEVER use before a swap — "
                "build_swap_tx handles balance lookup automatically with amount='all'. "
                "Input: the wallet address (or empty to use connected wallet)."
            ),
        ),
        Tool(
            name="simulate_swap",
            func=lambda raw: _simulate_swap(raw, chain_id),
            description=(
                "Estimates the token output of a swap using price data. "
                "Input: TOKEN_IN TOKEN_OUT [AMOUNT]  "
                "Example: BNB USDT 0.01"
            ),
        ),
        Tool(
            name="get_token_price",
            func=_get_token_price,
            description=(
                "Returns the current USD price of a token. "
                "Input: a symbol like 'BNB', 'BTC', 'ETH', 'USDT' "
                "or a CoinGecko coin ID like 'binancecoin', 'bitcoin'."
            ),
        ),
        Tool(
            name="build_swap_tx",
            func=lambda raw: _build_swap_tx(raw, user_address, chain_id, solana_address),
            description=(
                "Builds a complete, ready-to-sign swap transaction via Enso (EVM) or Jupiter (Solana). "
                "Returns a JSON object the frontend sends to the wallet for signing. "
                "Input: a JSON string with these keys — "
                "chain (evm or solana), "
                "token_in (address/mint or symbol like 'BNB', 'USDT', 'native'), "
                "token_out (address/mint or symbol), "
                "amount (in wei for EVM, base units for Solana, OR 'all' to swap entire balance), "
                "from (sender wallet address; omit to use the user's address), "
                "chain_id (EVM only; omit to use session chain), "
                "slippage_bps (optional, default 100 for EVM / 50 for Solana). "
                "IMPORTANT: When user says 'swap all X' or 'swap my X', set amount to 'all' — "
                "the tool will automatically look up the wallet balance. "
                "Example: {{\"chain\":\"evm\",\"token_in\":\"BNB\",\"token_out\":\"USDT\","
                "\"amount\":\"all\",\"chain_id\":56}}. "
                "Example with specific amount: "
                "{{\"chain\":\"evm\",\"token_in\":\"native\",\"token_out\":\"USDT\","
                "\"amount\":\"10000000000000000\",\"chain_id\":56}}."
            ),
        ),
        Tool(
            name="get_defi_market_overview",
            func=get_defi_market_overview,
            description=(
                "Returns a live macro overview of the DeFi market: total TVL, top-10 blockchains "
                "by TVL, dominance breakdown. Use this for ANY general question about the DeFi "
                "market state, trends, sentiment, or outlook — e.g. 'what do you think about DeFi', "
                "'how is the DeFi market', 'DeFi trends', 'which chain is leading'. "
                "No input needed — pass an empty string."
            ),
        ),
        Tool(
            name="get_defi_analytics",
            func=get_defi_analytics,
            description=(
                "Fetches live DeFi yield data from DefiLlama (no API key needed). "
                "Use this tool whenever the user asks about: earning yield, APY, APR, "
                "best pools, TVL of a protocol, passive income, "
                "'best pools on Y chain', or any question about DeFi strategies. "
                "Input: a query string combining token symbol, chain name, and/or protocol. "
                "Append 'sort:apr' to sort by highest fee APR, or 'sort:apy' to sort by highest APY instead of default TVL. "
                "IMPORTANT: when the user asks for 'highest APR' or 'best APR', you MUST add 'sort:apr'. "
                "When the user asks for 'highest APY', 'best yield', 'top APY', or 'highest return', you MUST add 'sort:apy'. "
                "Examples: 'USDC polygon' (by TVL), 'SOL solana sort:apy' (by APY), "
                "'USDT USDC sort:apr' (highest fee APR for that pair). "
                "Do NOT use this tool for native staking protocol links like 'where can I stake BNB' or 'give me a staking link'. "
                "Note: APY and APR are different metrics. Never claim they are the same or rename numbers that the tool did not return."
            ),
        ),
        Tool(
            name="get_staking_options",
            func=get_staking_options,
            return_direct=True,
            description=(
                "Returns direct staking protocol links for supported native staking assets. "
                "Use this for informational staking questions like 'where can I stake BNB', "
                "'give me a link to stake ETH', 'what staking protocols are supported', or 'where should I stake MATIC'. "
                "Do NOT use get_defi_analytics for these native staking-link questions."
            ),
        ),
        Tool(
            name="search_dexscreener_pairs",
            func=search_dexscreener_pairs,
            description=(
                "Universal token/pair search via DexScreener. "
                "Use this tool when the user provides a CONTRACT ADDRESS (any chain, including Solana) "
                "or asks 'where to trade this token', 'find pairs for <address>', "
                "'is this token listed anywhere', or pastes a raw mint/contract address. "
                "Also use for meme coins and newly launched tokens not found in DefiLlama. "
                "Input: the contract address OR token symbol/name as a plain string. "
                "Returns top-3 pairs ranked by 24h volume with DEX name, chain, price, liquidity, and link."
            ),
        ),
        Tool(
            name="find_liquidity_pool",
            func=find_liquidity_pool,
            description=(
                "Searches DexScreener for liquidity pools by token pair. "
                "Use this tool WHENEVER the user asks for a liquidity pool address, "
                "pair address, pool contract, or wants to know where a token pair trades. "
                "Input: a JSON string with keys — "
                "query (required, token pair e.g. 'USDC USDT' or 'WBNB CAKE'), "
                "chain_id (optional filter: 'bsc', 'ethereum', 'solana', 'polygon', etc.). "
                "Example: {{\"query\":\"USDC USDT\",\"chain_id\":\"bsc\"}}. "
                "Returns top-3 pools sorted by liquidity with dexId, pairAddress, "
                "token symbols, liquidity_usd, and volume_24h_usd."
            ),
        ),
        Tool(
            name="build_solana_swap",
            func=lambda raw: build_solana_swap(raw),
            description=(
                "Builds a ready-to-sign Solana swap transaction using Jupiter API v6 (no fees). "
                "Use this tool WHENEVER the user wants to swap tokens and a Solana/Phantom wallet is connected. "
                "Input: a JSON string with keys — "
                "sell_token (mint address or symbol: 'SOL', 'USDC', 'BONK', etc.), "
                "buy_token (mint address or symbol), "
                "sell_amount (integer in smallest units: 1 SOL = 1000000000, 1 USDC = 1000000), "
                "user_pubkey (the user's Solana wallet public key). "
                "Example: {{\"sell_token\":\"SOL\",\"buy_token\":\"USDC\","
                "\"sell_amount\":500000000,\"user_pubkey\":\"<phantom_pubkey>\"}}. "
                "Returns a JSON with swapTransaction (base64) that the frontend sends to Phantom for signing. "
                "Always show the user the expected out_amount and out_symbol before they sign."
            ),
        ),
        Tool(
            name="build_stake_tx",
            func=lambda raw: _build_stake_tx(raw, user_address, chain_id),
            return_direct=True,
            description=(
                "Builds a staking transaction via Enso. Stake tokens to earn yield. "
                "Use this when user says 'stake ETH', 'stake on Lido', 'stake my BNB'. "
                "Input: a JSON string with these keys - "
                "token (required: 'ETH', 'BNB', 'MATIC'), "
                "protocol (optional: 'lido', 'rocketpool', 'coinbase', 'binance', 'ankr'), "
                "amount (in wei, or 'all' for full balance), "
                "chain_id (optional; native staking chain is auto-detected: ETH->1, BNB->56, MATIC->137). "
                "If user doesn't specify a protocol, the best default is chosen. "
                "Example: {{\"token\":\"ETH\",\"protocol\":\"lido\",\"amount\":\"all\",\"chain_id\":1}}."
            ),
        ),
        Tool(
            name="build_deposit_lp_tx",
            func=lambda raw: _build_deposit_lp_tx(raw, user_address, chain_id),
            return_direct=True,
            description=(
                "Builds a liquidity pool deposit transaction via Enso routing. "
                "Use this when user says 'add liquidity', 'deposit into pool', 'put tokens in LP'. "
                "IMPORTANT: Before calling this tool, you must first find the pool address using "
                "find_liquidity_pool or get_defi_analytics. Then pass the pool's contract address "
                "as pool_address. "
                "Input: a JSON string with these keys - "
                "token_in (required: the token to deposit, e.g. 'USDC'), "
                "pool_address (required: the pool/LP contract address from find_liquidity_pool), "
                "amount (in token's smallest units, or 'all' for full balance), "
                "protocol (optional: protocol name for display, e.g. 'Uniswap V3'), "
                "chain_id (optional, defaults to current chain). "
                "Example: {{\"token_in\":\"USDC\",\"pool_address\":\"0xABC...\",\"amount\":\"5000000\",\"chain_id\":1}}."
            ),
        ),
        Tool(
            name="build_bridge_tx",
            func=lambda raw: _build_bridge_tx(raw, user_address, chain_id, solana_address),
            return_direct=True,
            description=(
                "Builds a cross-chain bridge transaction via deBridge DLN. "
                "Use this when user says 'bridge', 'move tokens to another chain', 'transfer cross-chain'. "
                "Input: a JSON string with these keys - "
                "token_in (required: token symbol like 'USDC', 'ETH', 'BNB', 'SOL'), "
                "token_out (optional: destination token symbol if it should differ from token_in), "
                "amount (in token's smallest units, or 'all' for full balance), "
                "src_chain_id (required: source chain ID, e.g. 1 for Ethereum, 7565164 for Solana), "
                "dst_chain_id (required: destination chain ID, e.g. 42161 for Arbitrum, 8453 for Base, 10 for Optimism, 137 for Polygon, 7565164 for Solana), "
                "recipient (optional: destination address, defaults to same wallet). "
                "Chain IDs: Ethereum=1, BSC=56, Polygon=137, Arbitrum=42161, Base=8453, "
                "Optimism=10, Avalanche=43114, Linea=59144, Fantom=250, Solana=7565164. "
                "For Phantom/Solana bridge requests, use Solana as the source chain when the user is bridging SOL. "
                "Example: {{\"token_in\":\"USDC\",\"amount\":\"5000000\",\"src_chain_id\":1,\"dst_chain_id\":42161}}."
            ),
        ),
        Tool(
            name="build_transfer_tx",
            func=lambda raw: _build_transfer_transaction(raw, chain_id),
            return_direct=True,
            description=(
                "Builds a ready-to-sign token transfer transaction (send / transfer). "
                "Use this IMMEDIATELY when the user wants to send or transfer crypto. "
                "Returns a JSON object with type='transaction' for MetaMask signing. "
                "IMPORTANT: For non-ETH native coins, always include chain_id in the JSON: "
                "AVAX → chain_id 43114, BNB → 56, MATIC → 137, FTM → 250, "
                "MNT → 5000, xDAI → 100, CELO → 42220, CRO → 25. "
                "Input: a JSON string with these keys — "
                "token_symbol (required, e.g. 'AVAX', 'BNB', 'USDT'), "
                "amount (required, float), "
                "to_address (required, recipient 0x… address), "
                "chain_id (required for non-ETH natives, e.g. 43114 for AVAX), "
                "token_address (optional — only for unknown tokens). "
                "Example AVAX: {{\"token_symbol\":\"AVAX\",\"amount\":1.0,\"to_address\":\"0xABC…\",\"chain_id\":43114}}. "
                "Example BNB: {{\"token_symbol\":\"BNB\",\"amount\":0.1,\"to_address\":\"0xABC…\",\"chain_id\":56}}. "
                "Example USDT on ETH: {{\"token_symbol\":\"USDT\",\"amount\":50,\"to_address\":\"0xABC…\"}}."
            ),
        ),
    ]

    agent: AgentExecutor = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        memory=memory,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=25,
        early_stopping_method="generate",
        # Inject system prompt + {chat_history} into ZeroShotAgent's prefix
        agent_kwargs={
            "prefix": _build_system_prompt(chain_id, user_address, solana_address),
            "input_variables": ["input", "chat_history", "agent_scratchpad"],
        },
    )
    return agent
