"""Generic ERC-4626 vault deposit adapter.

Covers any compliant vault by ABI alone: Yearn V3, Morpho vaults, Spark sDAI,
Sommelier, Origin Vault, Aera, Sky/MakerDAO sUSDS, Lido stETH wrapper, etc.

Selectors:
  ERC20.approve(spender, amount) → 0x095ea7b3
  IERC4626.deposit(uint256 assets, address receiver) → 0x6e553f65
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.defi.execution.adapters.aave_v3 import _encode_address, _encode_uint256, _to_unit, _ASSETS as _AAVE_ASSETS
from src.defi.execution.adapters.base import (
    CapabilityResult,
    VerifyResult,
    parse_receipt_logs,
    YieldBuildRequest,
    YieldQuote,
    YieldQuoteRequest,
    YieldVerifyRequest,
)
from src.defi.execution.models import ExecutionStepV3, UnsignedStepTransaction, make_step

_CHAIN_IDS = {
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "base": 8453,
    "avalanche": 43114,
    "bsc": 56,
}

# Curated registry of well-known ERC-4626 vaults: (chain, protocol_slug, asset)
# → (vault_address, underlying_asset_address, decimals).
# Add more as we verify them. The lookup falls back to the asset's native
# address from the Aave registry when the underlying token is the same symbol.
_VAULT_REGISTRY: dict[tuple[str, str, str], tuple[str, str, int]] = {
    # Yearn V3 USDC vault on Ethereum (yvUSDC-1)
    ("ethereum", "yearn-finance", "USDC"): (
        "0xbe53a109b494e5c9f97b9cd39fe969be68bf6204",  # yvUSDC v3
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
        6,
    ),
    # Yearn V3 DAI vault on Ethereum
    ("ethereum", "yearn-finance", "DAI"): (
        "0x028ec7330ff87667b6dfb0d94b954c820195336c",
        "0x6b175474e89094c44da98b954eedeac495271d0f",
        18,
    ),
    # Morpho-Blue MetaMorpho USDC on Base (Steakhouse USDC)
    ("base", "morpho-blue", "USDC"): (
        "0xbeef010f9cb27031ad51e3333f9af9c6b1228183",
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
        6,
    ),
    # Spark sDAI on Ethereum
    ("ethereum", "spark", "DAI"): (
        "0x83f20f44975d03b1b09e64809b757c47f942beea",
        "0x6b175474e89094c44da98b954eedeac495271d0f",
        18,
    ),
    # Sky sUSDS on Ethereum
    ("ethereum", "sky-lending", "USDS"): (
        "0xa3931d71877c0e7a3148cb7eb4463524fec27fbd",
        "0xdc035d45d973e3ec169d2276ddab16f1e407384f",
        18,
    ),
    # Morpho MetaMorpho USDC vaults on Arbitrum (chain 42161).
    # Underlying is native USDC: 0xaf88d065e77c8cC2239327C5EDb3A432268e5831 (6 dec).
    # Primary entry (Gauntlet USDC Prime, highest TVL) registered under the
    # protocol slug; alias-style sub-keys appended via _ARB_MORPHO_USDC_VAULTS
    # so callers can target a specific curator.
    ("arbitrum", "morpho-blue", "USDC"): (
        "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed",  # Gauntlet USDC Prime
        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        6,
    ),
    ("arbitrum", "metamorpho", "USDC"): (
        "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed",
        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        6,
    ),
}

# Per-curator MetaMorpho vault registry — Arbitrum USDC. Caller passes
# extra={"vault_curator": "<key>"} to target a specific vault instead of
# the default Gauntlet USDC Prime entry above.
_ARB_MORPHO_USDC_VAULTS: dict[str, str] = {
    "gauntlet-prime":    "0x7c574174DA4b2be3f705c6244B4BfA0815a8B3Ed",
    "gauntlet-core":     "0x7e97fa6893871A2751B5fE961978DCCb2c201E65",
    "steakhouse-prime":  "0x250CF7c82bAc7cB6cf899b6052979d4B5BA1f9ca",
    "steakhouse-high":   "0x5c0C306Aaa9F877de636f4d5822cA9F2E81563BA",
    "kpk-yield":         "0x5837e4189819637853a357aF36650902347F5e73",
}


@dataclass
class ERC4626VaultAdapter:
    adapter_id: str = "erc4626-vault"
    # V7-043 — canonical ERC4626 Deposit(address,address,uint256,uint256) topic0.
    EXPECTED_TOPIC0: str = "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7"
    chains: frozenset[str] = frozenset({"ethereum", "polygon", "arbitrum", "optimism", "base", "avalanche", "bsc"})
    # Empty protocol set means: defer support entirely to the registry lookup.
    # Anything in _VAULT_REGISTRY is supported; anything else returns False.
    protocols: frozenset[str] = frozenset({
        "yearn-finance", "yearn", "morpho-blue", "morpho", "metamorpho",
        "spark", "sky-lending", "sky", "sommelier", "origin", "origin-ether",
        "aera",
        # Lido / Rocket Pool are NOT IERC4626 vaults — Lido is rebasing,
        # rETH is a share-priced ERC20 but not IERC4626. They belong in
        # EvmLstDirectMintAdapter so the direct-mint contracts get called.
    })
    actions: frozenset[str] = frozenset({
        "supply", "deposit", "lend", "stake",
        "withdraw", "redeem",
    })

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"ERC-4626 adapter does not cover {chain}.")
        if action_norm not in self.actions:
            return CapabilityResult(supported=False, reason=f"ERC-4626 adapter does not handle {action}.")
        if protocol_norm not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Protocol {protocol} not in ERC-4626 registry.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={},
            metadata={"protocol": request.protocol, "chain": request.chain, "standard": "ERC-4626"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = _CHAIN_IDS.get(chain_norm)
        protocol_norm = request.protocol.lower()
        asset_norm = request.asset_in.upper()
        vault_meta = _VAULT_REGISTRY.get((chain_norm, protocol_norm, asset_norm))
        if vault_meta is None:
            # Fallback: attempt to read by (chain, asset) only if exactly one entry exists.
            matching = [
                (key, meta) for key, meta in _VAULT_REGISTRY.items()
                if key[0] == chain_norm and key[2] == asset_norm
            ]
            if len(matching) == 1:
                vault_meta = matching[0][1]
            else:
                raise ValueError(
                    f"ERC-4626 adapter has no registered vault for {request.protocol} {request.asset_in} on {request.chain}."
                )
        vault_address, underlying_address, decimals = vault_meta
        if chain_id is None:
            raise ValueError(f"Unknown chain id for {request.chain}.")

        # Per-curator override — Arbitrum Morpho USDC (5 verified vaults).
        # extra={"vault_curator": "steakhouse-prime"} routes the deposit to
        # the Steakhouse vault instead of default Gauntlet Prime. Decimals
        # + underlying USDC address are identical across all five entries.
        curator_hint = (request.extra or {}).get("vault_curator")
        if (
            curator_hint
            and chain_norm == "arbitrum"
            and protocol_norm in {"morpho-blue", "morpho", "metamorpho"}
            and asset_norm == "USDC"
        ):
            curated = _ARB_MORPHO_USDC_VAULTS.get(curator_hint.lower())
            if curated is None:
                raise ValueError(
                    f"Unknown Morpho Arb USDC curator '{curator_hint}'. "
                    f"Known: {sorted(_ARB_MORPHO_USDC_VAULTS)}."
                )
            vault_address = curated

        # Phase 4 lifecycle — withdraw(uint256 assets, address receiver, address owner)
        # selector 0xb460af94 / redeem(uint256 shares, address receiver, address owner)
        # selector 0xba087652.
        extra = request.extra or {}
        action_hint = (extra.get("action") or "").lower()
        if action_hint in {"withdraw", "redeem"}:
            wd_units = _to_unit(request.amount_in, decimals)
            # Matrix Pass A wave 3 D-P1-14 drain-risk fix: amount_in=0
            # silently rewrote to MAX_UINT256 while description still
            # read "withdraw(0)" — user signing "0 withdraw" would drain
            # entire position. Now:
            #   1. Explicit `extra.withdraw_all=true` -> MAX_UINT256
            #      with description "Withdraw ALL".
            #   2. amount_in=0 without that flag -> raise ValueError
            #      (refuse rather than silently rewrite).
            #   3. amount_in>0 -> as specified.
            withdraw_all = bool(extra.get("withdraw_all") or extra.get("max"))
            if wd_units <= 0 and not withdraw_all:
                raise ValueError(
                    f"ERC-4626 {action_hint}: amount_in must be > 0. "
                    f"To withdraw the entire position, pass "
                    f"extra.withdraw_all=true (the description will say "
                    f"'Withdraw ALL' and calldata will use MAX_UINT256)."
                )
            if withdraw_all:
                wd_units = (1 << 256) - 1
            sel = "0xba087652" if action_hint == "redeem" else "0xb460af94"
            data = (
                sel
                + _encode_uint256(wd_units)
                + _encode_address(request.user_address)
                + _encode_address(request.user_address)
            )
            display_amount = (
                "ALL (max)" if withdraw_all else str(request.amount_in)
            )
            step = make_step(
                index=1,
                action=action_hint,
                title=(
                    f"{action_hint.title()} {'ALL' if withdraw_all else request.asset_in} "
                    f"from {request.protocol} vault"
                ),
                description=(
                    f"ERC-4626 {action_hint}({display_amount}) — "
                    f"{'shares' if action_hint == 'redeem' else 'assets'} returned to "
                    f"{request.user_address}."
                ),
                chain=request.chain,
                wallet="MetaMask",
                protocol=request.protocol,
                asset_in=f"{request.protocol}-{request.asset_in}",
                amount_in=str(request.amount_in),
                asset_out=request.asset_in,
                slippage_bps=0,
                gas_estimate_usd=2.0,
                duration_estimate_s=15,
                transaction=UnsignedStepTransaction(
                    chain_kind="evm",
                    chain_id=chain_id,
                    to=vault_address,
                    data=data,
                    value="0x0",
                    spender=vault_address,
                ),
                risk_warnings=[
                    f"Vault {request.protocol} may impose exit fee or pending-queue delay.",
                ],
            )
            return [step]

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("amount_in must be > 0")

        approve_calldata = "0x095ea7b3" + _encode_address(vault_address) + _encode_uint256(amount_units)
        # IERC4626.deposit(uint256 assets, address receiver) → 0x6e553f65
        deposit_calldata = (
            "0x6e553f65"
            + _encode_uint256(amount_units)
            + _encode_address(request.user_address)
        )

        approve_step = make_step(
            index=1,
            action="approve",
            title=f"Approve {request.asset_in} for {request.protocol} vault",
            description=f"Approve {request.amount_in} {request.asset_in} so the {request.protocol} vault can pull funds.",
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            slippage_bps=0,
            gas_estimate_usd=1.4,
            duration_estimate_s=15,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=underlying_address,
                data=approve_calldata,
                value="0x0",
                spender=vault_address,
            ),
            risk_warnings=["Approval allows the vault contract to pull the exact amount you authorize."],
        )
        deposit_step = make_step(
            index=2,
            action="supply",
            title=f"Deposit {request.asset_in} into {request.protocol} vault",
            description=(
                f"ERC-4626 deposit({request.amount_in} {request.asset_in}). "
                f"You receive vault shares minted directly to your wallet."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"{request.protocol}-shares",
            slippage_bps=0,
            gas_estimate_usd=2.6,
            duration_estimate_s=15,
            depends_on=[approve_step.step_id],
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=vault_address,
                data=deposit_calldata,
                value="0x0",
                spender=vault_address,
            ),
            risk_warnings=["Vault APY varies with underlying utilization; treat headline APY as an estimate."],
        )
        return [approve_step, deposit_step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Parse receipt logs for canonical ERC-4626 Deposit event topic0."""
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        return parse_receipt_logs(receipt, self.EXPECTED_TOPIC0)
