"""
Smart contract scanner module.

Fetches contract source/bytecode, runs static analysis,
pattern-matches against known scam templates, and runs AI audit.
"""

import asyncio
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional

import aiohttp

from src.chains.base import ChainType, EVM_CHAIN_CONFIGS
from src.config import settings

logger = logging.getLogger(__name__)

# ─── Known vulnerability bytecode selectors (4-byte function selectors) ───────
RISK_SELECTORS = {
    # Ownership / access control
    "f2fde38b": ("transferOwnership", "medium", "Owner can be transferred"),
    "715018a6": ("renounceOwnership", "info", "Ownership can be renounced"),
    "8da5cb5b": ("owner", "info", "Has owner function"),
    # Minting
    "40c10f19": ("mint", "high", "Can mint new tokens"),
    "a9059cbb": ("transfer", "info", "Standard transfer"),
    # Blacklisting
    "f9f92be4": ("blacklist", "high", "Can blacklist addresses"),
    "44337ea1": ("addBlacklist", "high", "Can add to blacklist"),
    "537df3b6": ("excludeFromFee", "medium", "Can exclude from fees"),
    # Pausing
    "8456cb59": ("pause", "high", "Can pause transfers"),
    "3f4ba83a": ("unpause", "medium", "Can unpause transfers"),
    # Fee manipulation
    "b2bdfa7b": ("setFee", "high", "Can change fees dynamically"),
    "4a62bb65": ("paused", "info", "Has pause state"),
    # Proxy / upgradeability
    "3659cfe6": ("upgradeTo", "critical", "Contract is upgradeable"),
    "4f1ef286": ("upgradeToAndCall", "critical", "Contract is upgradeable (with call)"),
}

# ─── Known scam contract bytecode hashes ──────────────────────────────────────
KNOWN_SCAM_HASHES: Dict[str, str] = {
    # These would be populated from a real database in production
    # Format: "bytecode_hash": "description"
}

# ─── Vulnerability patterns in source code ───────────────────────────────────
SOURCE_PATTERNS = [
    # Reentrancy
    (r"\.call\.value\(", "critical", "Reentrancy risk: raw .call.value() used"),
    (r"\.send\(", "medium", "Low-level .send() call — check for reentrancy"),
    # Unchecked return values
    (r"\.call\{", "medium", "Low-level .call — return value should be checked"),
    # tx.origin auth
    (r"tx\.origin", "high", "tx.origin used for authorization — phishing risk"),
    # Selfdestruct
    (r"selfdestruct", "critical", "Contract can self-destruct"),
    (r"suicide\(", "critical", "Contract can self-destruct (deprecated syntax)"),
    # Timestamp dependence
    (r"block\.timestamp", "low", "Timestamp dependence — miner can manipulate"),
    (r"now\b", "low", "Deprecated 'now' alias — timestamp dependence"),
    # Integer overflow (pre-SafeMath)
    (r"\+\+\w+\s*;", "info", "Increment operation — verify SafeMath usage"),
    # Hidden minting
    (r"_mint\s*\(", "medium", "Internal _mint call — check access controls"),
    # Unlimited approvals
    (r"approve\s*\(\s*\w+\s*,\s*type\s*\(\s*uint256\s*\)\s*\.max", "medium",
     "Unlimited approval pattern"),
]


