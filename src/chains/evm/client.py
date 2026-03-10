"""
EVM chain client - unified client for all EVM-compatible blockchains.

Supports Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche
through a single client implementation that adapts to each chain's specifics.
"""

import logging
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

import aiohttp

from src.chains.base import ChainClient, ChainConfig, ChainType

logger = logging.getLogger(__name__)

# Standard ERC-20 ABI fragments needed for token analysis
ERC20_BALANCE_OF = "0x70a08231"  # balanceOf(address)
ERC20_TOTAL_SUPPLY = "0x18160ddd"  # totalSupply()
ERC20_DECIMALS = "0x313ce567"  # decimals()
ERC20_NAME = "0x06fdde03"  # name()
ERC20_SYMBOL = "0x95d89b41"  # symbol()
ERC20_OWNER = "0x8da5cb5b"  # owner()
ERC20_ALLOWANCE = "0xdd62ed3e"  # allowance(address,address)

# Common function signatures for risk detection
MINT_SIGNATURES = [
    "0x40c10f19",  # mint(address,uint256)
    "0xa0712d68",  # mint(uint256)
    "0x4e6ec247",  # _mint(address,uint256)
]
BLACKLIST_SIGNATURES = [
    "0x44337ea1",  # blacklist(address)
    "0xf9f92be4",  # blacklistAddress(address)
    "0x0ecb93c0",  # blacklistAccount(address)
]
PAUSE_SIGNATURES = [
    "0x8456cb59",  # pause()
    "0x3f4ba83a",  # unpause()
]


