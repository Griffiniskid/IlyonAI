"""
Shield / Approval Manager module.

Scans wallet token approvals across EVM chains,
scores each approval for risk, and prepares revoke transactions.

Uses direct RPC eth_getLogs to discover ERC-20 Approval events,
eliminating the need for Etherscan-family API keys.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from src.chains.base import ChainType
from src.chains.registry import ChainRegistry
from src.config import settings

logger = logging.getLogger(__name__)

# Known safe spenders (major DEX routers, well-audited protocols)
KNOWN_SAFE_SPENDERS = {
    # Uniswap
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": ("Uniswap V3 Router", "low"),
    "0xe592427a0aece92de3edee1f18e0157c05861564": ("Uniswap V3 Router 2", "low"),
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": ("Uniswap V2 Router", "low"),
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": ("Uniswap Universal Router", "low"),
    # PancakeSwap
    "0x13f4ea83d0bd40e75c8222255bc855a974568dd4": ("PancakeSwap V3", "low"),
    "0x10ed43c718714eb63d5aa57b78b54704e256024e": ("PancakeSwap V2", "low"),
    # 1inch
    "0x1111111254eeb25477b68fb85ed929f73a960582": ("1inch V5", "low"),
    "0x111111125421ca6dc452d289314280a0f8842a65": ("1inch V6", "low"),
    # Aave
    "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2": ("Aave V3 Pool", "low"),
    "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9": ("Aave V2 Pool", "low"),
    # Compound
    "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b": ("Compound Comptroller", "low"),
    # OpenSea
    "0x1e0049783f008a0085193e00003d00cd54003c71": ("OpenSea Conduit", "medium"),
    # Permit2
    "0x000000000022d473030f116ddee9f6b43ac78ba3": ("Uniswap Permit2", "low"),
    # SushiSwap
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": ("SushiSwap Router", "low"),
    # Lido
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": ("Lido stETH", "low"),
    # Curve
    "0x99a58482bd75cbab83b27ec03ca68ff489b5788f": ("Curve Router", "low"),
}

# ERC-20 approve function ABI for encoding revoke transactions
ERC20_APPROVE_SELECTOR = "095ea7b3"  # approve(address,uint256)

# ERC-20 allowance function selector
ERC20_ALLOWANCE_SELECTOR = "dd62ed3e"  # allowance(address,address)

# ERC-20 read selectors for token metadata
ERC20_NAME = "06fdde03"
ERC20_SYMBOL = "95d89b41"
ERC20_DECIMALS = "313ce567"

# Keccak256 of Approval(address,address,uint256)
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

# Block lookback ranges per chain (tuned for public RPC limits)
BLOCK_LOOKBACK = {
    ChainType.ETHEREUM: 50_000,   # ~7 days at 12s blocks
    ChainType.BSC: 100_000,       # ~3.5 days at 3s blocks
    ChainType.POLYGON: 100_000,   # ~2.3 days at 2s blocks
    ChainType.ARBITRUM: 500_000,  # ~1.5 days at 0.25s blocks
    ChainType.BASE: 200_000,      # ~4.6 days at 2s blocks
    ChainType.OPTIMISM: 200_000,  # ~4.6 days at 2s blocks
    ChainType.AVALANCHE: 200_000, # ~4.6 days at 2s blocks
}

# RPC URLs per chain (from config, with defaults)
def _get_rpc_url(chain: ChainType) -> str:
    """Get the RPC URL for a chain from settings."""
    mapping = {
        ChainType.ETHEREUM: settings.ethereum_rpc_url,
        ChainType.BSC: settings.bsc_rpc_url,
        ChainType.POLYGON: settings.polygon_rpc_url,
        ChainType.ARBITRUM: settings.arbitrum_rpc_url,
        ChainType.BASE: settings.base_rpc_url,
        ChainType.OPTIMISM: settings.optimism_rpc_url,
        ChainType.AVALANCHE: settings.avalanche_rpc_url,
    }
    return mapping.get(chain, "")


def encode_revoke_calldata(spender: str) -> str:
    """
    Encode calldata for approve(spender, 0) to revoke an ERC-20 approval.

    Returns hex-encoded calldata.
    """
    selector = ERC20_APPROVE_SELECTOR
    spender_clean = spender.lower().replace("0x", "").zfill(64)
    amount_zero = "0" * 64
    return f"0x{selector}{spender_clean}{amount_zero}"


class ApprovalScanner:
    """
    Scans EVM wallet token approvals and scores each for risk.

    Uses direct RPC eth_getLogs calls instead of Etherscan APIs,
    eliminating the need for block explorer API keys.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._chain_registry = ChainRegistry()
        self._chain_registry.initialize(settings)
        self._token_metadata_cache: Dict[str, Dict[str, Any]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def _rpc_call(self, rpc_url: str, method: str, params: list) -> Any:
        """Make a JSON-RPC call to an EVM node."""
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        try:
            async with session.post(rpc_url, json=payload) as resp:
                data = await resp.json()
                if "error" in data:
                    logger.warning(f"RPC error: {data['error']}")
                    return None
                return data.get("result")
        except Exception as e:
            logger.warning(f"RPC call failed ({method}): {e}")
            return None

    async def _get_current_block(self, rpc_url: str) -> Optional[int]:
        """Get the current block number from the RPC node."""
        result = await self._rpc_call(rpc_url, "eth_blockNumber", [])
        if result:
            return int(result, 16)
        return None

    async def _check_current_allowance(
        self, rpc_url: str, token: str, owner: str, spender: str
    ) -> Optional[int]:
        """Check the current allowance for a token/owner/spender triplet."""
        owner_padded = owner.lower().replace("0x", "").zfill(64)
        spender_padded = spender.lower().replace("0x", "").zfill(64)
        call_data = f"0x{ERC20_ALLOWANCE_SELECTOR}{owner_padded}{spender_padded}"

        result = await self._rpc_call(
            rpc_url,
            "eth_call",
            [{"to": token, "data": call_data}, "latest"],
        )
        if result and result != "0x":
            try:
                return int(result, 16)
            except (ValueError, TypeError):
                return None
        return None

    def _decode_string(self, hex_value: Optional[str]) -> str:
        """Decode ABI-encoded string from hex."""
        if not hex_value or hex_value == "0x" or len(hex_value) < 130:
            return ""
        try:
            hex_clean = hex_value[2:]
            length = int(hex_clean[64:128], 16)
            string_hex = hex_clean[128:128 + length * 2]
            return bytes.fromhex(string_hex).decode("utf-8", errors="ignore").strip("\x00")
        except Exception:
            return ""

    async def _fetch_token_metadata_rpc(
        self, rpc_url: str, token_address: str
    ) -> Dict[str, Any]:
        """Fetch token name, symbol, decimals via RPC eth_call."""
        cache_key = f"rpc:{token_address.lower()}"
        if cache_key in self._token_metadata_cache:
            return self._token_metadata_cache[cache_key]

        name_result, symbol_result, decimals_result = await asyncio.gather(
            self._rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": f"0x{ERC20_NAME}"}, "latest"]),
            self._rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": f"0x{ERC20_SYMBOL}"}, "latest"]),
            self._rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": f"0x{ERC20_DECIMALS}"}, "latest"]),
            return_exceptions=True,
        )

        name = ""
        symbol = ""
        decimals = 18

        if not isinstance(name_result, BaseException) and name_result:
            name = self._decode_string(name_result)
        if not isinstance(symbol_result, BaseException) and symbol_result:
            symbol = self._decode_string(symbol_result)
        if not isinstance(decimals_result, BaseException) and decimals_result:
            try:
                decimals = int(decimals_result, 16)
            except (ValueError, TypeError):
                decimals = 18

        metadata = {
            "token_name": name or None,
            "token_symbol": symbol or None,
            "token_decimals": decimals,
        }
        self._token_metadata_cache[cache_key] = metadata
        return metadata

    async def get_evm_approvals(self, wallet: str, chain: ChainType) -> List[Dict[str, Any]]:
        """
        Fetch ERC-20 Approval events for a wallet on an EVM chain.

        Uses direct RPC eth_getLogs instead of Etherscan APIs.
        No API keys required - works with any public RPC endpoint.
        """
        rpc_url = _get_rpc_url(chain)
        if not rpc_url:
            return []

        # Get current block
        current_block = await self._get_current_block(rpc_url)
        if current_block is None:
            logger.warning(f"Could not get block number for {chain.display_name}")
            return []

        # Calculate from_block based on chain-specific lookback
        lookback = BLOCK_LOOKBACK.get(chain, 50_000)
        from_block = max(0, current_block - lookback)

        # Pad wallet address to 32 bytes for topic filter
        wallet_topic = "0x" + wallet.lower().replace("0x", "").zfill(64)

        # Query eth_getLogs for Approval events where wallet is the owner
        log_params = [{
            "fromBlock": hex(from_block),
            "toBlock": "latest",
            "topics": [APPROVAL_TOPIC, wallet_topic],
        }]

        logs = await self._rpc_call(rpc_url, "eth_getLogs", log_params)
        if not logs or not isinstance(logs, list):
            return []

        # Deduplicate by token:spender (keep latest approval)
        approval_map: Dict[str, Dict[str, Any]] = {}

        for log in logs:
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue

            token_address = log.get("address", "").lower()
            spender = "0x" + topics[2][-40:]
            data_hex = log.get("data", "0x")

            # Parse allowance from event data
            try:
                amount_int = int(data_hex, 16) if data_hex and data_hex != "0x" else 0
            except (ValueError, TypeError):
                amount_int = 0

            # Skip zero approvals (revocations)
            if amount_int == 0:
                # Remove from map if previously tracked
                key = f"{token_address}:{spender}"
                approval_map.pop(key, None)
                continue

            allowance = "unlimited" if amount_int >= 2**200 else str(amount_int)
            block_number = int(log.get("blockNumber", "0x0"), 16)

            key = f"{token_address}:{spender}"
            approval_map[key] = {
                "token_address": token_address,
                "spender_address": spender,
                "allowance": allowance,
                "allowance_raw": amount_int,
                "block_number": block_number,
                "chain": chain.value,
                "chain_name": chain.display_name,
            }

        if not approval_map:
            return []

        # Verify current allowances (filter out already-revoked approvals)
        verified_approvals = []
        verify_tasks = []

        for key, approval in approval_map.items():
            verify_tasks.append(
                self._check_current_allowance(
                    rpc_url,
                    approval["token_address"],
                    wallet,
                    approval["spender_address"],
                )
            )

        verify_results = await asyncio.gather(*verify_tasks, return_exceptions=True)

        for (key, approval), result in zip(approval_map.items(), verify_results):
            if isinstance(result, Exception) or result is None:
                # If we can't verify, include it with a note
                approval["verified"] = False
                verified_approvals.append(approval)
            elif result > 0:
                # Active approval - update allowance to current value
                approval["verified"] = True
                approval["allowance_raw"] = result
                approval["allowance"] = "unlimited" if result >= 2**200 else str(result)
                verified_approvals.append(approval)
            # If result == 0, approval has been revoked - skip it

        # Fetch token metadata for discovered approvals
        unique_tokens = {a["token_address"] for a in verified_approvals}
        metadata_tasks = {
            token: self._fetch_token_metadata_rpc(rpc_url, token)
            for token in unique_tokens
        }
        metadata_results = await asyncio.gather(
            *metadata_tasks.values(), return_exceptions=True
        )
        token_metadata = {}
        for token, result in zip(metadata_tasks.keys(), metadata_results):
            if not isinstance(result, Exception):
                token_metadata[token] = result

        # Enrich approvals with metadata
        for approval in verified_approvals:
            meta = token_metadata.get(approval["token_address"], {})
            approval["token_name"] = meta.get("token_name")
            approval["token_symbol"] = meta.get("token_symbol")
            approval["token_decimals"] = meta.get("token_decimals", 18)

            # Calculate human-readable allowance
            if approval["allowance"] != "unlimited":
                try:
                    decimals = approval["token_decimals"]
                    raw = approval["allowance_raw"]
                    approval["allowance_formatted"] = f"{raw / (10 ** decimals):.4f}"
                except (ValueError, ZeroDivisionError):
                    approval["allowance_formatted"] = approval["allowance"]
            else:
                approval["allowance_formatted"] = "Unlimited"

        return verified_approvals

    def score_approval(
        self, approval: Dict[str, Any], spender_verified: bool = False
    ) -> Dict[str, Any]:
        """
        Score an approval 0-100 for risk (higher = more risky).

        Factors:
        - Unknown/unverified spender contract
        - Unlimited allowance amount
        - Known safe protocols reduce risk
        - Token symbol for context
        """
        spender = approval.get("spender_address", "").lower()
        allowance = approval.get("allowance", "unknown")
        token_symbol = approval.get("token_symbol") or "Unknown"

        risk_score = 50
        risk_reasons = []
        spender_name = None
        is_known_safe = False

        # Check against known safe list
        if spender in KNOWN_SAFE_SPENDERS:
            spender_name, risk_tier = KNOWN_SAFE_SPENDERS[spender]
            if risk_tier == "low":
                risk_score = 15
                is_known_safe = True
            elif risk_tier == "medium":
                risk_score = 35
        elif spender_verified:
            risk_score = 40
        else:
            risk_score = 65
            risk_reasons.append("Spender contract is unverified")

        # Unlimited allowance increases risk
        if allowance == "unlimited" and not is_known_safe:
            risk_score += 20
            risk_reasons.append(f"Unlimited {token_symbol} approval granted")

        # Old approvals (high block distance from current) get risk bump
        block_number = approval.get("block_number", 0)
        if block_number > 0 and not is_known_safe:
            # This is a heuristic - older approvals may be forgotten
            risk_reasons.append("Review old approvals regularly")

        risk_score = min(100, max(0, risk_score))

        if risk_score >= 70:
            risk_level = "HIGH"
        elif risk_score >= 50:
            risk_level = "MEDIUM"
        elif risk_score >= 25:
            risk_level = "LOW"
        else:
            risk_level = "LOW"

        return {
            **approval,
            "spender_name": spender_name,
            "spender_is_verified": spender_verified or is_known_safe,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
        }

    async def scan_wallet(
        self, wallet: str, chains: Optional[List[ChainType]] = None
    ) -> List[Dict[str, Any]]:
        """
        Scan a wallet's approvals across multiple chains.
        """
        if chains is None:
            chains = [
                ChainType.ETHEREUM, ChainType.BSC, ChainType.POLYGON,
                ChainType.ARBITRUM, ChainType.BASE, ChainType.OPTIMISM,
                ChainType.AVALANCHE
            ]

        all_approvals = []

        evm_chains = [chain for chain in chains if chain != ChainType.SOLANA]
        tasks = [self.get_evm_approvals(wallet, chain) for chain in evm_chains]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for chain, result in zip(evm_chains, results):
            if isinstance(result, Exception):
                logger.warning(f"Approval scan failed for {chain.value}: {result}")
                continue
            if not isinstance(result, list):
                continue
            for approval in result:
                scored = self.score_approval(approval)
                all_approvals.append(scored)

        # Sort by risk score descending
        all_approvals.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        return all_approvals

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
