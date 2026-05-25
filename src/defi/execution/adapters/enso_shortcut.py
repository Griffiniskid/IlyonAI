"""Enso shortcut adapter — universal EVM yield catch-all.

For every EVM chain Enso supports we:
  1. Resolve `tokenIn` from request.asset_in (symbol or address) via the
     asset registry + on-chain decimals() fallback.
  2. Resolve `tokenOut` (Enso position token) via the dynamic /tokens
     resolver. This auto-discovers Aave V3 static atokens, Compound V3
     Comets, Curve LP tokens, Balancer BPTs, Yearn vaults, Morpho vaults,
     Spark sDAI, Lido stETH, RocketPool rETH, EtherFi eETH, Frax sfrxETH,
     Stargate, Stader, Moonwell, GMX, Velodrome, Aerodrome, etc.
  3. Call /shortcuts/route which returns bundled calldata performing the
     full deposit (including internal approvals + swaps) in one tx.

V3 (uniswap-v3, pancake-v3, aerodrome-slipstream) NFT positions are
handled separately by the V3 router adapter — not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.config import settings
from src.data.asset_registry import resolve_any_evm_token, NATIVE_PLACEHOLDER
from src.data.enso_token_resolver import (
    ENSO_CHAIN_IDS,
    normalize_protocol,
    resolve_position,
)
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


def _to_unit(amount: Decimal, decimals: int) -> int:
    quant = Decimal(10) ** decimals
    return int((amount * quant).to_integral_value())


_SUPPORTED_PROTOCOLS = frozenset({
    "aave-v3", "aave", "aavev3",
    "aave-v2", "aave-v3-prime", "aave-static",
    "compound-v3", "compound", "compoundv3",
    "curve", "curve-dex", "curve-lending",
    "balancer", "balancer-v2", "balancer-v3",
    "yearn-finance", "yearn", "yearn-v3",
    "morpho-blue", "morpho", "metamorpho",
    "spark", "spark-protocol", "spark-lending",
    "sky", "sky-lending", "makerdao",
    "lido", "rocket-pool", "rocketpool",
    "ether.fi", "ether-fi", "etherfi",
    "frax", "frax-ether", "frx-ether",
    "ethena", "pendle",
    "stargate", "moonwell",
    "gmx", "velodrome", "velodrome-v2", "aerodrome", "aerodrome-v1",
    "stader", "origin", "origin-ether",
    "fluid", "fluid-lending",
    "beefy", "beefy-clm", "beefy-finance",
    "ichi", "ichi-vaults", "steer", "steer-protocol", "gamma", "arrakis",
    "tokemak", "tokemak-autoeth",
    # V2 AMM LP — Enso zaps a single token into the pair LP in one bundled tx
    # (swap half → add both legs), so the user doesn't need to supply both legs.
    "pancakeswap", "pancakeswap-amm", "pancakeswap-v2", "pancake",
    "uniswap-v2", "uniswap", "univ2",
    "sushiswap", "sushiswap-v2", "sushi",
    "quickswap", "camelot", "baseswap", "trader-joe", "traderjoe", "spookyswap",
})

_SUPPORTED_CHAINS = frozenset({
    "ethereum", "polygon", "arbitrum", "optimism", "base",
    "avalanche", "bsc", "binance", "linea", "zksync",
    "scroll", "gnosis", "sonic", "soneium", "plasma", "ink",
})

# V7-043 — canonical ERC-20 Transfer(address indexed from, address indexed to,
# uint256 value) topic0. Used as the cross-protocol fallback signal.
_TRANSFER_TOPIC0 = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# V7-043 — Per-protocol canonical Deposit-class event topic0. Keys are the
# normalized protocol slugs Enso route hits; values are the keccak256 of the
# event signature the destination contract emits on a successful supply.
# This is the strongest receipt signal we can give without doing a full
# protocol-specific decode in the watcher.
_PROTOCOL_DEPOSIT_TOPIC0: dict[str, str] = {
    # Aave V3 Pool.Supply(address reserve, address user, address onBehalfOf,
    #                     uint256 amount, uint16 referralCode)
    "aave-v3": "0x2b627736bca15cd5381dcf80b0bf11fd197d01a037c52b927a881a10fb73ba61",
    "aave": "0x2b627736bca15cd5381dcf80b0bf11fd197d01a037c52b927a881a10fb73ba61",
    "aavev3": "0x2b627736bca15cd5381dcf80b0bf11fd197d01a037c52b927a881a10fb73ba61",
    # Compound V3 Comet.Supply(address indexed from, address indexed dst,
    #                          uint256 amount)
    "compound-v3": "0xfa56f7b24f17183d81894d3ac2ee654e3c26388d17a28dbd9549b8114304e1f4",
    "compound": "0xfa56f7b24f17183d81894d3ac2ee654e3c26388d17a28dbd9549b8114304e1f4",
    "compoundv3": "0xfa56f7b24f17183d81894d3ac2ee654e3c26388d17a28dbd9549b8114304e1f4",
    # ERC-4626 Deposit(address indexed sender, address indexed owner,
    #                  uint256 assets, uint256 shares) — covers Yearn V3,
    # MetaMorpho, Morpho vaults, Spark sDAI, ERC-4626 vaults broadly.
    "yearn-finance": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "yearn": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "yearn-v3": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "morpho": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "morpho-blue": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "metamorpho": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "spark": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "spark-protocol": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "spark-lending": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "sky": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "sky-lending": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "fluid": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "fluid-lending": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "beefy": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "beefy-finance": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "beefy-clm": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "tokemak": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
    "tokemak-autoeth": "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7",
}


def _normalize_addr(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if not v:
        return None
    return v if v.startswith("0x") else "0x" + v


def _topic_addr_match(topic: str | None, addr: str | None) -> bool:
    """Compare a 32-byte topic (left-padded address) against a 20-byte addr."""
    if not isinstance(topic, str) or not isinstance(addr, str):
        return False
    t = topic.lower().removeprefix("0x").lstrip("0")
    a = addr.lower().removeprefix("0x").lstrip("0")
    return bool(t) and bool(a) and t == a


@dataclass
class EnsoShortcutAdapter:
    adapter_id: str = "enso-shortcut"
    chains: frozenset[str] = _SUPPORTED_CHAINS
    protocols: frozenset[str] = _SUPPORTED_PROTOCOLS
    actions: frozenset[str] = frozenset({"supply", "deposit", "lend", "stake", "deposit_lp"})

    def supports(self, *, chain: str, protocol: str, action: str) -> CapabilityResult:
        if not settings.enso_api_key:
            return CapabilityResult(
                supported=False,
                reason="ENSO_API_KEY is not configured; set it in the .env to enable Enso shortcut deposits.",
            )
        chain_norm = chain.lower()
        protocol_norm = protocol.lower()
        action_norm = action.lower()
        if chain_norm not in self.chains:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not cover {chain}.")
        if protocol_norm not in self.protocols:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not target {protocol}.")
        if action_norm not in self.actions:
            return CapabilityResult(supported=False, reason=f"Enso adapter does not support {action}.")
        return CapabilityResult(supported=True, adapter_id=self.adapter_id)

    async def quote(self, request: YieldQuoteRequest) -> YieldQuote:
        return YieldQuote(
            adapter_id=self.adapter_id,
            expected_apy=None,
            expected_amount_out=None,
            fees={"router": "Enso"},
            metadata={"protocol": request.protocol, "chain": request.chain, "router": "enso"},
        )

    async def build(self, request: YieldBuildRequest) -> list[ExecutionStepV3]:
        chain_norm = request.chain.lower()
        chain_id = ENSO_CHAIN_IDS.get(chain_norm)
        if chain_id is None:
            raise ValueError(f"Enso: unknown chain id for {request.chain}.")

        extra = request.extra or {}
        token_in_meta = await resolve_any_evm_token(chain_norm, request.asset_in)
        # Fallback: exotic tokens (GMT, long-tail) aren't in the symbol registry.
        # The pool's underlying token ADDRESSES (from DefiLlama) resolve on-chain,
        # so use one of them as the deposit token — Enso zaps it into the LP.
        if token_in_meta is None:
            for _addr in (extra.get("underlying_tokens") or extra.get("underlyingTokens") or []):
                if isinstance(_addr, str) and _addr.lower().startswith("0x") and len(_addr) == 42:
                    token_in_meta = await resolve_any_evm_token(chain_norm, _addr)
                    if token_in_meta is not None:
                        break
        if token_in_meta is None:
            raise ValueError(
                f"Enso: cannot resolve token {request.asset_in} on {request.chain}. "
                f"Pass an ERC20 contract address or a known symbol."
            )
        token_in_addr, decimals = token_in_meta

        protocol_slug = normalize_protocol(request.protocol)

        # Allow callers to override the position token (V3 NFT pool addresses,
        # bespoke vaults not in Enso's index).
        explicit_position = extra.get("position_token")

        if explicit_position:
            token_out_addr = explicit_position
            apy_hint = extra.get("apy")
            tvl_hint = extra.get("tvl")
        else:
            # Aliases here cover protocol-slug variants Enso uses internally
            # — when a hub's main alias misses (e.g. frax → frax-sfrxeth),
            # walk a fallback list before declaring unsupported. Without this
            # Frax/Stader/Kelp/Renzo style LST hubs surface adapter_build_failed
            # even though Enso indexes them under a sibling name.
            _SLUG_FALLBACKS: dict[str, list[str]] = {
                "frax-sfrxeth": ["frax-finance", "frax-ether", "frax", "staked-frax-ether"],
                "stader-ethx": ["stader-labs", "stader", "staked-eth"],
                "kelp-rseth": ["kelp-dao", "kelp"],
                "swell-rsweth": ["swell-network", "swell", "swelleth"],
                "renzo-ezeth": ["renzo-protocol", "renzo"],
                "puffer-pufeth": ["puffer-finance", "puffer"],
                "mantle-staked-eth": ["mantle-lsp", "mantle"],
            }
            tried = [protocol_slug] + _SLUG_FALLBACKS.get(protocol_slug, [])
            position = None
            for try_slug in tried:
                position = await resolve_position(
                    chain_id=chain_id,
                    protocol_slug=try_slug,
                    underlying_addr=token_in_addr,
                )
                if position is not None:
                    break
            # Last-resort hardcoded receipt-token addresses for LST hubs that
            # Enso doesn't index under any slug we know. These are canonical
            # mainnet contracts; the Enso /shortcuts/route still builds the
            # swap path because the receipt tokens are tradable on Curve /
            # Uniswap. Empty per chain when no override.
            override_used = False
            if position is None:
                _RECEIPT_BY_HUB: dict[int, dict[str, str]] = {
                    1: {  # ethereum
                        "frax-sfrxeth": "0xac3e018457b222d93114458476f3e3416abbe38f",
                        "kelp-rseth": "0xa1290d69c65a6fe4df752f95823fae25cb99e5a7",
                        "swell-rsweth": "0xfae103dc9cf190ed75350761e95403b7b8afa6c0",
                        "renzo-ezeth": "0xbf5495efe5db9ce00f80364c8b423567e58d2110",
                        "puffer-pufeth": "0xd9a442856c234a39a81a089c06451ebaa4306a72",
                        "mantle-staked-eth": "0xd5f7838f5c461feff7fe49ea5ebaf7728bb0adfa",
                    },
                    8453: {  # base — Aave V3 aTokens cover the most common deposit flow
                        "aave-v3:usdc": "0x4e65fe4dba92790696d040ac24aa414708f5c0ab",  # aBasUSDC
                        "aave-v3:weth": "0xd4a0e0b9149bcee3c920d2e00b5de09138fd8bb7",  # aBasWETH
                        "aave-v3:cbeth": "0xcf3d55c10db69f28fd1a75bd73f3d8a2d9c595ad",
                    },
                    10: {  # optimism
                        "aave-v3:usdc": "0x38d693ce1df5aadf7bc62595a37d667ad57922e5",
                        "aave-v3:usdt": "0x6ab707aca953edaefbc4fd23ba73294241490620",
                        "aave-v3:weth": "0xe50fa9b3c56ffb159cb0fca61f5c9d750e8128c8",
                    },
                    42161: {  # arbitrum
                        "aave-v3:usdc": "0x724dc807b04555b71ed48a6896b6f41bb6c2b3b3",
                        "aave-v3:usdc.e": "0x625e7708f30ca75bfd92586e17077590c60eb4cd",
                        "aave-v3:weth": "0xe50fa9b3c56ffb159cb0fca61f5c9d750e8128c8",
                    },
                    137: {  # polygon
                        "aave-v3:usdc": "0xa4d94019934d8333ef880abffbf2fdd611c762bd",
                        "aave-v3:usdt": "0x6ab707aca953edaefbc4fd23ba73294241490620",
                        "aave-v3:wmatic": "0x6d80113e533a2c0fe82eabd35f1875dcea89ea97",
                    },
                }
                hub_map = _RECEIPT_BY_HUB.get(chain_id, {})
                # Two key shapes accepted:
                #   - protocol_slug only (LST hubs — Renzo/Kelp/etc.)
                #   - protocol_slug:asset_in (Aave V3 aTokens — per-asset receipt)
                _asset_key = f"{protocol_slug}:{request.asset_in.lower()}"
                override = hub_map.get(_asset_key) or hub_map.get(protocol_slug)
                if override:
                    token_out_addr = override
                    apy_hint = extra.get("apy")
                    tvl_hint = extra.get("tvl")
                    override_used = True
            if position is None and not override_used and token_in_addr == NATIVE_PLACEHOLDER:
                # Native ETH path — protocol may index WETH as underlying.
                wrapped_meta = await resolve_any_evm_token(chain_norm, "WETH")
                if wrapped_meta:
                    for try_slug in tried:
                        position = await resolve_position(
                            chain_id=chain_id,
                            protocol_slug=try_slug,
                            underlying_addr=wrapped_meta[0],
                        )
                        if position is not None:
                            break
            if position is None and not override_used:
                raise ValueError(
                    f"Enso: no position token indexed for {request.protocol} {request.asset_in} on "
                    f"{request.chain}. Try a different asset or pass extra={{'position_token': '0x...'}}."
                )
            if position is not None:
                token_out_addr = position.position_address
                apy_hint = position.apy
                tvl_hint = position.tvl

        amount_units = _to_unit(request.amount_in, decimals)
        if amount_units <= 0:
            raise ValueError("Enso: amount_in must be > 0")

        from src.routing.enso_client import EnsoClient
        client = EnsoClient()
        try:
            response = await client.build(
                chain_id=chain_id,
                token_in=token_in_addr,
                token_out=token_out_addr,
                amount_in=str(amount_units),
                from_addr=request.user_address,
                slippage_bps=request.slippage_bps,
            )
        except Exception as exc:
            from src.defi.execution.error_decoder import decode_evm_revert
            import re as _re
            raw_msg = str(exc)
            decoded = decode_evm_revert(raw_msg)
            hint = f" Hint: {decoded}" if decoded else ""
            # Scrub Enso URLs from the surfaced error — they contain our wallet
            # address, the user's input amount, and the API base. Quoting them
            # back to the user in the chat is noisy and confusing.
            scrubbed = _re.sub(r"https?://api\.enso\.finance/[^\s'\"]+", "<enso api>", raw_msg)
            scrubbed = _re.sub(r"For more information check[^.]*\.\s*", "", scrubbed)
            # Common 422 = invalid amount / insufficient liquidity. Map to
            # something a tester can act on.
            user_hint = ""
            if "422" in scrubbed:
                user_hint = (
                    " (Enso returned 422 Unprocessable Entity — usually means the "
                    "amount is outside the route's liquidity, or the input token "
                    "isn't supported on this chain. Try a smaller amount or a "
                    "different protocol.)"
                )
            raise ValueError(
                f"Enso /shortcuts/route failed for {request.protocol} {request.asset_in} on {request.chain}: "
                f"{scrubbed.strip()}{user_hint}.{hint}"
            ) from exc

        unsigned = response.get("unsigned_tx") or {}
        to_addr = unsigned.get("to")
        data = unsigned.get("data")
        value = unsigned.get("value", "0x0")
        gas_estimate = unsigned.get("gas")
        sim = response.get("simulation") or {}
        if not to_addr or not data:
            raise ValueError("Enso returned an empty calldata payload; cannot build executable step.")

        # BUG-RC-023: replace the generic 'review the destination contract'
        # boilerplate with a pool-specific risk callout that names the
        # protocol + chain + estimated price impact. The generic line
        # was identical on every Enso card and lost signal value.
        # BUG-RC-022: annotate the receipt-token address with a
        # verification context line so the user knows what to compare
        # the rendered address against on Etherscan / Solscan.
        risk_lines = [
            f"Enso routes one bundled tx (approve → swap → deposit) for "
            f"{request.protocol} on {request.chain}. Verify the destination "
            f"contract matches the {request.protocol} pool address you "
            f"intended — Enso is the executor, not the receiving protocol.",
            f"Receipt token: {token_out_addr} — open this address on the "
            f"chain's explorer and verify the contract name reads "
            f"'{request.protocol}' or its canonical position-token symbol.",
        ]
        if apy_hint is not None:
            risk_lines.append(f"Pool APY (Enso quote): {apy_hint:.2f}%")
        if tvl_hint is not None:
            try:
                risk_lines.append(f"Pool TVL (Enso quote): ${tvl_hint:,.0f}")
            except (TypeError, ValueError):
                pass
        if sim.get("price_impact_bps") is not None:
            risk_lines.append(f"Quoted price impact: {sim['price_impact_bps']} bps")

        gas_value: str | None = None
        if gas_estimate is not None:
            try:
                gas_value = hex(int(gas_estimate))
            except (TypeError, ValueError):
                gas_value = None

        step = make_step(
            index=1,
            action="supply",
            title=f"Deposit {request.asset_in} into {request.protocol} via Enso",
            description=(
                f"Enso shortcut routes {request.amount_in} {request.asset_in} into {request.protocol} on {request.chain}. "
                f"You receive the protocol's position token ({token_out_addr[:10]}…)."
            ),
            chain=request.chain,
            wallet="MetaMask",
            protocol=request.protocol,
            asset_in=request.asset_in,
            amount_in=str(request.amount_in),
            asset_out=f"{request.protocol}-position",
            slippage_bps=request.slippage_bps,
            gas_estimate_usd=4.5,
            duration_estimate_s=30,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=chain_id,
                to=to_addr,
                data=data,
                value=str(value),
                gas=gas_value,
                spender=to_addr,
            ),
            risk_warnings=risk_lines,
        )
        return [step]

    async def verify(self, request: YieldVerifyRequest) -> VerifyResult:
        """Parse the receipt with awareness of the Enso-routed protocol.

        Enso bundles approvals + swaps + final supply into one tx, so the
        receipt carries logs from many contracts. Strategy:

        1. If ``expected_position.protocol`` resolves to a known canonical
           deposit topic0 (Aave Supply, Compound Supply, ERC-4626 Deposit,
           etc.), look for THAT — it's the strongest possible signal.
        2. Otherwise fall back to a two-leg ERC-20 Transfer check: user
           sent the input AND user received a position token. If both
           directions are present the supply settled; if only one is
           present we surface an ``ambiguous`` reason rather than lie.
        """
        receipt = request.receipt or (request.expected_position or {}).get("receipt")
        exp = request.expected_position or {}
        protocol_raw = exp.get("protocol") or exp.get("routed_protocol")
        if isinstance(protocol_raw, str):
            slug = normalize_protocol(protocol_raw)
            topic = _PROTOCOL_DEPOSIT_TOPIC0.get(slug) or _PROTOCOL_DEPOSIT_TOPIC0.get(protocol_raw.lower())
        else:
            topic = None

        if topic is not None:
            return parse_receipt_logs(receipt, topic)

        # Fallback path — generic ERC-20 Transfer reconciliation.
        if not receipt or not isinstance(receipt, dict):
            return VerifyResult(
                confirmed=False,
                detail="Enso verify: no receipt provided and no known deposit topic0 for protocol.",
            )
        logs = receipt.get("logs", []) or []
        user_addr = _normalize_addr(exp.get("user_address") or request.user_address)
        protocol_addr = _normalize_addr(exp.get("protocol_address") or exp.get("position_token") or exp.get("to"))

        sent_from_user = False
        received_by_user = False
        transfer_count = 0
        for log in logs:
            if not isinstance(log, dict):
                continue
            topics = log.get("topics") or []
            if not topics or not isinstance(topics[0], str):
                continue
            if topics[0].lower() != _TRANSFER_TOPIC0:
                continue
            transfer_count += 1
            if len(topics) < 3:
                continue
            from_topic, to_topic = topics[1], topics[2]
            if user_addr and _topic_addr_match(from_topic, user_addr):
                if protocol_addr is None or _topic_addr_match(to_topic, protocol_addr):
                    sent_from_user = True
            if user_addr and _topic_addr_match(to_topic, user_addr):
                received_by_user = True

        if sent_from_user and received_by_user:
            return VerifyResult(
                confirmed=True,
                detail=(
                    f"Enso receipt: user→protocol AND protocol→user Transfer legs both present "
                    f"({transfer_count} Transfer log(s) total)."
                ),
                receipt=receipt,
                event_signature=_TRANSFER_TOPIC0,
                log_match=transfer_count,
            )
        if user_addr is None:
            reason = "no user_address available to reconcile Transfer legs"
        elif transfer_count == 0:
            reason = "no ERC-20 Transfer logs present on receipt"
        else:
            missing = []
            if not sent_from_user:
                missing.append("user→protocol leg missing")
            if not received_by_user:
                missing.append("protocol→user leg missing")
            reason = "ambiguous: " + " and ".join(missing)
        return VerifyResult(
            confirmed=False,
            detail=f"Enso verify fallback inconclusive — {reason}.",
            receipt={"reason": reason, "transfer_log_count": transfer_count},
            log_match=transfer_count,
        )