class ContractScanner:
    """
    AI-powered smart contract security scanner.

    For verified contracts: fetches source from Etherscan-family APIs,
    runs pattern analysis, and sends to AI for deep audit.

    For unverified contracts: decompiles bytecode and checks function selectors.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    def _get_explorer_api(self, chain: ChainType) -> tuple[str, str]:
        """Returns (api_url, api_key) for the given chain's block explorer."""
        configs = {
            ChainType.ETHEREUM: (
                "https://api.etherscan.io/api",
                settings.etherscan_api_key or ""
            ),
            ChainType.BSC: (
                "https://api.bscscan.com/api",
                settings.bscscan_api_key or ""
            ),
            ChainType.POLYGON: (
                "https://api.polygonscan.com/api",
                settings.polygonscan_api_key or ""
            ),
            ChainType.ARBITRUM: (
                "https://api.arbiscan.io/api",
                settings.arbiscan_api_key or ""
            ),
            ChainType.BASE: (
                "https://api.basescan.org/api",
                settings.basescan_api_key or ""
            ),
            ChainType.OPTIMISM: (
                "https://api-optimistic.etherscan.io/api",
                settings.optimism_etherscan_api_key or ""
            ),
            ChainType.AVALANCHE: (
                "https://api.snowtrace.io/api",
                settings.snowtrace_api_key or ""
            ),
        }
        return configs.get(chain, ("", ""))

    async def get_contract_source(
        self, address: str, chain: ChainType
    ) -> Dict[str, Any]:
        """
        Fetch contract source code and ABI from block explorer.

        Returns dict with: source_code, abi, name, compiler_version,
        is_verified, license, constructor_args, proxy_info
        """
        api_url, api_key = self._get_explorer_api(chain)
        if not api_url:
            return {"is_verified": False, "source_code": "", "name": ""}

        session = await self._get_session()
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": api_key or "YourApiKeyToken",
        }

        try:
            async with session.get(api_url, params=params) as resp:
                data = await resp.json()

            if data.get("status") != "1" or not data.get("result"):
                return {"is_verified": False, "source_code": "", "name": ""}

            result = data["result"][0]
            source = result.get("SourceCode", "")

            # Detect proxy
            is_proxy = result.get("Proxy", "0") == "1"
            impl = result.get("Implementation", "")

            return {
                "is_verified": bool(source),
                "source_code": source,
                "abi": result.get("ABI", ""),
                "name": result.get("ContractName", ""),
                "compiler_version": result.get("CompilerVersion", ""),
                "license": result.get("LicenseType", ""),
                "constructor_args": result.get("ConstructorArguments", ""),
                "is_proxy": is_proxy,
                "proxy_implementation": impl or None,
                "optimization_used": result.get("OptimizationUsed") == "1",
            }

        except Exception as e:
            logger.warning(f"Failed to fetch contract source for {address}: {e}")
            return {"is_verified": False, "source_code": "", "name": ""}

    async def get_bytecode(self, address: str, chain: ChainType) -> str:
        """Fetch raw contract bytecode via RPC."""
        try:
            from src.chains.registry import ChainRegistry
            registry = ChainRegistry()
            registry.initialize(settings)
            client = registry.get_client(chain)
            if client and hasattr(client, "_rpc_call"):
                rpc_call = getattr(client, "_rpc_call")
                code = await rpc_call("eth_getCode", [address, "latest"])
                if isinstance(code, str):
                    return code
        except Exception as e:
            logger.warning(f"Failed to fetch bytecode for {address}: {e}")
        return ""

    def analyze_bytecode(self, bytecode: str) -> List[Dict[str, Any]]:
        """
        Analyze raw bytecode for risk indicators.

        Checks function selectors against known risky functions.
        """
        findings = []
        if not bytecode or bytecode == "0x":
            return findings

        # Extract 4-byte selectors from bytecode
        # Selectors appear as PUSH4 instructions (0x63) followed by 4 bytes
        bytecode_hex = bytecode.lower().replace("0x", "")

        for selector, (func_name, severity, description) in RISK_SELECTORS.items():
            if selector in bytecode_hex:
                findings.append({
                    "severity": severity,
                    "title": f"Function: {func_name}()",
                    "description": description,
                    "line_number": None,
                    "code_snippet": f"// Selector: 0x{selector}",
                    "recommendation": f"Verify that {func_name} has appropriate access controls."
                })

        return findings

    def analyze_source_code(self, source_code: str) -> List[Dict[str, Any]]:
        """
        Analyze Solidity source code for vulnerability patterns.
        """
        findings = []
        if not source_code:
            return findings

        lines = source_code.split("\n")
        for i, line in enumerate(lines, 1):
            for pattern, severity, description in SOURCE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "severity": severity,
                        "title": description.split("—")[0].strip(),
                        "description": description,
                        "line_number": i,
                        "code_snippet": line.strip()[:200],
                        "recommendation": "Review and add appropriate guards."
                    })

        return findings

    def check_similarity(self, bytecode: str) -> tuple[bool, float, Optional[str]]:
        """
        Check if bytecode matches known scam templates.

        Returns: (is_similar, similarity_score, description)
        """
        if not bytecode:
            return False, 0.0, None

        # Hash the bytecode (excluding metadata suffix)
        # Solidity appends CBOR metadata at end, strip it
        bytecode_clean = bytecode.replace("0x", "")
        if len(bytecode_clean) > 86:  # CBOR is typically 43 bytes
            bytecode_clean = bytecode_clean[:-86]

        hash_val = hashlib.sha256(bytes.fromhex(bytecode_clean)).hexdigest()[:16]

        if hash_val in KNOWN_SCAM_HASHES:
            return True, 1.0, KNOWN_SCAM_HASHES[hash_val]

        return False, 0.0, None

    async def scan(
        self, address: str, chain: ChainType
    ) -> Dict[str, Any]:
        """
        Full contract scan: source fetch + static analysis + similarity check.

        Returns structured scan result ready for AI audit and API response.
        """
        start_time = time.time()
        logger.info(f"Scanning contract {address[:8]}... on {chain.display_name}")

        result = {
            "address": address,
            "chain": chain.value,
            "name": None,
            "is_verified": False,
            "compiler_version": None,
            "license": None,
            "is_proxy": False,
            "proxy_implementation": None,
            "vulnerabilities": [],
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "source_code": "",
            "similar_to_scam": False,
            "similarity_score": 0.0,
            "similar_contract_info": None,
            "scan_duration_ms": 0,
        }

        # Step 1: Fetch source code
        if chain != ChainType.SOLANA:
            source_info = await self.get_contract_source(address, chain)
            result.update({
                "is_verified": source_info.get("is_verified", False),
                "name": source_info.get("name"),
                "compiler_version": source_info.get("compiler_version"),
                "license": source_info.get("license"),
                "is_proxy": source_info.get("is_proxy", False),
                "proxy_implementation": source_info.get("proxy_implementation"),
                "source_code": source_info.get("source_code", ""),
            })

            # Step 2: Source code analysis
            if source_info.get("source_code"):
                vulns = self.analyze_source_code(source_info["source_code"])
                result["vulnerabilities"].extend(vulns)

        # Step 3: Bytecode analysis
        bytecode = await self.get_bytecode(address, chain)
        if bytecode:
            bytecode_vulns = self.analyze_bytecode(bytecode)
            # Deduplicate against source findings
            existing_titles = {v["title"] for v in result["vulnerabilities"]}
            for v in bytecode_vulns:
                if v["title"] not in existing_titles:
                    result["vulnerabilities"].append(v)

            # Step 4: Similarity check
            is_similar, sim_score, sim_info = self.check_similarity(bytecode)
            result["similar_to_scam"] = is_similar
            result["similarity_score"] = sim_score
            result["similar_contract_info"] = sim_info

        # Count by severity
        for v in result["vulnerabilities"]:
            sev = v.get("severity", "").lower()
            if sev == "critical":
                result["critical_count"] += 1
            elif sev == "high":
                result["high_count"] += 1
            elif sev == "medium":
                result["medium_count"] += 1
            elif sev == "low":
                result["low_count"] += 1

        result["scan_duration_ms"] = int((time.time() - start_time) * 1000)
        logger.info(
            f"Contract scan complete for {address[:8]}: "
            f"verified={result['is_verified']}, "
            f"vulns={len(result['vulnerabilities'])}"
        )

        return result

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
