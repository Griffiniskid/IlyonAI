"""Aave V3 supply adapter — emits real ERC20 approve + Pool.supply calldata."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
    parse_receipt_logs,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step
from src.defi.resolver.entity_resolver import EntityResolver


# V7-015: centralised entity resolution (spec §3). `_ASSETS` and `_CHAIN_IDS`
# remain as exported surface (compound_v3 + erc4626 re-import _ASSETS / helpers).
# The build() path prefers EntityResolver and falls back to the local dicts.
_RESOLVER = EntityResolver()

# Aave V3 Pool addresses per chain (verified mainnets).
_AAVE_REWARDS_BY_CHAIN: dict[str, str] = {
    # RewardsController per official Aave docs (covers stkAAVE / gauge incentives).
    "ethereum": "0x8164Cc65827dcFe994AB23944CBC90e0aa80bFcb",
    "polygon":  "0x929EC64c34a17401F460460D4B9390518E5B473e",
    "arbitrum": "0x929EC64c34a17401F460460D4B9390518E5B473e",
    "optimism": "0x929EC64c34a17401F460460D4B9390518E5B473e",
    "base":     "0xf9cc4F0D883F1a1eb2c253bdb46c254Ca51E1F44",
    "avalanche":"0x929EC64c34a17401F460460D4B9390518E5B473e",
}


_AAVE_POOL_ADDRESSES: dict[str, str] = {
    "ethereum": "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
    "polygon": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "arbitrum": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "optimism": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
    "base": "0xa238dd80c259a72e81d7e4664a9801593f98d1c5",
    "avalanche": "0x794a61358d6845594f94dc1db02a252b5b4814ad",
}

# WrappedTokenGatewayV3 per chain (Aave V3 official addresses).
# For native-gas-token deposits, the user calls WTG3.depositETH instead of
# wrapping → approving → Pool.supply, which is what every Aave V3 UI does.
_AAVE_WTG3_ADDRESSES: dict[str, str] = {
    "ethereum": "0xD322A49006FC828F9B5B37Ab215F99B4E5caB19C",
    "polygon":  "0xF5f61a1ab3488fCB6d86451846bcFa9cdc108eB0",
    "arbitrum": "0xB5Ee21786D28c5Ba61661550879475976B707099",
    "optimism": "0x60eE8b61a13c67d0191c851BEC8F0bc850160710",
    "base":     "0x729b3EA8C005AbC58c9150fb57Ec161296F06766",
}

# Native gas token symbol per chain — when asset_in matches, route to WTG3.
_NATIVE_TOKEN_BY_CHAIN: dict[str, str] = {
    "ethereum": "ETH",
    "polygon":  "MATIC",
    "arbitrum": "ETH",
    "optimism": "ETH",
    "base":     "ETH",
    "avalanche": "AVAX",
}

# Canonical aWETH (or aMATIC/aAVAX) per chain — needed for WTG3.withdrawETH
# approval. Avoids forcing the caller to know these.
_AAVE_NATIVE_ATOKEN: dict[str, str] = {
    "ethereum": "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8",  # aWETH
    "polygon":  "0x6d80113e533a2C0fe82EaBD35f1875DcEA89Ea97",  # aWMATIC
    "arbitrum": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8",  # aWETH
    "optimism": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8",  # aWETH
    "base":     "0xD4a0e0b9149BCee3C920d2E00b5dE09138fd8bb7",  # aWETH
}

# Variable-debt WETH (or wrapped native) per chain. Used for WTG3.borrowETH:
# user must first call debtToken.approveDelegation(WTG3, amount) to let the
# gateway mint debt on their behalf.
_AAVE_NATIVE_VARIABLE_DEBT: dict[str, str] = {
    "ethereum": "0xeA51d7853EEFb32b6ee06b1C12E6dcCA88Be0fFE",  # variableDebtWETH
    "polygon":  "0x4a1c3aD6Ed28a636ee1751C69071f6be75DEb8B8",  # variableDebtWMATIC
    "arbitrum": "0x0c84331e39d6658Cd6e6b9ba04736cC4c4734351",  # variableDebtWETH
    "optimism": "0x0c84331e39d6658Cd6e6b9ba04736cC4c4734351",  # variableDebtWETH
    "base":     "0x24e6e0795b3c7c71D965fCc4f371803d1c1DcA1E",  # variableDebtWETH
}

_CHAIN_IDS: dict[str, int] = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
}

# Common asset addresses + decimals per chain. Add more incrementally.
_ASSETS: dict[tuple[str, str], tuple[str, int]] = {
    ("ethereum", "USDC"): ("0xa0b86a33e6441e8e421c6f9e8a37e2bd3df0f0fd", 6),  # canonical USDC.e style; replaced below
    ("ethereum", "USDT"): ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("ethereum", "DAI"): ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
    ("ethereum", "WETH"): ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    ("polygon", "USDC"): ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", 6),
    ("polygon", "USDT"): ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6),
    ("arbitrum", "USDC"): ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
    ("arbitrum", "USDT"): ("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", 6),
    ("optimism", "USDC"): ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", 6),
    ("optimism", "USDT"): ("0x94b008aa00579c1307b0ef2c499ad98a8ce58e58", 6),
    ("optimism", "DAI"): ("0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
    ("optimism", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
    ("polygon", "DAI"): ("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", 18),
    ("polygon", "WETH"): ("0x7ceb23fd6bc0add59e62ac25578270cff1b9f619", 18),
    ("arbitrum", "DAI"): ("0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
    ("arbitrum", "WETH"): ("0x82af49447d8a07e3bd95bd0d56f35241523fbab1", 18),
    ("avalanche", "USDC"): ("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", 6),
    ("avalanche", "USDT"): ("0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7", 6),
    ("base", "USDT"): ("0xfde4c96c8593536e31f229ea8f37b2ada2699bb2", 6),
    ("base", "USDC"): ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
    ("base", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
    ("base", "USDBC"): ("0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca", 6),
}

# Override Ethereum USDC with the canonical mainnet address.
_ASSETS[("ethereum", "USDC")] = ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6)


def _encode_uint256(value: int) -> str:
    if value < 0:
        raise ValueError("uint256 cannot be negative")
    return format(value, "064x")


def _encode_address(address: str) -> str:
    addr = address.lower()
    if addr.startswith("0x"):
        addr = addr[2:]
    if len(addr) != 40:
        raise ValueError(f"invalid address: {address}")
    return ("0" * 24) + addr


def _to_unit(amount: Decimal, decimals: int) -> int:
    quant = Decimal(10) ** decimals
    return int((amount * quant).to_integral_value())


def _read_current_allowance(
    *,
    extra: dict,
    chain: str,
    token_address: str,
    owner: str,
    spender: str,
) -> int | None:
    """Spec §7 S8 — fetch existing allowance (fail-soft).

    Reads in priority order:
      1. extra['current_allowance']         → raw int (pre-fetched by caller)
      2. extra['allowance_reader']          → callable(chain, token, owner, spender) -> int
      3. extra['web3_client'] / extra['evm_client'] with .allowance(...)
    Returns None on any error or when no reader is supplied — callers must
    treat that as "unknown → emit full approve" so behaviour is unchanged
    when the read path is unavailable.
    """
    try:
        ca = extra.get("current_allowance")
        if ca is not None:
            return int(ca)
        reader = extra.get("allowance_reader")
        if callable(reader):
            val = reader(chain, token_address, owner, spender)
            if val is None:
                return None
            return int(val)
        client = extra.get("web3_client") or extra.get("evm_client")
        if client is not None:
            fn = getattr(client, "allowance", None) or getattr(client, "get_allowance", None)
            if callable(fn):
                val = fn(chain, token_address, owner, spender)
                if val is None:
                    return None
                return int(val)
    except Exception:
        return None
    return None


def _resolve_approve_amount(
    requested_units: int,
    *,
    current_allowance: int | None,
) -> tuple[int | None, str | None]:
    """Decide approve amount per spec §7 S8 partial-allowance ladder.

    Returns (approve_units, warning):
      - approve_units = None      → SKIP the approve step entirely
      - approve_units = delta     → top-up approve for (requested - current)
      - approve_units = requested → full approve (current allowance is 0 or
                                    we couldn't read it — fail-soft)
      - warning                   → a string to attach to the supply step's
                                    risk_warnings (or None)
    """
    if requested_units <= 0:
        return requested_units, None
    if current_allowance is None:
        return requested_units, None  # fail-soft: full approve
    if current_allowance >= requested_units:
        return None, (
            f"Existing allowance sufficient — no approve needed "
            f"(current={current_allowance}, needed={requested_units})."
        )
    if current_allowance > 0:
        delta = requested_units - current_allowance
        return delta, (
            f"Topping up existing {current_allowance} allowance to {requested_units} "
            f"(delta approve = {delta})."
        )
    return requested_units, None  # current_allowance == 0 → full approve


@dataclass
class AaveV3SupplyAdapter:
    adapter_id: str = "aave-v3-supply"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base", "avalanche"})
    protocols: frozenset[str] = frozenset({"aave-v3", "aave", "aave v3", "aavev3"})
    # V7-043 — canonical Pool.Supply(address,address,address,uint256,uint16) topic0.
    EXPECTED_TOPIC0: str = "0x2b627736bca15cd5381dcf80b0bf11fd197d01a037c52b927a881a10fb73ba61"
    actions: frozenset[str] = frozenset({
        "supply", "deposit", "lend", "withdraw", "claim", "repay", "borrow",
        # V7-002 §7 S12 — claim Aave incentives and re-supply (stkAAVE
        # compounding loop). Composed by ClaimCompoundComposer into
        # [claim, supply_back].
        "claim_compound",
    })

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"Aave V3 adapter does not cover {chain}.")
        if protocol.lower() not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Adapter is for Aave V3, not {protocol}.")
        if action.lower() not in self.actions:
            return CapabilityResult(supported=False, reason=f"Aave V3 adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=str(request.amount_in),
            fees={"protocol": "0", "router": "0"},
            metadata={"protocol": "aave-v3", "chain": request.chain},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        # V7-015: chain id via EntityResolver; fall back to local _CHAIN_IDS.
        chain_info = _RESOLVER.resolve_chain(chain_norm)
        chain_id = (
            chain_info.chain_id
            if chain_info is not None and chain_info.chain_id > 0
            else _CHAIN_IDS.get(chain_norm)
        )
        pool_address = _AAVE_POOL_ADDRESSES.get(chain_norm)
        if chain_id is None or pool_address is None:
            raise ValueError(f"Aave V3 adapter cannot build on chain {request.chain}.")

        extra = request.extra or {}
        action_hint = (extra.get("action") or "").lower()

        # Native supply path runs before the ERC20 _ASSETS lookup, since
        # native gas tokens have no ERC20 address.
        native_sym = _NATIVE_TOKEN_BY_CHAIN.get(chain_norm)
        if (
            native_sym
            and request.asset_in.upper() == native_sym
            and action_hint in {"", "supply", "deposit", "lend"}
        ):
            wtg3 = _AAVE_WTG3_ADDRESSES.get(chain_norm)
            if wtg3 is None:
                raise ValueError(
                    f"Aave V3 WrappedTokenGatewayV3 not registered on {chain_norm}."
                )
            native_units = _to_unit(request.amount_in, 18)
            if native_units <= 0:
                raise ValueError("amount_in must be > 0")
            # depositETH(address pool, address onBehalfOf, uint16 referralCode)
            wtg3_calldata = (
                "0x474cf53d"
                + _encode_address(pool_address)
                + _encode_address(request.user_address)
                + _encode_uint256(0)
            )
            value_hex = "0x" + format(native_units, "x")
            native_step = make_step(
                index=1,
                action="supply",
                title=f"Supply native {native_sym} to Aave V3",
                description=(
                    f"WrappedTokenGatewayV3.depositETH({pool_address}, "
                    f"{request.user_address}, 0) at {wtg3}. Gateway wraps "
                    f"{request.amount_in} {native_sym} and supplies to Aave V3 "
                    f"Pool atomically. You receive aW{native_sym}."
                ),
                chain=request.chain,
                wallet="MetaMask",
                protocol="aave-v3",
                asset_in=native_sym,
                amount_in=str(request.amount_in),
                asset_out=f"aW{native_sym}",
                slippage_bps=0,
                gas_estimate_usd=3.2,
                duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm",
                    chain_id=chain_id,
                    to=wtg3,
                    data=wtg3_calldata,
                    value=value_hex,
                    spender=wtg3,
                ),
                risk_warnings=[
                    f"Native deposit wraps to W{native_sym} inside the gateway — no separate approve needed.",
                    "Withdraw requires WTG3.withdrawETH and a one-time aToken approval to WTG3.",
                ],
            )
            return [native_step]

        # Native repay via WTG3.repayETH (selector 0x02c5fcf8). msg.value
        # carries the repay amount; no approve step. Must check BEFORE
        # _ASSETS lookup (native gas tokens have no ERC20 entry).
        if action_hint == "repay" and (
            _NATIVE_TOKEN_BY_CHAIN.get(chain_norm) == request.asset_in.upper()
        ):
            wtg3 = _AAVE_WTG3_ADDRESSES.get(chain_norm)
            if wtg3 is None:
                raise ValueError(
                    f"Aave V3 WrappedTokenGatewayV3 not registered on {chain_norm}."
                )
            native_units = _to_unit(request.amount_in, 18)
            if native_units <= 0:
                native_units = (1 << 256) - 1
            rate_mode = int(extra.get("rate_mode") or 2)
            calldata = (
                "0x02c5fcf8"
                + _encode_address(pool_address)
                + _encode_uint256(native_units)
                + _encode_uint256(rate_mode)
                + _encode_address(request.user_address)
            )
            value_hex = "0x" + format(native_units if native_units < (1 << 256) - 1 else 0, "x")
            step = make_step(
                index=1, action="repay",
                title=f"Repay native {request.asset_in} via WTG3",
                description=(
                    f"WrappedTokenGatewayV3.repayETH({pool_address}, "
                    f"{request.amount_in}, rateMode={rate_mode}, "
                    f"onBehalfOf={request.user_address}) at {wtg3}. "
                    f"msg.value carries {request.amount_in} {request.asset_in}; "
                    f"gateway wraps + repays."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=request.asset_in, amount_in=str(request.amount_in),
                slippage_bps=0, gas_estimate_usd=3.0, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=wtg3, data=calldata, value=value_hex,
                    spender=wtg3,
                ),
                risk_warnings=[
                    "Native repay sends ETH via WTG3 — no approve step.",
                ],
            )
            return [step]

        # Native withdraw via WTG3 must check BEFORE _ASSETS lookup (native
        # gas tokens have no ERC20 metadata). Asset_in is the native symbol
        # (ETH/MATIC/AVAX); aToken address comes from extra.atoken_address.
        if action_hint == "withdraw" and (
            _NATIVE_TOKEN_BY_CHAIN.get(chain_norm) == request.asset_in.upper()
        ):
            wtg3 = _AAVE_WTG3_ADDRESSES.get(chain_norm)
            if wtg3 is None:
                raise ValueError(
                    f"Aave V3 WrappedTokenGatewayV3 not registered on {chain_norm}."
                )
            native_units = _to_unit(request.amount_in, 18)
            # Matrix Pass A wave 3 D-P1-14 drain-risk fix: amount_in=0
            # silently rewrote to MAX_UINT256 while description still
            # read "Withdraw 0 ETH" — user signing a "0 withdraw" would
            # actually withdraw the entire aToken balance via WTG3 burn.
            # Now require explicit extra.withdraw_all=true for max
            # withdrawal; refuse zero/negative otherwise.
            native_withdraw_all = bool(
                extra.get("withdraw_all") or extra.get("max")
            )
            if native_units <= 0 and not native_withdraw_all:
                raise ValueError(
                    "Aave V3 native withdraw via WTG3: amount_in must "
                    "be > 0. To withdraw the entire aToken balance, "
                    "pass extra.withdraw_all=true (the description "
                    "will say 'Withdraw ALL' and calldata will use "
                    "MAX_UINT256)."
                )
            if native_withdraw_all:
                native_units = (1 << 256) - 1
            atoken_addr = (
                extra.get("atoken_address")
                or extra.get("aToken")
                or _AAVE_NATIVE_ATOKEN.get(chain_norm)
                or ""
            ).lower()
            if not atoken_addr or len(atoken_addr) != 42:
                raise ValueError(
                    f"Native withdraw via WTG3 needs extra.atoken_address (the "
                    f"a{request.asset_in} contract on {chain_norm})."
                )
            approve_calldata = (
                "0x095ea7b3"
                + _encode_address(wtg3)
                + _encode_uint256(native_units)
            )
            withdraw_calldata = (
                "0x80500d20"
                + _encode_address(pool_address)
                + _encode_uint256(native_units)
                + _encode_address(request.user_address)
            )
            approve_step = make_step(
                index=1, action="approve",
                title=f"Approve a{request.asset_in} for WTG3",
                description=(
                    f"Approve {request.amount_in} a{request.asset_in} so the "
                    f"WrappedTokenGatewayV3 can burn it to redeem the underlying "
                    f"and unwrap to native {request.asset_in}."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=f"a{request.asset_in}", amount_in=str(request.amount_in),
                slippage_bps=0, gas_estimate_usd=1.4, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=atoken_addr, data=approve_calldata, value="0x0",
                    spender=wtg3,
                ),
            )
            wtg_step = make_step(
                index=2, action="withdraw",
                title=f"Withdraw native {request.asset_in} via WTG3",
                description=(
                    f"WrappedTokenGatewayV3.withdrawETH({pool_address}, "
                    f"{request.amount_in if native_units != (1<<256)-1 else 'ALL'}, "
                    f"{request.user_address}) at {wtg3}."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=f"a{request.asset_in}", amount_in=str(request.amount_in),
                asset_out=request.asset_in,
                slippage_bps=0, gas_estimate_usd=3.2, duration_estimate_s=15,
                depends_on=[approve_step.step_id],
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=wtg3, data=withdraw_calldata, value="0x0",
                    spender=wtg3,
                ),
            )
            return [approve_step, wtg_step]

        # Native borrow via WTG3.borrowETH (selector 0x66514c97). Requires
        # approveDelegation on the variable-debt WETH token first; WTG3 then
        # mints debt on behalf of the user, unwraps WETH → ETH, and sends it.
        if (
            action_hint == "borrow"
            and request.asset_in.upper() == _NATIVE_TOKEN_BY_CHAIN.get(chain_norm, "").upper()
        ):
            wtg3 = _AAVE_WTG3_ADDRESSES.get(chain_norm)
            if wtg3 is None:
                raise ValueError(
                    f"Aave V3 WrappedTokenGatewayV3 not registered on {chain_norm}."
                )
            debt_token = _AAVE_NATIVE_VARIABLE_DEBT.get(chain_norm)
            if debt_token is None:
                raise ValueError(
                    f"Aave V3 variable-debt token not registered for native borrow on {chain_norm}."
                )
            borrow_units = _to_unit(request.amount_in, 18)
            if borrow_units <= 0:
                raise ValueError("Borrow amount must be > 0.")
            rate_mode = int(extra.get("rate_mode") or 2)
            # ICreditDelegationToken.approveDelegation(delegatee, amount) = 0xc04a8a10
            approve_delegation_calldata = (
                "0xc04a8a10"
                + _encode_address(wtg3)
                + _encode_uint256(borrow_units)
            )
            # WTG3.borrowETH(pool, amount, interestRateMode, referralCode) → 0x66514c97
            borrow_eth_calldata = (
                "0x66514c97"
                + _encode_address(pool_address)
                + _encode_uint256(borrow_units)
                + _encode_uint256(rate_mode)
                + _encode_uint256(0)  # referralCode
            )
            approve_delegation_step = make_step(
                index=1, action="approve",
                title=f"Approve variable debt delegation to WTG3",
                description=(
                    f"variableDebt{_NATIVE_TOKEN_BY_CHAIN.get(chain_norm)}."
                    f"approveDelegation({wtg3}, {request.amount_in})."
                    f" Allows WrappedTokenGatewayV3 to mint debt on your behalf."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=None, amount_in=str(request.amount_in),
                slippage_bps=0, gas_estimate_usd=1.4, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=debt_token, data=approve_delegation_calldata, value="0x0",
                    spender=wtg3,
                ),
                risk_warnings=[
                    "Delegation lets WTG3 incur debt on your behalf — only the WTG3 address can use it.",
                ],
            )
            borrow_eth_step = make_step(
                index=2, action="borrow",
                title=f"Borrow native {request.asset_in} via WTG3",
                description=(
                    f"WrappedTokenGatewayV3.borrowETH({pool_address}, "
                    f"{request.amount_in}, rateMode={rate_mode}, referralCode=0). "
                    f"Mints variable debt against your existing collateral. "
                    f"WTG3 unwraps WETH and forwards native {request.asset_in} to your wallet."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=None, amount_in=str(request.amount_in),
                asset_out=request.asset_in,
                slippage_bps=0, gas_estimate_usd=3.0, duration_estimate_s=15,
                depends_on=[approve_delegation_step.step_id],
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=wtg3, data=borrow_eth_calldata, value="0x0",
                    spender=wtg3,
                ),
                risk_warnings=[
                    "Native borrow REVERTS if collateral health factor drops below 1.0.",
                    f"Variable-rate debt — interest accrues continuously. rateMode={rate_mode}.",
                ],
            )
            return [approve_delegation_step, borrow_eth_step]

        # V7-015 — central token resolver, fall back to local _ASSETS for any
        # adapter-specific extras (Base USDbC etc.) not yet in asset_registry.
        asset_key = (chain_norm, request.asset_in.upper())
        token_info = _RESOLVER.resolve_token(request.asset_in, chain_norm)
        if token_info is not None:
            asset_meta = (token_info.address, token_info.decimals)
        else:
            asset_meta = _ASSETS.get(asset_key)
        if asset_meta is None:
            raise ValueError(f"Aave V3 adapter has no token metadata for {request.asset_in} on {request.chain}.")
        token_address, decimals = asset_meta
        if action_hint == "borrow":
            # Pool.borrow(asset, amount, interestRateMode, referralCode, onBehalfOf)
            # selector 0xa415bcad. No approve step — borrow mints debt, doesn't pull funds.
            borrow_units = _to_unit(request.amount_in, decimals)
            if borrow_units <= 0:
                raise ValueError("Borrow amount must be > 0.")
            rate_mode = int(extra.get("rate_mode") or 2)  # 2 = variable, 1 = stable
            borrow_calldata = (
                "0xa415bcad"
                + _encode_address(token_address)
                + _encode_uint256(borrow_units)
                + _encode_uint256(rate_mode)
                + _encode_uint256(0)  # referralCode
                + _encode_address(request.user_address)
            )
            borrow_step = make_step(
                index=1, action="borrow",
                title=f"Borrow {request.asset_in} from Aave V3",
                description=(
                    f"Pool.borrow({request.asset_in}, {request.amount_in}, "
                    f"rateMode={rate_mode}, referralCode=0, onBehalfOf={request.user_address}). "
                    f"Mints variable-rate debt against your existing collateral; the asset is "
                    f"transferred to your wallet."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=None, amount_in=str(request.amount_in),
                asset_out=request.asset_in,
                slippage_bps=0, gas_estimate_usd=3.0, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=pool_address, data=borrow_calldata, value="0x0",
                    spender=pool_address,
                ),
                risk_warnings=[
                    "Borrow requires existing collateral with sufficient health factor.",
                    f"Variable-rate debt — interest accrues continuously. rateMode={rate_mode}.",
                    "Borrow will REVERT if your collateralized health factor goes below 1.0.",
                ],
            )
            return [borrow_step]
        if action_hint == "repay":
            repay_units = _to_unit(request.amount_in, decimals)
            if repay_units <= 0:
                repay_units = (1 << 256) - 1  # max sentinel
            rate_mode = int(extra.get("rate_mode") or 2)  # 2 = variable, 1 = stable
            # ERC20 approve(Pool, amount) first
            approve_calldata = "0x095ea7b3" + _encode_address(pool_address) + _encode_uint256(repay_units)
            # Pool.repay(asset, amount, rateMode, onBehalfOf) → 0x573ade81
            repay_calldata = (
                "0x573ade81"
                + _encode_address(token_address)
                + _encode_uint256(repay_units)
                + _encode_uint256(rate_mode)
                + _encode_address(request.user_address)
            )
            approve_step = make_step(
                index=1, action="approve",
                title=f"Approve {request.asset_in} for Aave V3 repay",
                description=f"Allow Aave V3 Pool to pull up to {request.amount_in} {request.asset_in} for repay.",
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=request.asset_in, amount_in=str(request.amount_in),
                slippage_bps=0, gas_estimate_usd=1.4, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=token_address, data=approve_calldata, value="0x0",
                    spender=pool_address,
                ),
            )
            repay_step = make_step(
                index=2, action="repay",
                title=f"Repay {request.asset_in} debt on Aave V3",
                description=(
                    f"Pool.repay({request.asset_in}, "
                    f"{request.amount_in if repay_units != (1<<256)-1 else 'ALL'}, "
                    f"rateMode={rate_mode}, onBehalfOf={request.user_address})."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=request.asset_in, amount_in=str(request.amount_in),
                asset_out=f"a{request.asset_in}",
                slippage_bps=0, gas_estimate_usd=2.5, duration_estimate_s=15,
                depends_on=[approve_step.step_id],
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=pool_address, data=repay_calldata, value="0x0",
                    spender=pool_address,
                ),
                risk_warnings=[
                    "Repay reduces debt balance; aToken accrual continues for any remaining supply.",
                ],
            )
            return [approve_step, repay_step]
        if action_hint == "claim":
            rewards_addr = _AAVE_REWARDS_BY_CHAIN.get(chain_norm)
            if not rewards_addr:
                raise ValueError(f"Aave V3 RewardsController not registered on {chain_norm}.")
            # RewardsController.claimAllRewards(address[] assets, address to) — selector 0xbb492bf5.
            # Dynamic-encoded address[]: offset (32 bytes pointing to head end) +
            # to address + length + asset (only the aToken here, which user
            # supplied via extra.aToken or we derive as the aave receipt).
            atoken = (
                (extra.get("aToken") or extra.get("atoken") or token_address).lower()
            )
            head = (
                _encode_uint256(64)                  # offset to assets array
                + _encode_address(request.user_address)
                + _encode_uint256(1)                 # array length = 1
                + _encode_address(atoken)            # the aToken address
            )
            data = "0xbb492bf5" + head
            step = make_step(
                index=1, action="claim",
                title=f"Claim Aave V3 rewards for {request.asset_in}",
                description=(
                    f"RewardsController.claimAllRewards([{atoken}], {request.user_address}) "
                    f"at {rewards_addr}. Accumulated rewards (stkAAVE / gauge incentives) "
                    f"transferred to the user wallet."
                ),
                chain=request.chain, wallet="MetaMask", protocol="aave-v3",
                asset_in=f"a{request.asset_in}", amount_in="0",
                asset_out="REWARDS",
                slippage_bps=0, gas_estimate_usd=2.5, duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm", chain_id=chain_id,
                    to=rewards_addr, data=data, value="0x0", spender=rewards_addr,
                ),
                risk_warnings=[
                    "Claim transfers accrued rewards to your wallet — no allowance or principal touched.",
                ],
            )
            return [step]
        if action_hint == "withdraw":
            withdraw_units = _to_unit(request.amount_in, decimals)
            # type(uint256).max = withdraw all. Pass-through when caller asks
            # "max" / amount=0.
            if withdraw_units <= 0:
                withdraw_units = (1 << 256) - 1
            withdraw_calldata = (
                "0x69328dec"
                + _encode_address(token_address)
                + _encode_uint256(withdraw_units)
                + _encode_address(request.user_address)
            )
            withdraw_step = make_step(
                index=1,
                action="withdraw",
                title=f"Withdraw {request.asset_in} from Aave V3",
                description=(
                    f"Withdraw {request.amount_in if withdraw_units != (1<<256)-1 else 'ALL'} "
                    f"{request.asset_in} via Aave V3 Pool. aToken burned + underlying returned."
                ),
                chain=request.chain,
                wallet="MetaMask",
                protocol="aave-v3",
                # asset_in is the user-perspective underlying (USDC), NOT the
                # receipt-token slug "aUSDC". v4-D02 caught: prior step
                # surfaced asset_in="aUSDC", lazy_resume rebuilt next turn
                # with asset_in=AUSDC, Aave V3 adapter refused 'no token
                # metadata for AUSDC on base'.
                asset_in=request.asset_in,
                amount_in=str(request.amount_in),
                asset_out=request.asset_in,
                slippage_bps=0,
                gas_estimate_usd=2.8,
                duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm",
                    chain_id=chain_id,
                    to=pool_address,
                    data=withdraw_calldata,
                    value="0x0",
                    spender=pool_address,
                ),
                risk_warnings=[
                    "Withdraw burns aTokens 1:1 with the underlying balance + interest.",
                ],
            )
            return [withdraw_step]

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        # Spec §7 S8 — partial allowance ladder. Skip approve when existing
        # allowance is sufficient, top-up the delta when partially funded,
        # full approve otherwise (or when read fails — fail-soft).
        current_allowance = _read_current_allowance(
            extra=extra,
            chain=chain_norm,
            token_address=token_address,
            owner=request.user_address,
            spender=pool_address,
        )
        approve_units, allowance_note = _resolve_approve_amount(
            amount_units, current_allowance=current_allowance,
        )

        # Aave Pool supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) -> 0x617ba037
        supply_calldata = (
            "0x617ba037"
            + _encode_address(token_address)
            + _encode_uint256(amount_units)
            + _encode_address(request.user_address)
            + _encode_uint256(0)
        )

        steps: list[ExecutionStepV3] = []
        supply_index = 1
        depends_on: list[str] = []
        if approve_units is not None:
            approve_calldata = (
                "0x095ea7b3"
                + _encode_address(pool_address)
                + _encode_uint256(approve_units)
            )
            approve_title = (
                f"Approve {request.asset_in} for Aave V3 Pool"
                if approve_units == amount_units
                else f"Top up {request.asset_in} allowance for Aave V3 Pool"
            )
            approve_desc = (
                f"Approve {request.amount_in} {request.asset_in} so Aave V3 Pool can pull funds."
                if approve_units == amount_units
                else (
                    f"Top-up approve: current allowance {current_allowance} is below the "
                    f"requested {amount_units}. Adding delta of {approve_units} so Aave V3 "
                    f"Pool can pull the full requested amount."
                )
            )
            approve_warnings = ["Approval allows Aave V3 Pool to pull the exact amount you authorize."]
            if allowance_note:
                approve_warnings.append(allowance_note)
            approve_step = make_step(
                index=1,
                action="approve",
                title=approve_title,
                description=approve_desc,
                chain=request.chain,
                wallet="MetaMask",
                protocol="aave-v3",
                asset_in=request.asset_in,
                amount_in=str(Decimal(approve_units) / (Decimal(10) ** decimals)),
                slippage_bps=0,
                gas_estimate_usd=1.4,
                duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm",
                    chain_id=chain_id,
                    to=token_address,
                    data=approve_calldata,
                    value="0x0",
                    spender=pool_address,
                ),
                risk_warnings=approve_warnings,
            )
            steps.append(approve_step)
            depends_on = [approve_step.step_id]
            supply_index = 2

        supply_warnings = ["Aave supply APY varies with utilization; treat headline APY as an estimate."]
        if allowance_note and approve_units is None:
            # Approve skipped entirely — surface the reason on the supply step.
            supply_warnings.append(allowance_note)
        supply_step = make_step(
            index=supply_index,
            action="supply",
            title=f"Supply {request.asset_in} to Aave V3",
            description=f"Deposit {request.amount_in} {request.asset_in} into Aave V3 Pool. You receive a{request.asset_in} receipt token.",
            chain=request.chain,
            wallet="MetaMask",
            protocol="aave-v3",
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"a{request.asset_in}",
            slippage_bps=0,
            gas_estimate_usd=2.8,
            duration_estimate_s=15,
            depends_on=depends_on,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=pool_address,
                data=supply_calldata,
                value="0x0",
                spender=pool_address,
            ),
            risk_warnings=supply_warnings,
        )
        steps.append(supply_step)
        return steps

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Parse receipt logs for canonical Aave V3 Pool.Supply event topic0.

        Accepts the EVM receipt via ``request.receipt`` or
        ``request.expected_position["receipt"]``. Returns confirmed=True when
        ≥1 log carries the Supply signature, plus log_match count and the
        first matching raw log for downstream attribution.
        """
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        return parse_receipt_logs(receipt, self.EXPECTED_TOPIC0)
