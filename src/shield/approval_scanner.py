"""
Shield / Approval Manager module.

Scans wallet token approvals across EVM chains and Solana,
scores each approval for risk, and prepares revoke transactions.
"""

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
}

# ERC-20 approve function ABI for encoding revoke transactions
ERC20_APPROVE_SELECTOR = "095ea7b3"  # approve(address,uint256)


def encode_revoke_calldata(spender: str) -> str:
    """
    Encode calldata for approve(spender, 0) to revoke an ERC-20 approval.

    Returns hex-encoded calldata.
    """
    # Function selector: approve(address,uint256)
    selector = ERC20_APPROVE_SELECTOR
    # ABI-encode spender address (padded to 32 bytes)
    spender_clean = spender.lower().replace("0x", "").zfill(64)
    # Amount = 0, padded to 32 bytes
    amount_zero = "0" * 64
    return f"0x{selector}{spender_clean}{amount_zero}"


class ApprovalScanner:
    """
    Scans EVM wallet token approvals and scores each for risk.
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

    def _get_explorer_api(self, chain: ChainType) -> tuple[str, str]:
        """Returns (api_url, api_key) for Etherscan-family explorer."""
        configs = {
            ChainType.ETHEREUM: ("https://api.etherscan.io/api", settings.etherscan_api_key or ""),
            ChainType.BSC: ("https://api.bscscan.com/api", settings.bscscan_api_key or ""),
            ChainType.POLYGON: ("https://api.polygonscan.com/api", settings.polygonscan_api_key or ""),
            ChainType.ARBITRUM: ("https://api.arbiscan.io/api", settings.arbiscan_api_key or ""),
            ChainType.BASE: ("https://api.basescan.org/api", settings.basescan_api_key or ""),
            ChainType.OPTIMISM: ("https://api-optimistic.etherscan.io/api", settings.optimism_etherscan_api_key or ""),
            ChainType.AVALANCHE: ("https://api.snowtrace.io/api", settings.snowtrace_api_key or ""),
        }
        return configs.get(chain, ("", ""))

    async def get_evm_approvals(self, wallet: str, chain: ChainType) -> List[Dict[str, Any]]:
        """
        Fetch ERC-20 Approval events for a wallet on an EVM chain.

        Uses Etherscan-family API to get Transfer and Approval event logs.
        """
        api_url, api_key = self._get_explorer_api(chain)
        if not api_url:
            return []

        if not api_key:
            logger.info(f"No API key configured for {chain.display_name}, skipping scan")
            return []

        session = await self._get_session()

        # Keccak256 of Approval(address,address,uint256)
        approval_topic = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
        # Pad wallet address to 32 bytes for topic filter
        wallet_topic = "0x" + wallet.lower().replace("0x", "").zfill(64)

        params = {
            "module": "logs",
            "action": "getLogs",
            "fromBlock": "0",
            "toBlock": "latest",
            "topic0": approval_topic,
            "topic1": wallet_topic,
            "apikey": api_key,
        }

        try:
            async with session.get(api_url, params=params) as resp:
                data = await resp.json()

            if data.get("status") != "1":
                return []

            logs = data.get("result", [])
            approvals = {}

            for log in logs:
                topics = log.get("topics", [])
                if len(topics) < 3:
                    continue

                token_address = log.get("address", "").lower()
                spender = "0x" + topics[2][-40:]  # Last 20 bytes of topic[2]
                data_hex = log.get("data", "0x")

                # Parse allowance amount
                try:
                    amount_int = int(data_hex, 16)
                    allowance = "unlimited" if amount_int >= 2**200 else str(amount_int)
                except Exception:
                    allowance = "unknown"

                key = f"{token_address}:{spender}"
                approvals[key] = {
                    "token_address": token_address,
                    "spender_address": spender,
                    "allowance": allowance,
                    "block_number": int(log.get("blockNumber", "0x0"), 16),
                    "chain": chain.value,
                }

            return list(approvals.values())

        except Exception as e:
            logger.warning(f"Failed to fetch approvals for {wallet} on {chain.display_name}: {e}")
            return []

    def score_approval(
        self, approval: Dict[str, Any], spender_verified: bool = False
    ) -> Dict[str, Any]:
        """
        Score an approval 0-100 for risk (higher = more risky).

        Factors:
        - Unknown/unverified spender contract
        - Unlimited allowance amount
        - Known safe protocols reduce risk
        """
        spender = approval.get("spender_address", "").lower()
        allowance = approval.get("allowance", "unknown")

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
            risk_reasons.append("Unlimited token approval granted")

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

    async def _get_token_metadata(self, token_address: str, chain: ChainType) -> Dict[str, Any]:
        """Fetch token metadata once per chain/address pair."""
        cache_key = f"{chain.value}:{token_address.lower()}"
        if cache_key in self._token_metadata_cache:
            return self._token_metadata_cache[cache_key]

        metadata: Dict[str, Any] = {
            "token_symbol": None,
            "token_name": None,
            "token_logo": None,
        }

        try:
            client = self._chain_registry.get_client(chain)
            info = await client.get_token_info(token_address)
            metadata.update({
                "token_symbol": info.get("symbol") or None,
                "token_name": info.get("name") or None,
            })
        except Exception as e:
            logger.debug(
                "Token metadata lookup failed for %s on %s: %s",
                token_address,
                chain.value,
                e,
            )

        self._token_metadata_cache[cache_key] = metadata
        return metadata

    async def _enrich_approval(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        """Attach token metadata to an approval when available."""
        token_address = approval.get("token_address")
        chain_name = approval.get("chain")
        if not token_address or not chain_name:
            return approval

        try:
            chain = ChainType(str(chain_name))
        except ValueError:
            return approval

        metadata = await self._get_token_metadata(token_address, chain)
        return {
            **approval,
            **metadata,
        }

    async def scan_wallet(
        self, wallet: str, chains: Optional[List[ChainType]] = None
    ) -> List[Dict[str, Any]]:
        """
        Scan a wallet's approvals across multiple chains.
        """
        if chains is None:
            # Default: scan all EVM chains
            chains = [
                ChainType.ETHEREUM, ChainType.BSC, ChainType.POLYGON,
                ChainType.ARBITRUM, ChainType.BASE, ChainType.OPTIMISM,
                ChainType.AVALANCHE
            ]

        all_approvals = []

        import asyncio
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

        if all_approvals:
            enriched_results = await asyncio.gather(
                *(self._enrich_approval(approval) for approval in all_approvals),
                return_exceptions=True,
            )
            all_approvals = [
                approval if isinstance(approval, dict) else original
                for original, approval in zip(all_approvals, enriched_results)
            ]

        # Sort by risk score descending
        all_approvals.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        return all_approvals

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