class EVMChainClient(ChainClient):
    """
    EVM chain client implementing the unified ChainClient interface.

    Works with any EVM-compatible chain by adapting to the chain config.
    Uses JSON-RPC for on-chain data and Etherscan-family APIs for
    contract source code and transaction history.
    """

    def __init__(self, config: ChainConfig):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def _rpc_call(self, method: str, params: Optional[list] = None) -> Any:
        """Make a JSON-RPC call to the chain's RPC endpoint."""
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1,
        }
        try:
            async with session.post(self.config.rpc_url, json=payload) as resp:
                data = await resp.json()
                if "error" in data:
                    logger.warning(f"RPC error on {self.chain_type.value}: {data['error']}")
                    return None
                return data.get("result")
        except Exception as e:
            logger.error(f"RPC call failed on {self.chain_type.value}: {e}")
            return None

    async def _eth_call(self, to: str, data: str, block: str = "latest") -> Optional[str]:
        """Execute eth_call (read-only contract interaction)."""
        result = await self._rpc_call("eth_call", [{"to": to, "data": data}, block])
        return result

    async def _explorer_api_call(self, params: Dict[str, str]) -> Optional[Dict]:
        """Make a call to the Etherscan-family block explorer API."""
        if not self.config.explorer_api_url:
            return None

        session = await self._get_session()
        if self.config.explorer_api_key:
            params["apikey"] = self.config.explorer_api_key

        try:
            async with session.get(self.config.explorer_api_url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "1" or data.get("message") == "OK":
                        return data
                    return data  # Return anyway, caller handles
                return None
        except Exception as e:
            logger.warning(f"Explorer API call failed on {self.chain_type.value}: {e}")
            return None

    def _decode_uint256(self, hex_value: Optional[str]) -> int:
        """Decode a hex-encoded uint256 value."""
        if not hex_value or hex_value == "0x":
            return 0
        try:
            return int(hex_value, 16)
        except (ValueError, TypeError):
            return 0

    def _decode_string(self, hex_value: Optional[str]) -> str:
        """Decode a hex-encoded string (ABI-encoded)."""
        if not hex_value or hex_value == "0x" or len(hex_value) < 130:
            return ""
        try:
            # ABI-encoded string: offset (32 bytes) + length (32 bytes) + data
            hex_clean = hex_value[2:]  # Remove 0x
            # Skip offset (64 hex chars), read length
            length = int(hex_clean[64:128], 16)
            # Read string data
            string_hex = hex_clean[128:128 + length * 2]
            return bytes.fromhex(string_hex).decode("utf-8", errors="ignore").strip("\x00")
        except Exception:
            return ""

    async def get_token_info(self, address: str) -> Dict[str, Any]:
        """Get ERC-20 token information via eth_call."""
        address = address.lower()

        # Parallel calls for name, symbol, decimals, totalSupply, owner
        import asyncio
        results = await asyncio.gather(
            self._eth_call(address, ERC20_NAME),
            self._eth_call(address, ERC20_SYMBOL),
            self._eth_call(address, ERC20_DECIMALS),
            self._eth_call(address, ERC20_TOTAL_SUPPLY),
            self._eth_call(address, ERC20_OWNER),
            return_exceptions=True,
        )

        name_result, symbol_result, decimals_result, supply_result, owner_result = results

        _name_hex: Optional[str] = None if isinstance(name_result, BaseException) else name_result
        _symbol_hex: Optional[str] = None if isinstance(symbol_result, BaseException) else symbol_result
        _decimals_hex: Optional[str] = None if isinstance(decimals_result, BaseException) else decimals_result
        _supply_hex: Optional[str] = None if isinstance(supply_result, BaseException) else supply_result
        _owner_hex: Optional[str] = None if isinstance(owner_result, BaseException) else owner_result

        name = self._decode_string(_name_hex) or ""
        symbol = self._decode_string(_symbol_hex) or ""
        decimals = self._decode_uint256(_decimals_hex) if _decimals_hex else 18
        total_supply = self._decode_uint256(_supply_hex) if _supply_hex else 0
        owner = None
        if _owner_hex and _owner_hex != "0x" and len(_owner_hex) >= 66:
            owner_hex = "0x" + _owner_hex[-40:]
            if owner_hex != "0x" + "0" * 40:
                owner = owner_hex

        # Check for bytecode (is it a contract?)
        code = await self._rpc_call("eth_getCode", [address, "latest"])
        is_contract = code and code != "0x" and len(code) > 2

        # Check for proxy pattern (EIP-1967)
        is_proxy = False
        implementation = None
        if is_contract:
            # EIP-1967 implementation slot
            impl_slot = await self._rpc_call(
                "eth_getStorageAt",
                [address, "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc", "latest"]
            )
            if impl_slot and impl_slot != "0x" + "0" * 64:
                impl_addr = "0x" + impl_slot[-40:]
                if impl_addr != "0x" + "0" * 40:
                    is_proxy = True
                    implementation = impl_addr

        # Detect risk functions by checking bytecode for known selectors
        bytecode = code or ""
        can_mint = any(sig[2:] in bytecode.lower() for sig in MINT_SIGNATURES)
        can_blacklist = any(sig[2:] in bytecode.lower() for sig in BLACKLIST_SIGNATURES)
        can_pause = any(sig[2:] in bytecode.lower() for sig in PAUSE_SIGNATURES)

        # Is ownership renounced?
        is_renounced = owner is None or owner == "0x" + "0" * 40

        contract_info = await self.get_contract_code(address)
        compiler_version = None
        is_verified = None
        is_open_source = None
        proxy_implementation = implementation

        if contract_info:
            compiler_version = contract_info.get("compiler_version") or None
            is_verified = contract_info.get("is_verified")
            is_open_source = bool(contract_info.get("source_code"))
            if contract_info.get("implementation_address"):
                proxy_implementation = contract_info.get("implementation_address")

        human_supply = total_supply / (10 ** decimals) if decimals > 0 else total_supply

        return {
            "name": name,
            "symbol": symbol,
            "decimals": decimals,
            "supply": human_supply,
            "total_supply": human_supply,
            "total_supply_raw": total_supply,
            "owner": owner,
            "is_contract": is_contract,
            "is_proxy": is_proxy,
            "implementation": proxy_implementation,
            "proxy_implementation": proxy_implementation,
            "is_renounced": is_renounced,
            "can_mint": can_mint,
            "can_blacklist": can_blacklist,
            "can_pause": can_pause,
            "has_owner_function": owner is not None,
            "transfer_pausable": can_pause,
            "is_verified": is_verified,
            "is_open_source": is_open_source,
            "compiler_version": compiler_version,
            "bytecode_length": len(bytecode) // 2 if bytecode else 0,
        }

    async def get_top_holders(self, address: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top token holders.

        Uses Etherscan-family API for holder data. Falls back to
        empty list if API not available.
        """
        # Try explorer API first
        data = await self._explorer_api_call({
            "module": "token",
            "action": "tokenholderlist",
            "contractaddress": address,
            "page": "1",
            "offset": str(limit),
        })

        if data and data.get("result") and isinstance(data["result"], list):
            holders = []
            for h in data["result"][:limit]:
                holders.append({
                    "address": h.get("TokenHolderAddress", ""),
                    "balance": float(h.get("TokenHolderQuantity", 0)),
                    "percentage": float(h.get("percentage", 0)),
                })
            return holders

        return []

    async def get_contract_code(self, address: str) -> Optional[Dict[str, Any]]:
        """Get verified contract source code from block explorer."""
        data = await self._explorer_api_call({
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
        })

        if not data or not data.get("result"):
            return None

        result = data["result"]
        if isinstance(result, list) and len(result) > 0:
            contract = result[0]
            source_code = contract.get("SourceCode", "")
            is_verified = bool(source_code and source_code != "")

            abi = contract.get("ABI", "")
            if abi == "Contract source code not verified":
                abi = ""
                is_verified = False

            # Check if proxy
            is_proxy = contract.get("Proxy", "0") == "1"
            implementation = contract.get("Implementation", "") or None

            return {
                "source_code": source_code if is_verified else None,
                "abi": abi,
                "compiler_version": contract.get("CompilerVersion", ""),
                "is_verified": is_verified,
                "is_proxy": is_proxy,
                "implementation_address": implementation,
                "contract_name": contract.get("ContractName", ""),
                "optimization_used": contract.get("OptimizationUsed", "0") == "1",
                "license_type": contract.get("LicenseType", ""),
            }

        return None

    async def get_transactions(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent transactions from block explorer."""
        data = await self._explorer_api_call({
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": "0",
            "endblock": "99999999",
            "page": "1",
            "offset": str(limit),
            "sort": "desc",
        })

        if not data or not data.get("result") or not isinstance(data["result"], list):
            return []

        txns = []
        for tx in data["result"][:limit]:
            txns.append({
                "hash": tx.get("hash", ""),
                "from": tx.get("from", ""),
                "to": tx.get("to", ""),
                "value": int(tx.get("value", 0)) / 1e18,
                "timestamp": int(tx.get("timeStamp", 0)),
                "block_number": int(tx.get("blockNumber", 0)),
                "gas_used": int(tx.get("gasUsed", 0)),
                "is_error": tx.get("isError", "0") == "1",
                "function_name": tx.get("functionName", ""),
                "method_id": tx.get("methodId", ""),
            })

        return txns

    async def validate_address(self, address: str) -> bool:
        """Validate EVM address format."""
        from src.chains.address import AddressResolver
        return AddressResolver.is_valid_evm_address(address)

    async def get_wallet_tokens(self, wallet: str) -> List[Dict[str, Any]]:
        """
        Get all ERC-20 token holdings for a wallet.

        Uses Etherscan-family tokentx API to discover token interactions,
        then fetches current balances.
        """
        # Get token transfer events to discover tokens
        data = await self._explorer_api_call({
            "module": "account",
            "action": "tokentx",
            "address": wallet,
            "page": "1",
            "offset": "100",
            "sort": "desc",
        })

        if not data or not data.get("result") or not isinstance(data["result"], list):
            return []

        # Collect unique token addresses
        seen_tokens = {}
        for tx in data["result"]:
            token_addr = tx.get("contractAddress", "").lower()
            if token_addr and token_addr not in seen_tokens:
                seen_tokens[token_addr] = {
                    "mint": token_addr,
                    "name": tx.get("tokenName", "Unknown"),
                    "symbol": tx.get("tokenSymbol", "???"),
                    "decimals": int(tx.get("tokenDecimal", 18)),
                }

        # Fetch current balances for each token
        import asyncio
        tokens = []
        wallet_padded = "0x" + wallet.lower().replace("0x", "").zfill(64)

        async def fetch_balance(token_addr: str, info: dict):
            balance_hex = await self._eth_call(
                token_addr,
                ERC20_BALANCE_OF + wallet_padded[2:]
            )
            balance_raw = self._decode_uint256(balance_hex)
            if balance_raw > 0:
                decimals = info["decimals"]
                balance = balance_raw / (10 ** decimals)
                tokens.append({
                    "mint": token_addr,
                    "name": info["name"],
                    "symbol": info["symbol"],
                    "amount": balance,
                    "value_usd": 0,  # Would need price oracle
                    "price_usd": 0,
                    "logo": None,
                })

        await asyncio.gather(
            *[fetch_balance(addr, info) for addr, info in list(seen_tokens.items())[:50]],
            return_exceptions=True
        )

        return tokens

    async def get_token_approvals(self, wallet: str) -> List[Dict[str, Any]]:
        """
        Get all ERC-20 token approvals for a wallet.

        Scans Approval events from the block explorer.
        """
        # Get approval events
        data = await self._explorer_api_call({
            "module": "account",
            "action": "tokentx",
            "address": wallet,
            "page": "1",
            "offset": "200",
            "sort": "desc",
        })

        if not data or not data.get("result") or not isinstance(data["result"], list):
            return []

        # Collect unique spender approvals
        # Note: This is a simplified approach. A full implementation would
        # use eth_getLogs to scan Approval events directly.
        approvals = []
        seen = set()

        for tx in data["result"]:
            contract = tx.get("contractAddress", "").lower()
            to = tx.get("to", "").lower()
            key = f"{contract}:{to}"

            if key not in seen and contract and to:
                seen.add(key)
                # Check current allowance
                wallet_padded = wallet.lower().replace("0x", "").zfill(64)
                spender_padded = to.replace("0x", "").zfill(64)
                allowance_hex = await self._eth_call(
                    contract,
                    ERC20_ALLOWANCE + wallet_padded + spender_padded
                )
                allowance = self._decode_uint256(allowance_hex)

                if allowance > 0:
                    max_uint256 = 2**256 - 1
                    is_unlimited = allowance >= max_uint256 // 2

                    approvals.append({
                        "token_address": contract,
                        "token_symbol": tx.get("tokenSymbol", "???"),
                        "token_name": tx.get("tokenName", "Unknown"),
                        "spender": to,
                        "allowance": allowance,
                        "allowance_human": "Unlimited" if is_unlimited else str(allowance / (10 ** int(tx.get("tokenDecimal", 18)))),
                        "is_unlimited": is_unlimited,
                    })

        return approvals

    async def simulate_swap(
        self,
        token_in: str,
        token_out: str,
        amount: int,
        slippage_bps: int = 100
    ) -> Dict[str, Any]:
        """
        Simulate a token swap to detect honeypots.

        Uses eth_call to simulate a swap through the chain's primary DEX router.
        Checks if sell transactions would revert.
        """
        if not self.config.dex_router_address:
            return {"success": False, "route_available": False, "error": "No DEX router configured"}

        try:
            # Try to get a quote from Uniswap V3 QuoterV2 or equivalent
            # This is a simplified version - full implementation would use
            # the exact quoter contract for each DEX

            # For now, use a basic approach: try to estimate gas for a swap
            # If it reverts, the token is likely a honeypot
            router = self.config.dex_router_address

            # Encode swap call data (Uniswap V2 style: getAmountsOut)
            # swapExactTokensForTokens path
            path = [token_in.lower(), token_out.lower()]

            # Simple getAmountsOut check
            # function getAmountsOut(uint amountIn, address[] memory path) -> uint[] memory
            # Selector: 0xd06ca61f
            amount_hex = hex(amount)[2:].zfill(64)
            # ABI encode the path array
            offset_hex = "0000000000000000000000000000000000000000000000000000000000000040"
            path_len_hex = "0000000000000000000000000000000000000000000000000000000000000002"
            path_0_hex = path[0].replace("0x", "").zfill(64)
            path_1_hex = path[1].replace("0x", "").zfill(64)

            call_data = f"0xd06ca61f{amount_hex}{offset_hex}{path_len_hex}{path_0_hex}{path_1_hex}"

            result = await self._eth_call(router, call_data)

            if result and result != "0x" and len(result) > 130:
                # Successfully got amounts out - not a honeypot (for this path at least)
                # Parse output amount
                try:
                    output_amount = int(result[-64:], 16)
                    return {
                        "success": True,
                        "route_available": True,
                        "expected_output": output_amount,
                        "price_impact_pct": 0,  # Would need deeper calculation
                        "estimated_tax_pct": 0,
                    }
                except (ValueError, IndexError):
                    pass

            return {
                "success": False,
                "route_available": False,
                "error": "Swap simulation reverted - possible honeypot",
            }

        except Exception as e:
            logger.warning(f"EVM swap simulation failed on {self.chain_type.value}: {e}")
            return {"success": False, "route_available": False, "error": str(e)}

    async def get_deployer(self, contract_address: str) -> Optional[str]:
        """Get the wallet that deployed a contract."""
        # Get contract creation transaction
        data = await self._explorer_api_call({
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": contract_address,
        })

        if data and data.get("result") and isinstance(data["result"], list):
            for item in data["result"]:
                creator = item.get("contractCreator")
                if creator:
                    return creator.lower()

        return None

    async def get_native_balance(self, wallet: str) -> float:
        """Get native token balance (ETH/BNB/MATIC/etc.)."""
        result = await self._rpc_call("eth_getBalance", [wallet, "latest"])
        if result:
            return self._decode_uint256(result) / 1e18
        return 0.0

    def get_explorer_url(self, address: str, type: str = "address") -> str:
        """Get block explorer URL."""
        base = self.config.explorer_url
        if type == "tx":
            return f"{base}/tx/{address}"
        elif type == "token":
            return f"{base}/token/{address}"
        return f"{base}/address/{address}"

    async def close(self) -> None:
        """Cleanup HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info(f"EVMChainClient ({self.chain_type.value}) closed")
