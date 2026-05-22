"""Build a real ExecutionPlanV3 for a specific yield action through registry adapters."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from src.agent.protocol_urls import classify_pool_kind, get_exec_capability, pool_protocol_url
from src.agent.tools._base import err_envelope, ok_envelope
from src.defi.apr_curve import compose_apr_curve, empirical_cdf_or_fallback
from src.defi.execution.adapters.base import YieldBuildRequest
from src.defi.execution.capabilities import build_default_registry
from src.defi.execution.models import ExecutionBlocker, ExecutionPlanV3
from src.defi.execution.preflight import WalletInventory, evaluate_preflight
from src.defi.recovery import FailureKind, Recovery, RecoveryAction, decide_recovery
from src.defi.strategy.memory import (
    StrategyRecord,
    pick_alt_pools,
    remember_strategy,
)


def _synth_cdf_30d(sym0: str, sym1: str) -> list[dict[str, float]]:
    """Synthetic 30-day price-ratio CDF for the V3 range card.

    Real implementation would fetch CoinGecko hourly prices over 30 days and
    compute empirical CDF over price-ratio buckets. Until that's wired, emit
    a smooth Gaussian-like CDF anchored to current price (ratio=1.0) so the
    frontend always has 30+ samples to render the in-range probability curve.
    Volatility is heuristic-tightened for stable pairs and widened for blue
    chips. Frontend can replace with live CDF when available.
    """
    import math

    a, b = (sym0 or "").upper(), (sym1 or "").upper()
    stables = {"USDC", "USDT", "DAI", "FRAX", "LUSD", "USDS", "TUSD", "BUSD",
               "FDUSD", "USDBC", "USDE", "SDAI", "SUSDE"}
    if a in stables and b in stables:
        sigma = 0.003  # 0.3% std dev — peg-tight
    elif a in stables or b in stables:
        sigma = 0.18  # 18% std dev — blue-chip vs stable
    else:
        sigma = 0.30  # exotic / blue-blue cross

    samples = []
    for i in range(30):
        # 30 buckets across [0.4, 2.5] ratio range
        t = i / 29.0
        ratio = 0.4 + (2.5 - 0.4) * t
        # Approximate Gaussian CDF via tanh
        z = (math.log(ratio)) / sigma
        cdf = 0.5 * (1.0 + math.tanh(z * 0.7978))  # erf(z/sqrt(2)) ≈ tanh(z*0.7978)
        samples.append({"ratio": round(ratio, 4), "cdf": round(cdf, 6)})
    return samples


def _augment_curve_with_four_factor_apr(
    bucket_curve: list[dict[str, float]] | None,
    pool_fee_apr_pct: float | None,
) -> list[dict[str, float]]:
    """Spec §6e four-factor composition.

        APR(width) = P_in(width) * CE(width) * fee_yield_full(pool) - IL_drag(width, vol)

    Each empirical-CDF bucket is `{"ratio": r, "cdf": p}`. We interpret the
    distance from ratio=1.0 (current) as a symmetric range half-width in bps,
    use the bucket CDF as P_in, derive 30-day vol from the CDF's 16-84th
    percentile spread, and feed (pool_fee_apr / 100) as fee_yield_full.

    Falls back to the unmodified curve when fee_apr or curve are missing —
    preserves the existing legacy `cdf` field for frontend backward compat
    and adds `composed_apr` per bucket for §6e consumers.
    """
    if not bucket_curve:
        return []
    fee_frac = (pool_fee_apr_pct or 0.0) / 100.0
    if fee_frac <= 0:
        # Pass through unchanged — composed APR cannot be assembled without fee.
        return list(bucket_curve)
    # Estimate 30-day vol from the empirical CDF: half-spread of 16-84th percentile
    # in log-ratio space approximates 1 sigma of a lognormal price-ratio.
    import math as _math
    ratios = [float(b.get("ratio") or 0.0) for b in bucket_curve]
    cdfs = [float(b.get("cdf") or 0.0) for b in bucket_curve]
    r16 = r84 = None
    for r, c in zip(ratios, cdfs):
        if r16 is None and c >= 0.16:
            r16 = r
        if r84 is None and c >= 0.84:
            r84 = r
            break
    if r16 and r84 and r16 > 0 and r84 > 0:
        vol_30d = abs(_math.log(r84 / r16)) / 2.0
    else:
        vol_30d = 0.3  # exotic default; matches _synth_cdf_30d
    p_in_curve = cdfs
    width_bps_curve = [int(round(abs(r - 1.0) * 10000.0)) for r in ratios]
    composed = compose_apr_curve(p_in_curve, width_bps_curve, fee_frac, vol_30d)
    out: list[dict[str, float]] = []
    for bucket, apr in zip(bucket_curve, composed):
        new_bucket = dict(bucket)
        new_bucket["composed_apr"] = round(float(apr), 6)
        out.append(new_bucket)
    return out


def _coerce_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


# DeFi acronyms that should stay uppercase after .title() — otherwise "raydium-amm"
# → "Raydium-Amm" and "deposit_lp" → "Deposit Lp" leak into user-facing copy.
_ACRONYMS = {"AMM", "CLMM", "DLMM", "LP", "DEX", "CL", "CP", "NFT",
             "V2", "V3", "V4", "USDC", "USDT", "DAI", "ETH", "SOL", "BNB", "BTC"}


def _humanize_token(tok: str) -> str:
    up = tok.upper()
    if up in _ACRONYMS:
        return up
    return tok.capitalize()


def humanize_protocol(name: str) -> str:
    """`raydium-amm` -> `Raydium AMM`, `uniswap-v3` -> `Uniswap V3`."""
    if not name:
        return ""
    return " ".join(_humanize_token(p) for p in name.replace("_", "-").split("-") if p)


def humanize_action(name: str) -> str:
    """`deposit_lp` -> `Deposit LP`, `prep_swap` -> `Prep Swap`."""
    if not name:
        return ""
    return " ".join(_humanize_token(p) for p in name.replace("-", "_").split("_") if p)


async def build_yield_execution_plan(
    ctx,
    *,
    chain: str,
    protocol: str,
    action: str,
    asset_in: str,
    amount_in: Any,
    asset_out: str | None = None,
    user_address: str | None = None,
    slippage_bps: int = 50,
    inventory: dict[str, Any] | None = None,
    research_thesis: str | None = None,
    extra: dict[str, Any] | None = None,
):
    # Wave-11 D-P0-10b verb-inversion guard. Matrix wave-10 D05 t2 surfaced
    # a context-bleed regression: prompt "Exit Balancer wsteth-weth with 0.5
    # BPT" was reaching this tool with action="deposit_lp" because the live
    # LLM-based intent extractor bled t1's deposit context into t2. The
    # deterministic `detect_intent` parser routes this correctly to
    # action="exit_pool"; the LLM dispatcher overrides. Resulting in a
    # READY 3-step joinPool DEPOSIT plan for an EXIT request — drain-
    # equivalent.
    #
    # Defense: refuse any verb-inverted dispatch where the user message
    # carries an exit/withdraw/remove verb but action is on the deposit
    # side. user_message arrives via extra (set by the runtime when the
    # tool is dispatched).
    _extra_for_verb_guard = extra or {}
    _user_message = (
        _extra_for_verb_guard.get("user_message")
        or _extra_for_verb_guard.get("cross_chain_message")
        or ""
    )

    # BUG-RC-001 — protocol-name guard. When the user explicitly named a
    # protocol family in the message ("Aave V3", "Compound", "Fluid",
    # "Spark", etc.) but the dispatcher selected a DIFFERENT protocol,
    # refuse with INTENT_MISMATCH rather than silently substituting.
    # This is the surgical close for AI Bug Convo.md lines 801-833 where
    # 'Supply 100 USDC to Aave V3 on Base' silently routed to
    # 'fluid-lending'. Full LiquidityIntent envelope wire-up (P1-C-006)
    # would do this via structured LLM extraction — this regex guard
    # catches the obvious case without an LLM call.
    if _user_message and isinstance(_user_message, str) and protocol:
        import re as _re_proto_guard
        _USER_PROTOCOL_RE = _re_proto_guard.compile(
            r"\b(?P<proto>aave(?:[\s-]?v[23])?|compound(?:[\s-]?v[23])?|"
            r"fluid(?:[\s-]?lending)?|spark(?:[\s-]?protocol|[\s-]?lending)?|"
            r"morpho(?:[\s-]?blue)?|metamorpho|"
            r"yearn(?:[\s-]?finance|[\s-]?v[23])?|"
            r"curve(?:[\s-]?dex)?|balancer(?:[\s-]?v[23])?|"
            r"sky(?:[\s-]?lending|maker(?:dao)?)?|"
            r"lido|rocket[\s-]?pool|rocketpool|ether[\.\-]?fi|etherfi|"
            r"frax(?:[\s-]?ether)?|stader|"
            r"uniswap(?:[\s-]?v[234])?|pancakeswap(?:[\s-]?v[23])?|sushiswap|"
            r"aerodrome(?:[\s-]?slipstream|[\s-]?cl)?|velodrome(?:[\s-]?cl)?|"
            r"raydium(?:[\s-]?amm|[\s-]?clmm)?|orca(?:[\s-]?whirlpools)?|"
            r"meteora(?:[\s-]?dlmm)?|kamino(?:[\s-]?lend|[\s-]?liquidity)?|"
            r"jupiter(?:[\s-]?lend|[\s-]?perps|[\s-]?staked[\s-]?sol)?|"
            r"pendle|stargate|moonwell|venus|gmx)\b",
            _re_proto_guard.IGNORECASE,
        )
        _user_proto_m = _USER_PROTOCOL_RE.search(_user_message)
        if _user_proto_m:
            _user_proto_raw = _re_proto_guard.sub(
                r"\s+", "-", _user_proto_m.group("proto").lower().strip()
            )
            # Normalize to a canonical "family" head — strip version
            # suffix (-v2/-v3/-v4) for the comparison, since 'aave' and
            # 'aave-v3' are the same family but 'aave' vs 'fluid' is a
            # real substitution.
            def _family_head(p: str) -> str:
                p = p.lower().replace(" ", "-").strip()
                # Strip version suffix
                p = _re_proto_guard.sub(r"[-_]?v\d+$", "", p)
                # Strip family suffix (-lending, -finance, -dex)
                p = _re_proto_guard.sub(
                    r"[-_]?(lending|finance|dex|protocol|slipstream|cl|"
                    r"amm|clmm|whirlpools|dlmm|blue)$",
                    "", p,
                )
                # Aliases
                return {
                    "rocketpool": "rocket-pool",
                    "ether-fi": "etherfi",
                    "ether.fi": "etherfi",
                    "metamorpho": "morpho",
                    "frax-ether": "frax",
                    "makerdao": "sky",
                    "maker": "sky",
                }.get(p, p)
            _user_family = _family_head(_user_proto_raw)
            _dispatched_family = _family_head(str(protocol))
            if (
                _user_family
                and _dispatched_family
                and _user_family != _dispatched_family
            ):
                plan = ExecutionPlanV3.new(
                    title=(
                        f"Intent mismatch — refusing to substitute "
                        f"{_user_family} → {_dispatched_family}"
                    ),
                    summary=(
                        f"You asked for {_user_family!r} but the dispatcher "
                        f"selected {_dispatched_family!r}. Refusing to "
                        f"silently route your intent to a different protocol."
                    ),
                )
                plan.add_blocker(ExecutionBlocker(
                    code="INTENT_MISMATCH",
                    severity="blocker",
                    title=(
                        f"Protocol substitution refused: "
                        f"{_user_family} != {_dispatched_family}"
                    ),
                    detail=(
                        f"Your message named {_user_family!r} as the target "
                        f"protocol, but the dispatcher resolved this request "
                        f"to {_dispatched_family!r}. To proceed, either "
                        f"(a) re-issue naming the dispatcher's protocol "
                        f"explicitly, or (b) widen the prompt so the "
                        f"intended protocol is unambiguous (e.g. include "
                        f"chain + asset + version: 'Supply 100 USDC to "
                        f"{_user_family} V3 on Base')."
                    ),
                    affected_step_ids=[],
                    cta=f"Re-issue with the {_user_family} pool explicitly.",
                ))
                return ok_envelope(
                    data={"plan": plan.to_dict()},
                    card_type="execution_plan_v3",
                    card_payload=plan.to_dict(),
                )

    if _user_message and isinstance(_user_message, str):
        import re as _re_verb
        _exit_verb_re = _re_verb.compile(
            r"^\s*(?:exit|withdraw|remove|redeem|unstake|liquid[-\s]unstake|"
            r"close|claim|harvest)\b",
            _re_verb.IGNORECASE,
        )
        _deposit_actions = {
            "supply", "deposit_lp", "add_liquidity", "stake",
            "deposit", "join_pool", "joinpool", "buy", "lp",
        }
        if (
            _exit_verb_re.match(_user_message)
            and str(action).lower() in _deposit_actions
        ):
            # Reshape into a structured blocker so the user sees a typed
            # refusal instead of getting silently routed to a deposit.
            # BUG-RC-003 fix: removed redundant in-function import — the
            # module-level import at line 12 already provides
            # ExecutionBlocker. A duplicate `from … import …` inside this
            # function bound the name as a function-local, which made
            # every other branch that referenced ExecutionBlocker (lines
            # 269, 422, 472, etc.) raise UnboundLocalError when reached
            # before this branch.
            plan = ExecutionPlanV3.new(
                title="Verb inverted — refusing deposit for exit request",
                summary=(
                    f"Your prompt starts with an exit/withdraw verb but the "
                    f"dispatcher selected action={action!r}. Refusing to "
                    f"silently route a withdraw intent to a deposit plan "
                    f"(would deposit funds when you meant to withdraw)."
                ),
            )
            plan.add_blocker(ExecutionBlocker(
                code="VERB_INVERTED",
                severity="blocker",
                title="Withdraw intent routed to deposit action — refused",
                detail=(
                    f"User prompt: {_user_message[:120]!r}. "
                    f"Action passed: {action!r}. "
                    f"Use the lifecycle verb form explicitly (e.g. "
                    f"'Exit <protocol> <pool> with <amount> <token>') "
                    f"or re-issue with action=exit_pool / withdraw_lp / "
                    f"remove_liquidity."
                ),
                affected_step_ids=[],
                cta="Re-issue with withdraw verb",
            ))
            return ok_envelope(
                data={"plan": plan.to_dict()},
                card_type="execution_plan_v3",
                card_payload=plan.to_dict(),
            )

    # Resolve user_address early so the composed-plan branch + non-composed
    # path both see the EVM/Solana wallet without raising "wallet missing".
    if not user_address:
        wallet = getattr(ctx, "wallet", None)
        if wallet:
            user_address = str(wallet)
        if not user_address:
            evm_alt = getattr(ctx, "evm_wallet", None)
            if evm_alt:
                user_address = str(evm_alt)
    # §6c composed-plan branch — when intent carries extra.source_chain that
    # differs from `chain`, snapshot a deBridge DLN bridge quote first, block
    # the deposit step on PENDING_DST_FILL, and let the runtime rebuild it
    # with the actual fill amount after the webhook resolves.
    extra_dict_pre = extra or {}
    src_chain_hint = (extra_dict_pre.get("source_chain") or "").lower()
    # Pass A rows 10-11: cross-chain intent must NEVER route to pool_link.
    # When the caller supplied a free-form `user_message` (or set
    # `extra.cross_chain_message`), backstop the routing by inferring the
    # source/dest chains from the prose. If the destination matches the
    # `chain` argument and the source differs, force composed_plan. If the
    # destination is set but the source can't be unambiguously extracted,
    # surface CROSS_CHAIN_SOURCE_AMBIGUOUS instead of silently routing to
    # pool_link (the E04-E14 bug class).
    cross_chain_message = (
        extra_dict_pre.get("cross_chain_message")
        or extra_dict_pre.get("user_message")
        or ""
    )
    if cross_chain_message and not src_chain_hint:
        from src.agent.cross_chain import (
            cross_chain_source_blocker_payload,
            infer_cross_chain_hint,
        )

        hint = infer_cross_chain_hint(cross_chain_message)
        if hint.is_cross_chain and hint.needs_source_blocker:
            plan = ExecutionPlanV3.new(
                title="Cross-chain plan — source chain missing",
                summary=(
                    "Cross-chain intent detected but the source chain "
                    "wasn't specified. Re-prompt with 'from <chain>'."
                ),
            )
            blocker_payload = cross_chain_source_blocker_payload(
                dest_chain=hint.dest_chain, message=cross_chain_message,
            )
            plan.add_blocker(ExecutionBlocker(
                code=blocker_payload["code"],
                severity=blocker_payload["severity"],
                title=blocker_payload["title"],
                detail=blocker_payload["detail"],
                affected_step_ids=[],
                cta=blocker_payload["cta"],
            ))
            plan_dict = plan.to_dict()
            plan_dict["recovery"] = Recovery(
                action=RecoveryAction.ASK_USER,
                posture="Ask user for the source chain.",
                buttons=["Specify source chain", "Cancel"],
                rationale=(
                    "Cross-chain motion needs both endpoints. Refusing to "
                    "default to dest-only so the bridge leg quote isn't "
                    "silently dropped."
                ),
            ).to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )
        if (
            hint.is_cross_chain
            and hint.source_chain
            and hint.dest_chain
            and hint.source_chain != hint.dest_chain
            and (chain or "").lower() in {hint.dest_chain, ""}
        ):
            src_chain_hint = hint.source_chain
            if not chain:
                chain = hint.dest_chain
    if src_chain_hint and src_chain_hint != (chain or "").lower():
        from src.defi.execution.composed_plan import (
            Snapshot, block_step_for_async_fill, snapshot_bridge_quote,
        )
        # ExecutionPlanV3 + ExecutionStepV3 are imported at module top; only
        # bring in the helpers we don't already have.
        from src.defi.execution.models import UnsignedStepTransaction, make_step
        from src.routing.debridge_client import DeBridgeBridge
        _CHAIN_ID_MAP = {
            "ethereum": 1, "polygon": 137, "arbitrum": 42161, "optimism": 10,
            "base": 8453, "avalanche": 43114, "bsc": 56,
            # deBridge Solana cluster ID per docs.debridge.finance/dln/api
            "solana": 7565164,
        }
        # Per-chain stablecoin + native + LST symbol → address map. deBridge DLN
        # rejects symbol names with HTTP 400; the API needs the EVM contract or
        # the SPL mint for Solana. Native ETH on EVM chains is normalised to
        # the canonical WETH9 address with auto-wrap handled by deBridge DLN's
        # order builder (ETH → wrap → WETH → bridge → unwrap on dst).
        _TOKEN_ADDRS: dict[tuple[str, str], tuple[str, int]] = {
            ("ethereum", "USDC"): ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
            ("ethereum", "USDT"): ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
            ("ethereum", "DAI"):  ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
            ("ethereum", "WETH"): ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
            ("ethereum", "ETH"):  ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
            ("ethereum", "WBTC"): ("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", 8),
            ("base", "USDC"):     ("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
            ("base", "WETH"):     ("0x4200000000000000000000000000000000000006", 18),
            ("base", "ETH"):      ("0x4200000000000000000000000000000000000006", 18),
            ("arbitrum", "USDC"): ("0xaf88d065e77c8cc2239327c5edb3a432268e5831", 6),
            ("arbitrum", "USDT"): ("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", 6),
            ("arbitrum", "DAI"):  ("0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
            ("arbitrum", "WETH"): ("0x82af49447d8a07e3bd95bd0d56f35241523fbab1", 18),
            ("arbitrum", "ETH"):  ("0x82af49447d8a07e3bd95bd0d56f35241523fbab1", 18),
            ("optimism", "USDC"): ("0x0b2c639c533813f4aa9d7837caf62653d097ff85", 6),
            ("optimism", "USDT"): ("0x94b008aa00579c1307b0ef2c499ad98a8ce58e58", 6),
            ("optimism", "DAI"):  ("0xda10009cbd5d07dd0cecc66161fc93d7c9000da1", 18),
            ("optimism", "WETH"): ("0x4200000000000000000000000000000000000006", 18),
            ("optimism", "ETH"):  ("0x4200000000000000000000000000000000000006", 18),
            ("polygon", "USDC"):  ("0x3c499c542cef5e3811e1192ce70d8cc03d5c3359", 6),
            ("polygon", "USDT"):  ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6),
            ("polygon", "DAI"):   ("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063", 18),
            ("polygon", "WETH"):  ("0x7ceb23fd6bc0add59e62ac25578270cff1b9f619", 18),
            ("base", "USDT"):     ("0xfde4c96c8593536e31f229ea8f37b2ada2699bb2", 6),
            ("base", "DAI"):      ("0x50c5725949a6f0c72e6c4a641f24049a917db0cb", 18),
            ("avalanche", "USDC"):("0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e", 6),
            ("avalanche", "WETH"):("0x49d5c2bdffac6ce2bfdb6640f4f80f226bc10bab", 18),
            ("avalanche", "ETH"): ("0x49d5c2bdffac6ce2bfdb6640f4f80f226bc10bab", 18),
            ("bsc", "USDC"):      ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
            ("bsc", "USDT"):      ("0x55d398326f99059ff775485246999027b3197955", 18),
            ("bsc", "WETH"):      ("0x2170ed0880ac9a755fd29b2688956bd959f933f8", 18),
            ("bsc", "ETH"):       ("0x2170ed0880ac9a755fd29b2688956bd959f933f8", 18),
            # Solana SPL mints — required for ETH/BSC/Polygon ↔ Solana bridging
            ("solana", "USDC"):   ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 6),
            ("solana", "USDT"):   ("Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 6),
            ("solana", "SOL"):    ("So11111111111111111111111111111111111111112", 9),
            ("solana", "WSOL"):   ("So11111111111111111111111111111111111111112", 9),
        }
        src_sym = str(extra_dict_pre.get("source_token") or asset_in).upper()
        dst_sym = str(asset_in).upper()
        src_meta = _TOKEN_ADDRS.get((src_chain_hint, src_sym))
        dst_meta = _TOKEN_ADDRS.get(((chain or "").lower(), dst_sym))
        if src_meta is None or dst_meta is None:
            return err_envelope(
                "composed_plan_token_unknown",
                f"deBridge needs the EVM contract for {src_sym}@{src_chain_hint} or "
                f"{dst_sym}@{chain}. Add the (chain, symbol) entry to "
                f"_TOKEN_ADDRS or pass extra.source_token_address.",
            )
        src_addr, src_dec = src_meta
        if not user_address or user_address == "0x0":
            return err_envelope(
                "composed_plan_wallet_missing",
                "Cross-chain composed plan needs an EVM wallet address. "
                "Reconnect MetaMask and retry.",
            )
        amount_units = int(float(amount_in) * 10 ** src_dec)
        try:
            bridge = DeBridgeBridge()
            snap = await snapshot_bridge_quote(
                bridge,
                src_chain_id=_CHAIN_ID_MAP.get(src_chain_hint, 0),
                dst_chain_id=_CHAIN_ID_MAP.get((chain or "").lower(), 0),
                token_in=src_addr,
                token_out=dst_meta[0],
                amount=amount_units,
                recipient=user_address,
            )
        except Exception as exc:  # noqa: BLE001
            return err_envelope(
                "composed_plan_bridge_quote_failed",
                f"deBridge DLN quote failed for {src_chain_hint}→{chain}: {exc}",
            )
        # RC7a — fetch the REAL unsigned tx envelope so the bridge step is
        # signable. Without this, the step would have transaction=None and
        # the user could click "Approve step 1" and either noop or fall
        # through to step 2 out of order (financial-loss bug). The DLN
        # /dln/order/create-tx endpoint returns {to, data, value}.
        from src.routing.debridge_client import DeBridgeClient as _LegacyDeBridge  # used by network mock test paths
        # BUG-E-002 (matrix Pass A wave 1): the guest sentinel must NEVER
        # be passed to deBridge — DLN responds HTTP 400 with a
        # mozilla.org docs URL that leaks back to the user. Gate the call
        # on a real EVM address; emit a structured WALLET_CHAIN_MISMATCH
        # blocker (the closest canonical code for "wallet not connected"
        # until a distinct code lands).
        _looks_like_evm_addr = (
            isinstance(user_address, str)
            and user_address.startswith("0x")
            and len(user_address) == 42
        )
        if (not _looks_like_evm_addr) or user_address.lower() == "guest":
            plan = ExecutionPlanV3.new(
                title="Cross-chain bridge requires a connected wallet",
                summary=(
                    f"Composed plan {src_chain_hint}→{chain} needs an EVM wallet "
                    f"address to construct the deBridge order. Connect a wallet "
                    f"and resend."
                ),
            )
            plan.add_blocker(ExecutionBlocker(
                code="WALLET_CHAIN_MISMATCH",
                severity="blocker",
                title="Wallet not connected",
                detail=(
                    f"deBridge DLN /create-tx requires senderAddress and "
                    f"recipient to be valid EVM addresses. Current "
                    f"user_address={user_address!r} is not signable. "
                    f"Connect an EVM wallet (MetaMask / Phantom EVM mode) and resend."
                ),
                affected_step_ids=[],
                cta="Connect an EVM wallet via the wallet button, then re-send the request.",
            ))
            plan_dict = plan.to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )
        try:
            order_tx = await bridge.create_order_encoded(
                src_chain_id=_CHAIN_ID_MAP.get(src_chain_hint, 0),
                dst_chain_id=_CHAIN_ID_MAP.get((chain or "").lower(), 0),
                token_in=src_addr,
                token_out=dst_meta[0],
                amount=amount_units,
                sender=user_address,
                recipient=user_address,
            )
        except Exception as exc:  # noqa: BLE001
            return err_envelope(
                "composed_plan_bridge_build_failed",
                f"deBridge DLN /create-tx failed for {src_chain_hint}→{chain}: {exc}",
            )
        bridge_tx_payload = order_tx.get("tx") or {}
        bridge_to = bridge_tx_payload.get("to")
        bridge_data = bridge_tx_payload.get("data")
        bridge_value = bridge_tx_payload.get("value") or "0x0"
        if not bridge_to or not bridge_data:
            # RC7a — DLN returned a malformed tx envelope. Refuse to emit
            # a composed plan with a null calldata bridge step; emit a
            # structured COMPOSED_PLAN_INCOMPLETE_TX blocker instead.
            plan = ExecutionPlanV3.new(
                title="Cross-chain bridge build incomplete",
                summary=(
                    f"deBridge DLN did not return signable calldata for "
                    f"{src_chain_hint}→{chain}. Refusing to emit an "
                    f"unsignable composed plan."
                ),
            )
            plan.add_blocker(ExecutionBlocker(
                code="COMPOSED_PLAN_INCOMPLETE_TX",
                severity="blocker",
                title="Bridge step has no calldata",
                detail=(
                    f"DLN order quote succeeded (quote_id={snap.quote_id}) but "
                    f"/create-tx returned tx.to={bridge_to!r}, tx.data="
                    f"{(bridge_data or '')[:20]}... Cannot construct a signable "
                    f"bridge leg. Step index: 1 (bridge)."
                ),
                affected_step_ids=[],
                cta="Retry the request; if the issue persists, the DLN solver "
                    "may be temporarily refusing this route. Try a different "
                    "bridge or smaller amount.",
            ))
            plan_dict = plan.to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )
        # Convert hex value (DLN returns "0x..." for EVM) to a plain hex
        # string we can put on UnsignedStepTransaction.value.
        if isinstance(bridge_value, int):
            bridge_value = "0x" + format(bridge_value, "x")
        plan = ExecutionPlanV3.new(
            title=f"Cross-chain {action} via deBridge DLN",
            summary=(
                f"Bridge {amount_in} {asset_in} from {src_chain_hint} to {chain} "
                f"via deBridge DLN, then {action} into {protocol}."
            ),
        )
        bridge_step = make_step(
            index=1, action="bridge", title="deBridge DLN bridge leg",
            description=(
                f"Bridge {amount_in} {asset_in} from {src_chain_hint} (chain_id "
                f"{snap.src_chain_id}) to {chain} (chain_id {snap.dst_chain_id}). "
                f"Expected dst amount {snap.expected_dst_amount} (slippage band "
                f"{snap.slippage_bps_band_min}-{snap.slippage_bps_band_max} bps). "
                f"Quote id {snap.quote_id}."
            ),
            chain=src_chain_hint, wallet="MetaMask", protocol="debridge-dln",
            asset_in=asset_in, amount_in=str(amount_in),
            asset_out=asset_in,
            slippage_bps=snap.slippage_bps_band_max,
            duration_estimate_s=300,
            transaction=UnsignedStepTransaction(
                chain_kind="evm",
                chain_id=_CHAIN_ID_MAP.get(src_chain_hint, 0),
                to=bridge_to,
                data=bridge_data,
                value=bridge_value,
                spender=bridge_to,
            ),
        )
        deposit_step = make_step(
            index=2, action=action,
            title=f"{protocol} {action} (blocked on bridge fill)",
            description=(
                f"Awaits actual dst-chain delivery from the deBridge DLN order. "
                f"Runtime auto-rebuilds with the realised amount via "
                f"composed_plan.rebuild_step_with_actual_delta."
            ),
            chain=chain, wallet="MetaMask", protocol=protocol,
            asset_in=asset_in, amount_in=str(amount_in),
        )
        from src.defi.execution.pending import debridge_fill as _debridge_pending
        block_step_for_async_fill(
            deposit_step,
            blocker_code="PENDING_DST_FILL",
            pending=_debridge_pending(),
        )
        plan.steps = [bridge_step, deposit_step]
        plan._recompute_step_statuses()
        plan._refresh_plan_status()
        # Fix-wave-3 — §13 spec-scenario blocker scan on the composed-plan
        # branch. Pass C 58517bf hand-read flagged H07/H08/H09/H10/H15 + E15
        # as silent fall-throughs in cross-chain plans. We run the scenario
        # scan BEFORE the RC7a signability gate so a present-but-unsignable
        # scenario surfaces a structured blocker rather than reaching the
        # invariant exception. `inventory` is read from `extra` when the
        # caller doesn't pass the top-level kwarg.
        try:
            from src.defi.execution.scenarios import scan_scenario_blockers
            _composed_inv = (extra_dict_pre or {}).get("inventory")
            _composed_inv_obj = None
            if _composed_inv:
                try:
                    _composed_inv_obj = _inventory_from_dict(_composed_inv)
                except Exception:  # noqa: BLE001
                    _composed_inv_obj = None
            _composed_blockers = scan_scenario_blockers(
                steps=plan.steps,
                inventory=_composed_inv_obj,
                extra=extra_dict_pre,
                protocol=protocol,
                action=action,
                asset_in=asset_in,
                chain=chain,
                user_address=user_address,
                dst_chain=chain,  # composed-plan dst is the build's `chain` arg
            )
            for _b in _composed_blockers:
                plan.add_blocker(_b)
        except Exception:  # noqa: BLE001
            # Scenario scan is best-effort; failure should not block plan
            # emission. The downstream signability gate still runs.
            pass
        # RC7a — final invariant gate. Refuse emission if any non-blocked
        # step is missing its transaction. Bridge step + any future
        # pre-bridge wrap step must be signable; only the post-bridge
        # deposit step is allowed to be blocked.
        try:
            from src.defi.execution.composed_plan import (
                ComposedPlanIncompleteTxError,
                assert_signable_composed_plan,
            )
            assert_signable_composed_plan(plan)
        except ComposedPlanIncompleteTxError as exc:
            # Reshape the exception into a structured blocker. We never
            # surface the bare exception to the user; the blocker carries
            # the offending step's index so the frontend can highlight it.
            blocker_plan = ExecutionPlanV3.new(
                title="Composed plan refused — step missing calldata",
                summary=(
                    f"Plan emission refused: step {exc.step_index} "
                    f"({exc.action}) has no signable transaction."
                ),
            )
            blocker_plan.add_blocker(ExecutionBlocker(
                code="COMPOSED_PLAN_INCOMPLETE_TX",
                severity="blocker",
                title="Step missing calldata",
                detail=(
                    f"step_index={exc.step_index} step_id={exc.step_id} "
                    f"action={exc.action} carries transaction=None and is "
                    f"not blocked. Refusing to emit an unsignable plan."
                ),
                affected_step_ids=[exc.step_id],
                cta="Retry the request or contact support.",
            ))
            plan_dict = blocker_plan.to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )
        # Stash the snapshot in the plan metadata so the rebuild loop can
        # consume it without re-fetching.
        if not hasattr(plan, "metadata") or plan.metadata is None:
            plan.metadata = {}
        plan.metadata["composed_plan_snapshot"] = snap.to_dict()
        # Register in the in-memory pending-plan registry so the deBridge
        # webhook can look up this plan by order_id and call
        # rebuild_step_with_actual_delta + promote when DLN fills the order.
        order_id = snap.quote_id  # DLN reuses quote_id as the order_id post-broadcast
        if order_id:
            try:
                from src.defi.execution.pending_plans import (
                    PendingPlan,
                    register as register_pending,
                )
                await register_pending(PendingPlan(
                    plan_id=plan.plan_id,
                    order_id=str(order_id),
                    plan=plan,
                    deposit_step=deposit_step,
                    snapshot=snap,
                    user_wallet=user_address or "",
                    src_chain=src_chain_hint,
                    dst_chain=chain,
                ))
            except Exception:  # noqa: BLE001
                # Registry failure is non-fatal — plan still surfaces with
                # PENDING_DST_FILL blocker; user can re-prompt to retry.
                pass
        return ok_envelope(
            data={"plan": plan.to_dict()},
            card_type="execution_plan_v3",
            card_payload=plan.to_dict(),
        )

    if not user_address:
        wallet = getattr(ctx, "wallet", None)
        if wallet:
            user_address = str(wallet)
    # Wallet/chain compatibility preflight. Phantom in dual-mode exposes both
    # an EVM hex address and a Solana base58 pubkey; if the primary `wallet`
    # is wrong for the target chain but the per-chain ctx field has the
    # right one, swap it in here so we don't leak Enso 422 errors when the
    # user is asking from the wrong wallet (e.g. Phantom on Solana for an
    # Ethereum supply).
    import re as _re_addr
    def _is_evm_addr(s: Any) -> bool:
        return isinstance(s, str) and s.lower().startswith("0x") and len(s) == 42
    def _is_sol_addr(s: Any) -> bool:
        return isinstance(s, str) and bool(_re_addr.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", s))
    chain_norm = (chain or "").lower()
    is_evm_chain = chain_norm in {"ethereum", "polygon", "arbitrum", "base", "optimism", "bsc", "avalanche", "linea", "scroll", "zksync"}
    is_solana_chain = chain_norm in {"solana", "sol"}
    if is_evm_chain and not _is_evm_addr(user_address):
        evm_alt = getattr(ctx, "evm_wallet", None)
        if _is_evm_addr(evm_alt):
            user_address = evm_alt  # type: ignore[assignment]
    if is_solana_chain and not _is_sol_addr(user_address):
        sol_alt = getattr(ctx, "solana_wallet", None)
        if _is_sol_addr(sol_alt):
            user_address = sol_alt  # type: ignore[assignment]
    if not user_address:
        return err_envelope(
            "missing_wallet",
            "Connect a wallet before requesting an execution plan; the plan needs a destination address.",
        )
    # F02 protocol-chain support matrix — reject combos like aave-v3 on
    # solana, marinade on ethereum, lido on bsc before they reach the
    # adapter layer (which would silently route via Enso fallback or
    # raise a leaky 422). Emit typed UNSUPPORTED_CHAIN blocker so the
    # frontend renders a real recovery card.
    _EVM_ONLY_PROTOS = {
        "aave-v3", "aave", "compound-v3", "compound", "morpho-blue", "morpho",
        "spark", "sparklend", "yearn-finance", "yearn", "lido", "rocket-pool",
        "ether.fi", "etherfi", "renzo", "swell", "frax-ether", "frax",
        "mantle-staked-ether", "kelp", "uniswap-v3", "uniswap-v2", "uniswap-v4",
        "uniswap", "pancakeswap-amm-v3", "pancakeswap", "balancer-v3",
        "balancer", "curve-dex", "curve", "convex", "pendle", "stargate",
        "gmx", "velodrome", "aerodrome", "aerodrome-slipstream",
        "moonwell", "stader", "sky-savings-rate", "sky",
    }
    _SOLANA_ONLY_PROTOS = {
        "raydium", "raydium-amm", "raydium-clmm", "raydium-cp",
        "orca", "orca-dex", "orca-whirlpools",
        "meteora", "meteora-dlmm", "meteora-vault", "meteora-amm",
        "kamino", "kamino-liquidity", "kamino-lend", "kamino-vault",
        "marinade", "marinade-liquid-staking", "marinade-native",
        "jito", "jito-liquid-staking",
        "sanctum", "sanctum-infinity", "sanctum-liquid-staking",
        "jlp", "jupiter-perps", "jupiter-perpetuals", "jupiter-perpetuals-lp",
        "drift", "phoenix", "openbook", "gmtrade",
    }
    proto_lc = (protocol or "").lower()
    if proto_lc in _EVM_ONLY_PROTOS and is_solana_chain:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=(f"{humanize_protocol(protocol)} doesn't run on Solana. "
                     f"{humanize_protocol(protocol)} is an EVM protocol — try Ethereum, "
                     f"Base, Arbitrum, Optimism, Polygon, BSC, or Avalanche."),
        )
        plan.add_blocker(ExecutionBlocker(
            code="unsupported_chain",
            severity="blocker",
            title=f"{humanize_protocol(protocol)} not deployed on Solana",
            detail=(f"{humanize_protocol(protocol)} is an EVM-only protocol. It does not "
                    f"exist on Solana. Solana lending equivalents: Kamino Lend, MarginFi. "
                    f"Solana LP equivalents: Raydium, Orca, Meteora."),
            affected_step_ids=[],
            cta=f"Pick an EVM chain (e.g. Ethereum, Base) for {humanize_protocol(protocol)}, "
                f"or switch to a Solana-native protocol (Kamino, Raydium, Orca, Marinade).",
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture=f"{humanize_protocol(protocol)} isn't deployed on Solana",
            buttons=[f"Use Kamino on Solana", f"Use {humanize_protocol(protocol)} on Base",
                     f"Use {humanize_protocol(protocol)} on Ethereum", "Cancel"],
            rationale="EVM protocol on Solana chain — no on-chain deployment exists.",
        ).to_dict()
        return ok_envelope(data={"plan": plan_dict}, card_type="execution_plan_v3", card_payload=plan_dict)
    if proto_lc in _SOLANA_ONLY_PROTOS and is_evm_chain:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=(f"{humanize_protocol(protocol)} doesn't run on {chain.title()}. "
                     f"{humanize_protocol(protocol)} is a Solana-native protocol."),
        )
        plan.add_blocker(ExecutionBlocker(
            code="unsupported_chain",
            severity="blocker",
            title=f"{humanize_protocol(protocol)} not deployed on {chain.title()}",
            detail=(f"{humanize_protocol(protocol)} is a Solana-only protocol. EVM lending "
                    f"equivalents: Aave V3, Compound V3, Morpho Blue. EVM LP equivalents: "
                    f"Uniswap V3, Balancer, Curve."),
            affected_step_ids=[],
            cta=f"Switch to Solana for {humanize_protocol(protocol)}, or pick an EVM-native "
                f"protocol (Aave V3, Compound, Morpho) for {chain.title()}.",
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture=f"{humanize_protocol(protocol)} is Solana-only",
            buttons=[f"Use {humanize_protocol(protocol)} on Solana",
                     f"Use Aave V3 on {chain.title()}", "Cancel"],
            rationale="Solana-only protocol on EVM chain — no on-chain deployment exists.",
        ).to_dict()
        return ok_envelope(data={"plan": plan_dict}, card_type="execution_plan_v3", card_payload=plan_dict)
    # If the user's wallet still doesn't match the target chain, emit a
    # structured blocker instead of running the adapter (which would raise
    # an Enso 422 with a leaky URL in the detail).
    if is_evm_chain and not _is_evm_addr(user_address):
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"{humanize_protocol(protocol)} {asset_in} on {chain[:1].upper()+chain[1:]} requires an EVM wallet.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="WALLET_CHAIN_MISMATCH",
            severity="blocker",
            title="Wrong wallet for this chain",
            detail=(
                f"This action runs on {chain} ({protocol} {asset_in}). Your connected wallet "
                f"`{str(user_address)[:12]}…` looks Solana (or otherwise non-EVM). "
                "Switch to an EVM wallet (MetaMask) and retry."
            ),
            affected_step_ids=[],
            cta="Connect an EVM wallet (MetaMask) to sign this action.",
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture="Wrong wallet — switch to MetaMask",
            buttons=["Connect MetaMask", "Try a different chain", "Cancel"],
            rationale="EVM action needs an EVM wallet. No auto-recovery possible.",
        ).to_dict()
        return ok_envelope(data={"plan": plan_dict}, card_type="execution_plan_v3", card_payload=plan_dict)
    if is_solana_chain and not _is_sol_addr(user_address):
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"{humanize_protocol(protocol)} {asset_in} on Solana requires a Solana wallet.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="WALLET_CHAIN_MISMATCH",
            severity="blocker",
            title="Wrong wallet for this chain",
            detail=(
                f"This action runs on Solana ({protocol} {asset_in}). Your connected wallet "
                f"`{str(user_address)[:12]}…` looks EVM (or otherwise non-Solana). "
                "Switch to a Solana wallet (Phantom in Solana mode) and retry."
            ),
            affected_step_ids=[],
            cta="Connect a Solana wallet (Phantom) to sign this action.",
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture="Wrong wallet — switch to Phantom",
            buttons=["Connect Phantom", "Try a different chain", "Cancel"],
            rationale="Solana action needs a Solana wallet. No auto-recovery possible.",
        ).to_dict()
        return ok_envelope(data={"plan": plan_dict}, card_type="execution_plan_v3", card_payload=plan_dict)

    # RC8 — Solana-native asset → force chain_kind=solana. Symbols like
    # MSOL, JITOSOL, BSOL, BNSOL, JUPSOL, JSOL, INF, JLP are SPL mints that
    # only exist on Solana. If the caller (or an upstream router) stamped an
    # EVM chain on a Solana-native asset, refuse the build and emit a
    # CHAIN_KIND_MISMATCH blocker — never silently route an SPL mint to an
    # EVM adapter (would either Enso-422 or, worse, sign a swap for a same-
    # symbol scam token on the wrong chain).
    # RC8-narrow (Pass B 113755f A08): exclude symbols that ALSO have an
    # Ethereum/EVM mint (USDS lives at 0xdc035d45...; PYUSD lives at
    # 0x6c3ea9036406852006290770BEdFcAbA0e23A0e8 on Ethereum). Solana-only set
    # — never let an EVM holding force a Solana plan.
    _SOLANA_NATIVE_ASSETS = {
        "MSOL", "JITOSOL", "BSOL", "BNSOL", "JUPSOL", "JSOL",
        "INF", "JLP", "JTO", "RAY", "ORCA", "BONK", "PYTH", "JUP",
        "WIF",
    }
    _asset_up = (asset_in or "").strip().upper()
    if _asset_up in _SOLANA_NATIVE_ASSETS and not is_solana_chain:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=(
                f"{_asset_up} is a Solana-native SPL mint; refusing to "
                f"build on {chain or 'unknown'} (chain_kind=evm)."
            ),
        )
        plan.add_blocker(ExecutionBlocker(
            code="CHAIN_KIND_MISMATCH",
            severity="blocker",
            title="Asset is Solana-native — wrong chain",
            detail=(
                f"{_asset_up} only exists on Solana (SPL mint). The caller "
                f"requested {protocol} {action} on chain={chain!r}. Refusing "
                f"to emit a plan that would route a Solana-native asset to "
                f"an EVM adapter. Resubmit with chain='solana'."
            ),
            affected_step_ids=[],
            cta=(
                f"Switch chain to Solana for {_asset_up}, or pick a different "
                f"asset for {chain or 'this chain'}."
            ),
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture=f"{_asset_up} is Solana-only — switch chain",
            buttons=["Use Solana", "Pick a different asset", "Cancel"],
            rationale=(
                "Solana-native SPL mint requested on a non-Solana chain. "
                "Refuse build to prevent same-symbol token confusion."
            ),
        ).to_dict()
        return ok_envelope(
            data={"plan": plan_dict},
            card_type="execution_plan_v3",
            card_payload=plan_dict,
        )

    amount = _coerce_amount(amount_in)
    # Phase 4 lifecycle: claim / withdraw with amount=0 is the canonical
    # "max" sentinel (adapter converts to uint256.max for withdraw, ignores
    # amount entirely for claim). Skip the positivity gate for those actions.
    _lifecycle_zero_ok = (action or "").lower() in {"claim", "withdraw"} or (
        (extra or {}).get("action", "").lower() in {"claim", "withdraw"}
    )
    if amount <= 0 and not _lifecycle_zero_ok:
        return err_envelope("invalid_amount", "amount_in must be a positive decimal value.")

    # RC3 — refuse to build when the user did NOT confirm the amount. The
    # earlier behaviour silently substituted a $1000 placeholder when the
    # detector couldn't pull a numeric amount out of the prose; that path
    # was a financial-loss bug (user typed "stake some ETH on Lido" and
    # got a 1000-ETH supply card). The detector now sets
    # `extra.amount_confirmed=True` only when it extracted an explicit
    # number from the user message (or when the caller passes through a
    # known-good value). Without that flag, refuse the build and surface
    # AMOUNT_NOT_CONFIRMED so the runtime re-prompts the user.
    _extra = extra or {}
    _amount_confirmed = bool(_extra.get("amount_confirmed"))
    _placeholder_flag = bool(_extra.get("amount_is_placeholder"))
    # Lifecycle "withdraw all" / "claim" emit amount=0; those are exempt
    # because the sentinel is the confirmation.
    if not _amount_confirmed and not _lifecycle_zero_ok and not _placeholder_flag:
        # If the amount looks like a textbook placeholder (exactly 1000 or
        # 100 with no decimal component) AND there's no confirmation flag,
        # block the build. We don't want to refuse arbitrary integer
        # amounts the user actually typed, so the gate fires only on the
        # explicit placeholder values the legacy default-amount path used.
        _looks_placeholder = amount == Decimal("1000")
        if _looks_placeholder:
            plan = ExecutionPlanV3.new(
                title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
                summary=(
                    f"Amount not confirmed — refusing to build a "
                    f"{humanize_protocol(protocol)} {humanize_action(action)} "
                    f"plan with a placeholder value."
                ),
            )
            plan.add_blocker(ExecutionBlocker(
                code="AMOUNT_NOT_CONFIRMED",
                severity="blocker",
                title="Amount not confirmed",
                detail=(
                    f"Caller passed amount_in={amount_in!r} but did NOT set "
                    f"extra.amount_confirmed=True. The value matches the "
                    f"legacy placeholder default ($1000 / $100), so refusing "
                    f"to emit a signable plan. Re-prompt the user for the "
                    f"exact amount."
                ),
                affected_step_ids=[],
                cta=(
                    f"Ask the user how much {asset_in} they want to "
                    f"{humanize_action(action).lower()}."
                ),
            ))
            plan_dict = plan.to_dict()
            plan_dict["recovery"] = Recovery(
                action=RecoveryAction.ASK_USER,
                posture="Need an exact amount — no placeholder defaults",
                buttons=["Use 0.1", "Use 1", "Use 10", "Custom amount", "Cancel"],
                rationale=(
                    "Caller passed a placeholder amount. Refusing to risk "
                    "the user signing a 1000-token plan they didn't intend."
                ),
            ).to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )

    # Fix-wave-3 FIX 2 — cross-chain composed_plan FORCE. Pass C E01-E14 +
    # H04/H06/H09 leaked pool_link link_only cards for cross-chain SUPPLY/
    # STAKE/LP_MINT intents because the dispatcher only entered the explicit
    # composed-plan branch when `extra.source_chain` was set. If the caller's
    # extras carry an EXPLICIT cross-chain indicator AND the post-action is
    # a yield verb, refuse to fall through to pool_link.
    #
    # Definition of "explicit indicator":
    #   * extra.cross_chain == True, OR
    #   * extra.is_cross_chain == True, OR
    #   * extra.bridge_via set (e.g. "debridge", "lifi"), OR
    #   * extra.source_chain set AND != chain.
    # cross_chain_message alone is NOT enough — the upper branch at line
    # ~184 already calls `infer_cross_chain_hint` and emits the source-
    # ambiguous blocker when the prose actually expresses cross-chain
    # motion. Re-firing here on bare-string presence would false-trigger
    # on plain single-chain prompts (test_single_chain_message_unaffected
    # pin).
    _extra_xchain = extra or {}
    _xchain_indicators = (
        bool(_extra_xchain.get("cross_chain"))
        or bool(_extra_xchain.get("is_cross_chain"))
        or bool(_extra_xchain.get("bridge_via"))
    )
    _src_indicator = (_extra_xchain.get("source_chain") or "").lower()
    if _src_indicator and _src_indicator != (chain or "").lower():
        _xchain_indicators = True
    _xchain_post_actions = {
        "supply", "deposit", "stake", "lp_mint", "deposit_lp",
        "add_liquidity", "provide_liquidity", "lend",
    }
    if _xchain_indicators and (action or "").lower() in _xchain_post_actions:
        # We're past the explicit composed-plan branch (line ~236-513) which
        # would have caught this when src_chain_hint != chain. Reaching here
        # means either (a) src_chain_hint == chain (degenerate, drop the
        # cross_chain flag), (b) source_chain missing → ambiguous, or
        # (c) caller bridged "via deBridge" without a from_chain. Refuse
        # pool_link emission with an explicit blocker.
        _src = (_extra_xchain.get("source_chain") or "").lower()
        _msg = _extra_xchain.get("cross_chain_message") or ""
        if _src and _src != (chain or "").lower():
            # Source IS present but the composed-plan branch wasn't entered —
            # this is a routing bug. Refuse pool_link and tell the caller.
            plan = ExecutionPlanV3.new(
                title="Cross-chain composed plan required",
                summary=(
                    f"Cross-chain {action} from {_src} to {chain} via "
                    f"{protocol} — refusing pool_link fall-through; the "
                    f"composed-plan branch must be re-entered."
                ),
            )
            plan.add_blocker(ExecutionBlocker(
                code="COMPOSED_PLAN_INCOMPLETE_TX",
                severity="blocker",
                title="Cross-chain intent dropped to pool_link",
                detail=(
                    f"Routing detected cross-chain intent (source={_src}, "
                    f"dest={chain}) with post-action `{action}`, but the "
                    f"explicit composed-plan branch was not entered. "
                    f"Refusing to emit a pool_link link_only card — "
                    f"signing would lose the bridge leg silently. "
                    f"Re-prompt with explicit `from {_src.title()}` so the "
                    f"composed-plan branch fires the deBridge DLN quote."
                ),
                affected_step_ids=[],
                cta=f"Retry with explicit source chain (e.g. 'from {_src.title()}').",
            ))
            plan_dict = plan.to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )
        # Source missing but a cross-chain indicator IS present — emit the
        # canonical source-ambiguous blocker (matches the E04-E14 fix
        # contract).
        from src.agent.cross_chain import (
            cross_chain_source_blocker_payload,
            infer_cross_chain_hint,
        )
        _hint = infer_cross_chain_hint(_msg) if _msg else None
        _dst_for_blocker = (_hint.dest_chain if _hint else None) or chain
        plan = ExecutionPlanV3.new(
            title="Cross-chain plan — source chain missing",
            summary=(
                "Cross-chain intent detected but the source chain wasn't "
                "specified. Re-prompt with 'from <chain>'."
            ),
        )
        _bp = cross_chain_source_blocker_payload(
            dest_chain=_dst_for_blocker, message=_msg or "",
        )
        plan.add_blocker(ExecutionBlocker(
            code=_bp["code"], severity=_bp["severity"], title=_bp["title"],
            detail=_bp["detail"], affected_step_ids=[], cta=_bp["cta"],
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture="Ask user for the source chain.",
            buttons=["Specify source chain", "Cancel"],
            rationale=(
                "Cross-chain motion needs both endpoints. Refusing pool_link "
                "fall-through so the bridge leg is not silently dropped."
            ),
        ).to_dict()
        return ok_envelope(
            data={"plan": plan_dict},
            card_type="execution_plan_v3",
            card_payload=plan_dict,
        )

    # Pool-link gate: consult the canonical `get_exec_capability` helper so
    # the search-card badge and this gate cannot drift. When the helper
    # reports `mode == "link_only"` (V3 EVM LPs, generic V2 EVM LPs, non-Aave
    # EVM supply, non-LST stake), emit a pool_link card pointing at the exact
    # pool on the protocol app. Solana flows pass through (sidecar adapters
    # handle pair-aware prep + sim themselves).
    _cap = get_exec_capability(protocol, chain, action)
    if _cap["mode"] == "link_only":
        extra_dict = extra or {}
        url = pool_protocol_url(
            chain=chain,
            project=protocol,
            pool_address=extra_dict.get("pool_address") or extra_dict.get("poolAddress"),
            underlying_tokens=extra_dict.get("underlying_tokens") or extra_dict.get("underlyingTokens"),
            pool_symbol=extra_dict.get("pool_symbol") or extra_dict.get("poolSymbol"),
            project_url=extra_dict.get("project_url"),
        )
        kind_hint = classify_pool_kind(
            protocol=protocol,
            pool_symbol=extra_dict.get("pool_symbol") or asset_in,
            pool_id=extra_dict.get("pool_id"),
        )

        # V3 / CLMM pools get the interactive range card with live APR math.
        # Other pool types (V2, stable, vault) keep the bare pool_link redirect.
        if kind_hint == "v3":
            pool_symbol = extra_dict.get("pool_symbol") or asset_in or ""
            # Parse pair from pool_symbol when available, else default to USDC/<asset>.
            sym_parts = [s for s in pool_symbol.replace("/", "-").split("-") if s]
            t0 = sym_parts[0].upper() if len(sym_parts) >= 1 else (asset_in or "USDC").upper()
            t1 = sym_parts[1].upper() if len(sym_parts) >= 2 else "WETH"
            decimals_map = {"USDC": 6, "USDT": 6, "DAI": 18, "WETH": 18, "ETH": 18,
                             "WSOL": 9, "SOL": 9, "WBTC": 8, "BTC": 8, "BNB": 18}
            apy_pct = float(extra_dict.get("apy") or 0.0)
            current_price_hint = float(extra_dict.get("current_price") or 1.0)
            v3_card = {
                "card_type": "pool_deposit_v3",
                "card_id": f"v3-{protocol}-{(extra_dict.get('pool_id') or pool_symbol)[:24]}",
                "chain": chain,
                "protocol": protocol,
                "pool_address": extra_dict.get("pool_address") or extra_dict.get("poolAddress") or "",
                "pair": {
                    "token0": {"symbol": t0, "decimals": decimals_map.get(t0, 18), "address": None},
                    "token1": {"symbol": t1, "decimals": decimals_map.get(t1, 18), "address": None},
                },
                "current": {
                    "price_human": f"1 {t0} ≈ {current_price_hint:.4f} {t1}",
                    "current_price": current_price_hint,
                    "sqrt_price_x96": extra_dict.get("sqrt_price_x96"),
                    "tick": extra_dict.get("current_tick"),
                    "tvl_usd": extra_dict.get("tvl_usd"),
                    "vol_24h_usd": extra_dict.get("vol_24h_usd"),
                    "fee_tier_bps": extra_dict.get("fee_tier_bps"),
                    "tick_spacing": extra_dict.get("tick_spacing"),
                },
                "market": {
                    "base_apr_pct": apy_pct,
                    "reward_apr_pct": float(extra_dict.get("reward_apr") or 0.0),
                    "cdf_30d": extra_dict.get("cdf_30d") or [],
                },
                "input_token": {
                    "symbol": (asset_in or "USDC").upper(),
                    "decimals": decimals_map.get((asset_in or "USDC").upper(), 18),
                    "address": None,
                },
                "input_amount_human": str(amount),
                "input_amount_usd": float(amount),
                "initial_range": {"preset": "balanced", "lower_pct": -10.0, "upper_pct": 10.0},
                "initial_steps": [],
                "rebuild_endpoint": "/api/v1/pool/rebuild",
                "protocol_url": url,
                "finalize_externally": True,
                "notice": (
                    f"{protocol.title()} V3 concentrated liquidity — adjust the range to see "
                    "live APR / capital efficiency / in-range probability. Range NFT mint "
                    "currently finalizes on the protocol app (in-chat mint lands in Phase 4)."
                ),
            }
            return ok_envelope(data=v3_card, card_type="pool_deposit_v3", card_payload=v3_card)

        card = {
            "card_type": "pool_link",
            "title": f"{protocol.title()} · {action.replace('_', ' ').title()}",
            "protocol": protocol,
            "chain": chain,
            "pool_kind": kind_hint,
            "pool_symbol": extra_dict.get("pool_symbol") or asset_in,
            "pool_id": extra_dict.get("pool_id"),
            "pool_address": extra_dict.get("pool_address") or extra_dict.get("poolAddress"),
            "apy_pct": extra_dict.get("apy"),
            "tvl_usd": extra_dict.get("tvl_usd"),
            "underlying_tokens": extra_dict.get("underlying_tokens") or extra_dict.get("underlyingTokens"),
            "sentinel": extra_dict.get("sentinel") or {},
            "url": url,
            "amount": str(amount),
            "asset_in": asset_in,
            "amount_is_usd": bool(extra_dict.get("amount_is_usd")),
            "research_thesis": research_thesis,
            "exec_status": "link_only",
            "notice": (
                f"{protocol.title()} {kind_hint.upper()} pool — finalize on the "
                "protocol app. Direct execution from chat is currently disabled "
                "for this pool type because single-token Enso routing was silently "
                "depositing the wrong asset for many pools."
            ),
        }
        return ok_envelope(data=card, card_type="pool_link", card_payload=card)

    # RC6 — verb-aware dispatch table. Reject (protocol, verb) pairs the
    # protocol doesn't support BEFORE the generic adapter registry, so the
    # build never silently downgrades verbs (e.g. user requested `borrow`
    # on a stake-only protocol like Lido → fell through to a supply step).
    # Source of truth for what each protocol actually supports. Add new
    # protocols here when adapters add new verbs; pin tests catch drift.
    _VERB_DISPATCH: dict[str, frozenset[str]] = {
        # EVM lending — full lend/borrow/repay/withdraw/claim cycle.
        "aave-v3":     frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim", "claim_compound"}),
        "aave":        frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim", "claim_compound"}),
        "compound-v3": frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim", "claim_compound"}),
        "compound":    frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim", "claim_compound"}),
        "morpho-blue": frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim"}),
        "morpho":      frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim"}),
        "spark":       frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim"}),
        "sparklend":   frozenset({"supply", "deposit", "lend", "withdraw",
                                   "borrow", "repay", "claim"}),
        # EVM LSTs — stake only. NO borrow/repay/lend.
        "lido":            frozenset({"stake", "unstake", "withdraw"}),
        "rocket-pool":     frozenset({"stake", "unstake", "withdraw"}),
        "ether.fi":        frozenset({"stake", "unstake", "withdraw"}),
        "etherfi":         frozenset({"stake", "unstake", "withdraw"}),
        "renzo":           frozenset({"stake", "unstake", "withdraw"}),
        "swell":           frozenset({"stake", "unstake", "withdraw"}),
        "frax-ether":      frozenset({"stake", "unstake", "withdraw"}),
        "kelp":            frozenset({"stake", "unstake", "withdraw"}),
        "mantle-staked-ether": frozenset({"stake", "unstake", "withdraw"}),
        # Solana LSTs — stake only.
        "marinade":               frozenset({"stake", "unstake", "withdraw"}),
        "marinade-liquid-staking": frozenset({"stake", "unstake", "withdraw"}),
        "marinade-native":        frozenset({"stake", "unstake", "withdraw"}),
        "jito":                   frozenset({"stake", "unstake", "withdraw"}),
        "jito-liquid-staking":    frozenset({"stake", "unstake", "withdraw"}),
        "sanctum":                frozenset({"stake", "unstake", "withdraw"}),
        "sanctum-infinity":       frozenset({"stake", "unstake", "withdraw"}),
        "sanctum-liquid-staking": frozenset({"stake", "unstake", "withdraw"}),
        # Yield vaults — deposit / withdraw, no lend/borrow.
        "yearn-finance":   frozenset({"deposit", "supply", "withdraw", "claim"}),
        "yearn":           frozenset({"deposit", "supply", "withdraw", "claim"}),
        "sky-savings-rate": frozenset({"deposit", "supply", "withdraw", "claim"}),
        "sky":             frozenset({"deposit", "supply", "withdraw", "claim"}),
    }
    proto_lc_rc6 = (protocol or "").lower()
    action_lc_rc6 = (action or "").lower()
    if proto_lc_rc6 in _VERB_DISPATCH:
        if action_lc_rc6 and action_lc_rc6 not in _VERB_DISPATCH[proto_lc_rc6]:
            _supported_verbs = sorted(_VERB_DISPATCH[proto_lc_rc6])
            plan = ExecutionPlanV3.new(
                title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
                summary=(
                    f"{humanize_protocol(protocol)} does not support the "
                    f"`{action}` verb. Refusing to silently downgrade."
                ),
            )
            plan.add_blocker(ExecutionBlocker(
                code="VERB_NOT_SUPPORTED",
                severity="blocker",
                title=f"{humanize_protocol(protocol)} can't {humanize_action(action).lower()}",
                detail=(
                    f"`{action}` is not in the supported verb set for "
                    f"{humanize_protocol(protocol)}. Supported: "
                    f"{', '.join(_supported_verbs)}. Earlier builds would "
                    f"silently fall through to a `supply` step here — that "
                    f"path is now disabled to prevent verb-downgrade bugs."
                ),
                affected_step_ids=[],
                cta=(
                    f"Use one of: {', '.join(_supported_verbs)} — or pick a "
                    f"protocol that supports `{action}` (e.g. Aave V3 / "
                    f"Compound V3 for borrow/repay)."
                ),
            ))
            plan_dict = plan.to_dict()
            plan_dict["recovery"] = Recovery(
                action=RecoveryAction.ASK_USER,
                posture=(
                    f"{humanize_protocol(protocol)} doesn't support "
                    f"`{action}` — pick a different verb or protocol"
                ),
                buttons=(
                    [f"Try {humanize_action(v)}" for v in _supported_verbs[:3]]
                    + ["Switch to Aave V3", "Cancel"]
                ),
                rationale=(
                    "Verb-aware dispatch refused to silently downgrade an "
                    "unsupported action to supply. No financial-loss path."
                ),
            ).to_dict()
            return ok_envelope(
                data={"plan": plan_dict},
                card_type="execution_plan_v3",
                card_payload=plan_dict,
            )

    registry = build_default_registry()
    capability = registry.find(chain=chain, protocol=protocol, action=action)
    if not capability.supported:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"Direct execution for {humanize_protocol(protocol)} {humanize_action(action)} on {chain[:1].upper()+chain[1:]} is not yet supported.",
        )
        plan.add_blocker(ExecutionBlocker(
            code="UNSUPPORTED_ADAPTER",
            severity="blocker",
            title="No verified adapter",
            detail=capability.reason or "No adapter is registered for that protocol/action/chain combination.",
            affected_step_ids=[],
            cta="Pick an adapter-supported protocol such as Aave V3 supply on Ethereum/Polygon/Arbitrum/Base.",
        ))
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = Recovery(
            action=RecoveryAction.ASK_USER,
            posture="No verified adapter — pick a different route",
            buttons=["Try Aave V3", "Try Compound V3", "Cancel"],
            rationale=(
                f"{protocol} {action} on {chain} is not in any adapter's coverage. "
                "Pick an adapter-supported route or change one of (protocol, action, chain)."
            ),
        ).to_dict()
        return ok_envelope(
            data={"plan": plan_dict},
            card_type="execution_plan_v3",
            card_payload=plan_dict,
        )

    adapter = registry.adapter_for(chain=chain, protocol=protocol, action=action)
    assert adapter is not None  # registry.find succeeded above

    try:
        steps = await adapter.build(YieldBuildRequest(
            chain=chain,
            protocol=protocol,
            asset_in=asset_in,
            amount_in=amount,
            user_address=user_address,
            asset_out=asset_out,
            slippage_bps=slippage_bps,
            extra=extra,
        ))
    except ValueError as exc:
        plan = ExecutionPlanV3.new(
            title=f"{humanize_protocol(protocol)} {humanize_action(action)}",
            summary=f"Could not build execution plan for {humanize_protocol(protocol)} {humanize_action(action)} on {chain[:1].upper()+chain[1:]}.",
        )
        # Spec §6f: classify the failure and attach a typed recovery
        # posture so the frontend can surface explicit recovery buttons
        # instead of a generic "try again" CTA.
        from src.defi.recovery import FailureKind, decide_recovery
        _msg = str(exc).lower()
        if "slippage" in _msg:
            _fk = FailureKind.SLIPPAGE_BREACH
        elif "cap" in _msg or "supply cap" in _msg or "frozen" in _msg or "paused" in _msg:
            _fk = FailureKind.DEPOSIT_CAP_REACHED
        elif "blockhash" in _msg:
            _fk = FailureKind.BLOCKHASH_EXPIRED
        elif "gas" in _msg or "insufficient gas" in _msg:
            _fk = FailureKind.GAS_INSUFFICIENT
        elif "revert" in _msg or "transaction reverted" in _msg:
            _fk = FailureKind.EXEC_REVERT
        elif "simulation" in _msg and "failed" in _msg:
            _fk = FailureKind.SIMULATION_FAIL
        elif "user reject" in _msg or "user cancelled" in _msg:
            _fk = FailureKind.USER_CANCELLED
        else:
            # Default to POOL_REMOVED so the recovery dispatcher surfaces
            # ranked alternatives (RC14) for adapter-build failures that
            # don't map to one of the typed kinds above. Adapter-build
            # failure with a candidate universe → "this pool didn't work,
            # here are 3 you already saw that might".
            _fk = FailureKind.POOL_REMOVED
        # RC14: pull alt pools from the cached search universe so
        # recovery.alternatives is populated instead of the empty list
        # that forced G04 t3 to issue a brand-new search. The lookup is
        # a closure over the session_id + chain + asset + protocol so
        # decide_recovery can call it without knowing about the cache.
        _failed_pool_id = (extra or {}).get("pool_id")
        _session_id = getattr(ctx, "session_id", None) if ctx is not None else None

        def _alts_lookup(_pid: str) -> list[dict]:  # pragma: no cover - thin wrapper
            if not _session_id:
                return []
            return pick_alt_pools(
                str(_session_id),
                failed_pool_id=_pid or _failed_pool_id,
                failed_protocol=protocol,
                chain=chain,
                asset=asset_in,
                limit=3,
            )

        _recovery = decide_recovery(
            _fk,
            step_kind=action,
            elapsed_since_fail_s=0,
            current_slippage_bps=50,
            user_slippage_cap_bps=500,
            alternatives_lookup=_alts_lookup,
            pool_id=str(_failed_pool_id or f"{protocol}:{chain}:{asset_in}"),
        )
        # If the typed failure kind didn't trigger the alternatives branch
        # inside decide_recovery (only POOL_PAUSED/REMOVED/DEPOSIT_CAP do),
        # still surface the alt pools we have — the user's recovery card
        # should never be empty when the cache has real candidates.
        if not _recovery.alternatives:
            try:
                _fallback_alts = _alts_lookup(str(_failed_pool_id or ""))
            except Exception:  # noqa: BLE001
                _fallback_alts = []
            if _fallback_alts:
                _recovery.alternatives = _fallback_alts[:3]
        plan.add_blocker(ExecutionBlocker(
            code="ADAPTER_BUILD_FAILED",
            severity="blocker",
            title="Adapter could not build steps",
            detail=str(exc),
            affected_step_ids=[],
            cta=_recovery.posture or "Adjust the asset, chain, or amount and try again.",
        ))
        # Stash typed recovery on the plan dict so the frontend can render
        # explicit recovery buttons. Spec §6f hard rule preserved: only
        # AUTO_REBUILD is auto; everything else requires user click.
        plan_dict = plan.to_dict()
        plan_dict["recovery"] = _recovery.to_dict()
        return ok_envelope(
            data={"plan": plan_dict},
            card_type="execution_plan_v3",
            card_payload=plan_dict,
        )

    proto_human = humanize_protocol(protocol)
    action_human = humanize_action(action)
    chain_human = (chain[:1].upper() + chain[1:]) if chain else chain
    plan = ExecutionPlanV3.new(
        title=f"{proto_human} {action_human}",
        summary=f"{action_human} {amount} {asset_in} via {proto_human} on {chain_human}.",
        research_thesis=research_thesis,
    )
    # RC7b — native ETH (or MATIC/BNB/AVAX) → V3-style LP/supply must wrap first.
    # Spec §13 row 3 mandates wrap(ETH)→LP(WETH), never a swap-router round-trip.
    # Pass A H03 captured a 4-step plan where step 1 was a free-money swap of
    # ETH→USDC (wrong leg) and step 2 was a *swap* of ETH→WETH via Enso
    # (paying router fees on a 1:1 wrap). We refuse both routes: if the
    # adapter didn't itself include a deposit() wrap, we prepend one here.
    try:
        from src.defi.execution.composed_plan import (
            build_wrap_step,
            is_native_wrap_required,
        )

        # Sniff whether the adapter already emitted a wrap step (evm_lst
        # auto-wrap path does this when the LST mint accepts ERC20 only).
        # We only prepend when no step is already wrapping the native.
        _already_wrapping = False
        for _st in steps:
            _tx = getattr(_st, "transaction", None)
            if _tx is not None and (getattr(_tx, "data", None) or "").lower().startswith(
                "0xd0e30db0"
            ):
                _already_wrapping = True
                break

        # V4 LP guard — V4 PoolManager settles native ETH via flash accounting
        # (msg.value, currency = address(0)). Prepending a WETH9.deposit() wrap
        # both burns gas and breaks PoolKey matching. Skip the wrap entirely.
        try:
            from src.defi.execution.adapters.uniswap_v4 import (
                is_v4_native_lp_no_wrap as _v4_no_wrap,
            )
            _skip_wrap_for_v4 = _v4_no_wrap(protocol=protocol, asset_in=asset_in)
        except Exception:
            _skip_wrap_for_v4 = False

        if not _already_wrapping and not _skip_wrap_for_v4 and is_native_wrap_required(
            chain=chain, asset_in=asset_in, action=action,
        ):
            from decimal import Decimal as _Dec

            _native_sym = (asset_in or "").upper()
            try:
                _amt_dec = _Dec(str(amount))
            except Exception:  # noqa: BLE001
                _amt_dec = _Dec("0")
            if _amt_dec > 0:
                _amt_wei = int((_amt_dec * (_Dec(10) ** 18)).to_integral_value())
                _wrap = build_wrap_step(
                    chain=chain,
                    native_symbol=_native_sym,
                    amount_wei=_amt_wei,
                    index=0,
                )
                # Insert the wrap step at the head, re-index everything else.
                # Existing steps may already have depends_on chains; the wrap
                # is a pure prepend so we leave their depends_on alone but
                # bump indices.
                _new_steps: list = [_wrap]
                for _i, _st in enumerate(steps, start=1):
                    _st.index = _i
                    _new_steps.append(_st)
                steps = _new_steps
                # Rewrite subsequent steps that referenced native asset_in to
                # use the wrapped symbol — they're now consuming the wrap
                # step's output. Wrap meta gives the canonical wrapped sym.
                from src.defi.execution.composed_plan import (
                    get_wrapped_native_for_chain,
                )

                _wm = get_wrapped_native_for_chain(chain)
                if _wm:
                    _wrapped_sym = _wm[0]
                    for _st in steps[1:]:
                        if (
                            (_st.asset_in or "").upper() == _native_sym
                            and _st.action in {"approve", "deposit_lp", "supply",
                                               "add_liquidity", "provide_liquidity"}
                        ):
                            _st.asset_in = _wrapped_sym
    except Exception:
        # Wrap-prepend is best-effort; fail-soft so adapters that already
        # handle wrap internally don't double-emit. Real failures surface
        # via the downstream signability invariant or preflight blockers.
        pass

    for step in steps:
        plan.add_step(step)

    if inventory:
        wallet_inventory = _inventory_from_dict(inventory)
        blockers = evaluate_preflight(steps=plan.steps, inventory=wallet_inventory)
        for blocker in blockers:
            plan.add_blocker(blocker)

    # Fix-wave-3 — §13 scenario blocker scan on the regular adapter build
    # path. Covers H10 (LST_ALREADY_DEPOSITED), H11 (NFT_LP_REFINANCE_
    # INCOMPLETE), H12 (CLAIM_COMPOUND_INCOMPLETE), H14 (V2_TO_V3_MIGRATE_
    # INCOMPLETE), H15 (WALLET_CHAIN_MISMATCH via extra.wallet_chain_kind)
    # and E15 (PRICE_IMPACT_TOO_HIGH ≥500 bps). Each detector is fail-soft;
    # an absent extras flag means the detector skips silently. The dust
    # detector (H07) is intentionally NOT triggered here — the regular
    # single-chain path's amounts come straight from user prose and are
    # routinely sub-$1 for testing; only the composed-plan branch surfaces
    # DUST_BELOW_THRESHOLD.
    try:
        from src.defi.execution.scenarios import scan_scenario_blockers
        _scenario_inv_obj = None
        if inventory:
            try:
                _scenario_inv_obj = _inventory_from_dict(inventory)
            except Exception:  # noqa: BLE001
                _scenario_inv_obj = None
        _scenario_blockers = scan_scenario_blockers(
            steps=plan.steps,
            inventory=_scenario_inv_obj,
            extra=extra,
            protocol=protocol,
            action=action,
            asset_in=asset_in,
            chain=chain,
            user_address=user_address,
            # Single-chain path: dst == chain.
            dst_chain=None,
            enable_dust=False,
        )
        for _b in _scenario_blockers:
            plan.add_blocker(_b)
    except Exception:  # noqa: BLE001
        # Scenario scan is best-effort; fail-soft so adapter builds that
        # already produce valid plans aren't blocked by detector bugs.
        pass

    session_id = getattr(ctx, "session_id", None)
    if session_id:
        remember_strategy(StrategyRecord(
            session_id=str(session_id),
            chat_id=str(session_id),
            user_address=user_address,
            intent_summary=f"{action} {amount} {asset_in} via {protocol} on {chain}",
            plan=plan.to_dict(),
            constraints={
                "chain": chain,
                "protocol": protocol,
                "action": action,
                "asset_in": asset_in,
                "amount_in": str(amount),
                "asset_out": asset_out,
                "slippage_bps": slippage_bps,
            },
        ))

    # User-level wallet hold floor. When the plan's only signable step is a
    # half-zap prep_swap and the LP-add itself is link-only (Raydium / Orca /
    # Meteora handoff), totals.assets_required reflects only the swap leg —
    # so a user typing "$10 USDC" sees "USDC: 5" which is wrong. Surface the
    # FULL deposit amount as the wallet floor.
    try:
        floor_sym = (asset_in or "").strip().upper()
        if floor_sym and "+" not in floor_sym and not floor_sym.startswith("0X"):
            existing = plan.totals.assets_required.get(floor_sym)
            try:
                existing_v = float(existing) if existing else 0.0
            except (TypeError, ValueError):
                existing_v = 0.0
            req_v = float(amount) if amount else 0.0
            if req_v > existing_v:
                merged = dict(plan.totals.assets_required)
                text = f"{req_v:.8f}".rstrip("0").rstrip(".") or "0"
                merged[floor_sym] = text
                plan.totals.assets_required = merged
    except Exception:
        pass

    plan_dict = plan.to_dict()

    # CLMM-like protos: V3 EVM + Solana concentrated/dynamic. Attach a
    # range_block payload so the frontend can render the interactive range
    # slider above the step list (spec §6b).
    _V3_EVM_PROTOS = {
        "uniswap-v3", "uniswap-v4", "pancakeswap-v3", "pancake-v3",
        "aerodrome-slipstream", "aerodrome-cl",
    }
    _SOLANA_CLMM_LIKE_PROTOS = {
        "raydium-clmm", "raydium-amm-v3",
        "orca", "orca-whirlpools", "orca-clmm", "orca-dex",
        "meteora-dlmm", "meteora",
    }
    # Try Solana CLMM/DLMM first; emit range_block via sidecar pool_state probe.
    if chain.lower() in {"solana", "sol"} and protocol.lower() in _SOLANA_CLMM_LIKE_PROTOS:
        try:
            import os
            import aiohttp as _aiohttp
            sidecar_url = os.environ.get("SOLANA_YIELD_BUILDER_URL", "http://solana-yield-builder:8090")
            pair_sym = (extra or {}).get("pool_symbol") or asset_in or ""
            sides_sol = [p.strip().upper()
                         for p in pair_sym.replace("/", "-").split("-") if p.strip()]
            if len(sides_sol) >= 2:
                async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=8)) as _sess:
                    async with _sess.post(
                        f"{sidecar_url}/pool_state",
                        json={"protocol": protocol, "pair": "-".join(sides_sol[:2])},
                    ) as _resp:
                        if _resp.status == 200:
                            sp = (await _resp.json()).get("pool") or {}
                            cur_price = float(sp.get("currentPrice") or 0.0)
                            kind = sp.get("kind") or "clmm"
                            tok_a = sp.get("tokenA") or {}
                            tok_b = sp.get("tokenB") or {}
                            # Compute the §6e empirical APR curve once and
                            # surface under both legacy + spec-mandated keys.
                            _sol_apr_curve = await empirical_cdf_or_fallback(sides_sol[0], sides_sol[1])
                            # §6e four-factor composition: augment each bucket
                            # with `composed_apr = P_in*CE*fee_yield - IL_drag`.
                            # Falls back to P_in-only when fee_apr missing.
                            _sol_apr_curve = _augment_curve_with_four_factor_apr(
                                _sol_apr_curve,
                                float(sp.get("baseAprPct") or 0.0),
                            )
                            plan_dict["range_block"] = {
                                "card_subtype": "v3_range",
                                "chain": chain,
                                "protocol": protocol,
                                "pool_address": sp.get("poolAddress"),
                                "pair": {
                                    "token0": {
                                        "symbol": tok_a.get("symbol") or sides_sol[0],
                                        "address": tok_a.get("mint") or "",
                                        "decimals": int(tok_a.get("decimals") or 9),
                                    },
                                    "token1": {
                                        "symbol": tok_b.get("symbol") or sides_sol[1],
                                        "address": tok_b.get("mint") or "",
                                        "decimals": int(tok_b.get("decimals") or 6),
                                    },
                                },
                                "current": {
                                    "current_price": cur_price,
                                    "price_human": (
                                        f"1 {tok_a.get('symbol') or sides_sol[0]} ≈ "
                                        f"{cur_price:.6f} {tok_b.get('symbol') or sides_sol[1]}"
                                    ),
                                    "tick": sp.get("tick"),
                                    "tick_spacing": sp.get("tickSpacing"),
                                    "bin_step": sp.get("binStep"),
                                    "fee_tier_bps": sp.get("feeBps"),
                                    "sqrt_price_x96": str(sp.get("sqrtPriceX64") or ""),
                                    "liquidity": str(sp.get("tvlUsd") or 0),
                                },
                                "market": {
                                    "base_apr_pct": float(sp.get("baseAprPct") or 0.0),
                                    "reward_apr_pct": float(sp.get("rewardAprPct") or 0.0),
                                    # Spec §3.3 → §6e: real-data APR curve. The
                                    # empirical_cdf_or_fallback series IS the §6e
                                    # APR-by-range curve (module docstring is
                                    # explicit). Surface under both legacy
                                    # `cdf_30d` and the spec-mandated
                                    # `apr_curve_30d` field for downstream
                                    # consumers that key on the spec name.
                                    "cdf_30d": _sol_apr_curve,
                                    "apr_curve_30d": _sol_apr_curve,
                                    "kind": kind,
                                },
                                "initial_range": {
                                    "preset": "balanced",
                                    "lower_pct": -10.0,
                                    "upper_pct": 10.0,
                                },
                                "range_presets": [
                                    {"label": "Narrow", "lower_pct": -5.0, "upper_pct": 5.0},
                                    {"label": "Balanced", "lower_pct": -10.0, "upper_pct": 10.0},
                                    {"label": "Wide", "lower_pct": -25.0, "upper_pct": 25.0},
                                    {"label": "Full", "lower_pct": -50.0, "upper_pct": 100.0},
                                ],
                            }
        except Exception:
            pass
    if protocol.lower() in _V3_EVM_PROTOS:
        try:
            from src.data.v3_pool_resolver import resolve_v3_pool
            from src.data.asset_registry import resolve_any_evm_token
            from src.data.v3_tick_math import price_from_tick

            extra_dict = dict(extra or {})
            # If apy_base / apy_total wasn't pre-populated (direct-LP intent
            # skips the meta-fetch), look it up from DefiLlama yields for the
            # exact protocol + chain + symbol match so range_block.market
            # shows real APR instead of a stale 0.
            if not extra_dict.get("apy_base") and not extra_dict.get("apy_total"):
                try:
                    import aiohttp as _aiohttp
                    _ll_url = "https://yields.llama.fi/pools"
                    _pair_symbol_raw = (extra_dict.get("pool_symbol") or asset_in or "").upper().replace("/", "-")
                    _pair_target = _pair_symbol_raw
                    _pair_target_alt = "-".join(reversed(_pair_target.split("-")))
                    # DefiLlama chain canonicalization. "Optimism" → "op mainnet";
                    # "BSC" → "bsc"; "Polygon" → "polygon pos" sometimes; etc.
                    _DEFILLAMA_CHAIN_ALIASES = {
                        "optimism": ("op mainnet", "optimism"),
                        "polygon": ("polygon", "polygon pos", "matic"),
                        "bsc": ("bsc", "bnb smart chain", "binance"),
                        "avalanche": ("avalanche", "avax"),
                        "arbitrum": ("arbitrum", "arbitrum one"),
                        "ethereum": ("ethereum",),
                        "base": ("base",),
                        "linea": ("linea",),
                        "mantle": ("mantle",),
                        "zksync": ("zksync era", "zksync"),
                        "scroll": ("scroll",),
                    }
                    _chain_canonical = _DEFILLAMA_CHAIN_ALIASES.get(chain.lower(), (chain.lower(),))
                    async with _aiohttp.ClientSession(timeout=_aiohttp.ClientTimeout(total=6)) as _llsess:
                        async with _llsess.get(_ll_url) as _llresp:
                            if _llresp.status == 200:
                                _lldata = await _llresp.json()
                                _proto_l = protocol.lower()
                                best = None
                                best_tvl = 0.0
                                for _e in (_lldata.get("data") or []):
                                    if str(_e.get("project") or "").lower() != _proto_l:
                                        continue
                                    _ec = str(_e.get("chain") or "").lower()
                                    if not any(cv == _ec for cv in _chain_canonical):
                                        continue
                                    _sym = str(_e.get("symbol") or "").upper().replace("/", "-")
                                    if _pair_target not in _sym and _pair_target_alt not in _sym:
                                        continue
                                    _t = float(_e.get("tvlUsd") or 0)
                                    if _t > best_tvl:
                                        best = _e
                                        best_tvl = _t
                                if best is not None:
                                    extra_dict["apy_total"] = float(best.get("apy") or 0.0)
                                    extra_dict["apy_base"] = float(best.get("apyBase") or 0.0)
                                    extra_dict["apy_reward"] = float(best.get("apyReward") or 0.0)
                                    extra_dict["tvl_usd"] = float(best.get("tvlUsd") or 0.0)
                except Exception:
                    pass

            pair_sym = extra_dict.get("pool_symbol") or asset_in or ""
            fee_bps = int(extra_dict.get("fee_bps") or 500)
            sides = [p.strip().upper()
                     for p in pair_sym.replace("/", "-").split("-") if p.strip()]
            if len(sides) >= 2:
                meta_a = await resolve_any_evm_token(chain, sides[0])
                meta_b = await resolve_any_evm_token(chain, sides[1])
                # V3 pools always trade wrapped natives, never the 0xEee...
                # placeholder. Resolve the right wrapper per chain so the
                # range_block matches what the V3 NFT adapter actually mints
                # (WETH on EVM L1/L2, WBNB on BSC, WAVAX on Avalanche, WMATIC
                # on Polygon).
                from src.data.asset_registry import NATIVE_PLACEHOLDER
                _WRAP_BY_CHAIN = {
                    "ethereum": "WETH", "base": "WETH", "arbitrum": "WETH",
                    "optimism": "WETH", "linea": "WETH", "scroll": "WETH",
                    "zksync": "WETH", "bsc": "WBNB", "avalanche": "WAVAX",
                    "polygon": "WMATIC",
                }
                _wrap_sym = _WRAP_BY_CHAIN.get(chain.lower(), "WETH")
                _wrap_meta = await resolve_any_evm_token(chain, _wrap_sym)
                if meta_a and meta_a[0] == NATIVE_PLACEHOLDER and _wrap_meta:
                    meta_a = _wrap_meta
                    sides[0] = _wrap_sym
                if meta_b and meta_b[0] == NATIVE_PLACEHOLDER and _wrap_meta:
                    meta_b = _wrap_meta
                    sides[1] = _wrap_sym
                if meta_a and meta_b:
                    pool_state = await resolve_v3_pool(
                        chain=chain, protocol=protocol,
                        token_a=meta_a[0], token_b=meta_b[0], fee_bps=fee_bps,
                    )
                    if pool_state is None:
                        # Match the V3 NFT adapter's fee-tier auto-discovery:
                        # the user-given tier might not exist; pick the deepest
                        # tier that does, so the slider always renders.
                        from src.data.v3_pool_resolver import list_fee_tiers_with_pools
                        try:
                            tiers = await list_fee_tiers_with_pools(
                                chain=chain, protocol=protocol,
                                token_a=meta_a[0], token_b=meta_b[0],
                            )
                        except Exception:
                            tiers = []
                        if tiers:
                            best_state = max(tiers, key=lambda t: int(getattr(t, "liquidity", 0) or 0))
                            pool_state = best_state
                            fee_bps = best_state.fee_bps
                    if pool_state is not None:
                        # price_from_tick expects POOL token0/token1 decimals
                        # AND returns token1-per-token0. The user's sides[0] /
                        # sides[1] may be in the opposite order from the pool's
                        # on-chain token0/token1 (addresses sort the pool, the
                        # user types whichever side first). Resolve both
                        # decimals + direction by comparing addresses.
                        pool_t0_addr = (pool_state.token0 or "").lower()
                        user_a_addr = (meta_a[0] or "").lower()
                        user_b_addr = (meta_b[0] or "").lower()
                        if pool_t0_addr == user_a_addr:
                            dec0, dec1 = meta_a[1], meta_b[1]
                            invert = False
                        elif pool_t0_addr == user_b_addr:
                            dec0, dec1 = meta_b[1], meta_a[1]
                            invert = True
                        else:
                            # Unknown ordering — fall back to user order and
                            # accept that the display might be flipped (rare).
                            dec0, dec1 = meta_a[1], meta_b[1]
                            invert = False
                        raw = price_from_tick(pool_state.tick, dec0, dec1)
                        if invert:
                            from decimal import Decimal as _D
                            raw = _D(1) / raw if raw != 0 else raw
                        human_price = float(raw)
                        # Spec §3.3 → §6e: compute the empirical APR curve once
                        # and surface under both legacy + spec-mandated keys.
                        _evm_apr_curve = await empirical_cdf_or_fallback(sides[0], sides[1])
                        # §6e four-factor composition: augment each bucket with
                        # `composed_apr = P_in*CE*fee_yield - IL_drag`. Falls
                        # back to P_in-only when fee_apr missing.
                        _evm_apr_curve = _augment_curve_with_four_factor_apr(
                            _evm_apr_curve,
                            float(extra_dict.get("apy_base") or extra_dict.get("apy_total") or 0.0),
                        )
                        plan_dict["range_block"] = {
                            "card_subtype": "v3_range",
                            "chain": chain,
                            "protocol": protocol,
                            "pool_address": pool_state.pool_address,
                            "pair": {
                                "token0": {"symbol": sides[0],
                                           "address": pool_state.token0,
                                           "decimals": meta_a[1]},
                                "token1": {"symbol": sides[1],
                                           "address": pool_state.token1,
                                           "decimals": meta_b[1]},
                            },
                            "current": {
                                "current_price": human_price,
                                "price_human": f"1 {sides[0]} ≈ {human_price:.6f} {sides[1]}",
                                "tick": pool_state.tick,
                                "tick_spacing": pool_state.tick_spacing,
                                "fee_tier_bps": pool_state.fee_bps,
                                "sqrt_price_x96": str(pool_state.sqrt_price_x96),
                                "liquidity": str(pool_state.liquidity),
                            },
                            "market": {
                                "base_apr_pct": float(extra_dict.get("apy_base") or extra_dict.get("apy_total") or 0.0),
                                "reward_apr_pct": float(extra_dict.get("apy_reward") or 0.0),
                                "tvl_usd": float(extra_dict.get("tvl_usd") or 0.0),
                                "cdf_30d": _evm_apr_curve,
                                "apr_curve_30d": _evm_apr_curve,
                                "kind": "v3" if "v3" in protocol.lower() else (
                                    "v4" if "v4" in protocol.lower() else (
                                        "slipstream" if "slipstream" in protocol.lower() else "v3"
                                    )
                                ),
                            },
                            "initial_range": {
                                "preset": "balanced",
                                "lower_pct": -10.0,
                                "upper_pct": 10.0,
                            },
                            # Frontend slider bounds: lower in [-50, 0], upper in [0, 100].
                            # Anything wider would clip silently and confuse the user.
                            "range_presets": [
                                {"label": "Narrow", "lower_pct": -5.0, "upper_pct": 5.0},
                                {"label": "Balanced", "lower_pct": -10.0, "upper_pct": 10.0},
                                {"label": "Wide", "lower_pct": -25.0, "upper_pct": 25.0},
                                {"label": "Full", "lower_pct": -50.0, "upper_pct": 100.0},
                            ],
                        }
        except Exception:
            pass

    # §6d exposure_disclosure: when the user explicitly named a source token
    # via "with my <SRC>" that is not one of the pool's legs, surface the
    # silent reassignment in the plan card so the user understands their
    # capital is being zapped through a swap and becomes exposed to a leg
    # they didn't explicitly hold. Spec: "You said USDT. I'll split into
    # 50.3% USDC + 49.7% SOL (the ratio for your selected range). After
    # this trade, your position is exposed to SOL price movement, not just
    # USDC peg."
    try:
        _src = (extra or {}).get("source_token")
        if _src:
            _src_u = str(_src).upper()
            # Pool legs come from extra.pool_symbol when available; fall
            # back to asset_in for single-asset deposits.
            _pair_sym = str((extra or {}).get("pool_symbol") or asset_in or "")
            _legs = [p.strip().upper() for p in _pair_sym.replace("/", "-").split("-") if p.strip()]
            if _src_u and _src_u not in _legs:
                _other_legs = [l for l in _legs if l]
                _legs_human = " + ".join(_other_legs) if _other_legs else "the pool legs"
                plan_dict["exposure_disclosure"] = {
                    "source_token": _src_u,
                    "pool_legs": _other_legs,
                    "headline": (
                        f"You said {_src_u}. I'll split it into {_legs_human} "
                        f"via aggregator zap-in for this pool."
                    ),
                    "detail": (
                        f"After this trade your position is exposed to "
                        f"{_legs_human} price movement, not just the "
                        f"{_src_u} peg. Slippage budget includes the swap "
                        f"leg; review the Preview before signing."
                    ),
                    "severity": "info",
                }
    except Exception:
        pass

    # F03/F08 wallet preflight — fail-soft balance + native gas check.
    # The plan thought-stream advertises "Running wallet preflight (balance /
    # gas / allowance) before exposing any signing button" but earlier passes
    # never actually ran a balance lookup. Empty wallet + 100k USDC supply
    # would silently emit a `ready` plan. Wire the real check here so
    # frontends gate the signing CTA on visible blockers.
    try:
        from IlyonAi_Wallet_assistant_main.server.app.agents.crypto_agent import (
            get_smart_wallet_balance,
        )
        import asyncio as _asyncio
        import json as _json
        _raw_bal = await _asyncio.to_thread(
            get_smart_wallet_balance,
            str(user_address or ""),
            str(user_address or ""),
            str(user_address or ""),
        )
        try:
            _bal_doc = _json.loads(_raw_bal) if isinstance(_raw_bal, str) else (_raw_bal or {})
        except Exception:
            _bal_doc = {}
        # Build symbol → human balance map across all chains the scanner
        # returned. Caller's chain context drives the gas check, but token
        # presence is checked symbolically (Aave V3 USDC on Ethereum vs.
        # Polygon is still USDC for shortfall purposes).
        _wallet_balances: dict[str, float] = {}
        _native_gas_by_chain: dict[str, float] = {}
        _CHAIN_NAME_TO_KEY = {
            "Ethereum": "ethereum", "BNB Chain": "bsc", "BSC": "bsc",
            "Polygon": "polygon", "Arbitrum": "arbitrum", "Optimism": "optimism",
            "Base": "base", "Avalanche": "avalanche", "Solana": "solana",
            "Linea": "linea", "Mantle": "mantle", "Scroll": "scroll",
            "zkSync": "zksync",
            # V7-069 — Sonic chain name → key.
            "Sonic": "sonic",
        }
        for _entry in (_bal_doc.get("balances") or []):
            _chain_name = str(_entry.get("chain") or "")
            _chain_key = _CHAIN_NAME_TO_KEY.get(_chain_name, _chain_name.lower())
            _native_sym = str(_entry.get("native_symbol") or "").upper()
            try:
                _native_amt = float(_entry.get("native_balance") or 0)
            except (TypeError, ValueError):
                _native_amt = 0.0
            if _native_sym:
                _wallet_balances[_native_sym] = max(
                    _wallet_balances.get(_native_sym, 0.0), _native_amt
                )
                _native_gas_by_chain[_chain_key] = max(
                    _native_gas_by_chain.get(_chain_key, 0.0), _native_amt
                )
            for _tok in (_entry.get("tokens") or []):
                _sym = str(_tok.get("symbol") or "").upper()
                try:
                    _amt = float(_tok.get("balance") or 0)
                except (TypeError, ValueError):
                    _amt = 0.0
                if _sym:
                    _wallet_balances[_sym] = max(_wallet_balances.get(_sym, 0.0), _amt)

        # 1) Per-asset shortfall — emit one INSUFFICIENT_BALANCE blocker per
        #    short symbol so the recovery card can route bridge/swap source.
        _shortfall_emitted: set[str] = set()
        for _sym, _required_text in (plan.totals.assets_required or {}).items():
            _sym_up = str(_sym).upper()
            if not _sym_up or _sym_up.startswith("0X") or "+" in _sym_up:
                continue
            try:
                _required = float(_required_text)
            except (TypeError, ValueError):
                _required = 0.0
            if _required <= 0:
                continue
            _have = float(_wallet_balances.get(_sym_up, 0.0))
            if _have < _required and _sym_up not in _shortfall_emitted:
                _shortfall_emitted.add(_sym_up)
                plan.add_blocker(ExecutionBlocker(
                    code="INSUFFICIENT_BALANCE",
                    severity="blocker",
                    title=f"Not enough {_sym_up}",
                    detail=(
                        f"Need {_required:g} {_sym_up}, wallet has "
                        f"{_have:g} {_sym_up}."
                    ),
                    affected_step_ids=[],
                    cta=(
                        f"Bridge or swap into {_sym_up} on {chain} before "
                        f"signing this plan."
                    ),
                ))

        # 2) Native gas top-up — sum step.gas_estimate_usd, convert to native
        #    via the live DefiLlama price_oracle (V7-044). No hardcoded USD
        #    fallback: when the oracle has no price for the native symbol the
        #    plan emits a STALE_PRICE_FEED blocker rather than silently pricing
        #    gas at a stale baked-in number.
        _NATIVE_BY_CHAIN = {
            "ethereum": "ETH", "base": "ETH", "arbitrum": "ETH",
            "optimism": "ETH", "linea": "ETH", "scroll": "ETH",
            "zksync": "ETH", "bsc": "BNB", "polygon": "MATIC",
            "avalanche": "AVAX", "solana": "SOL", "mantle": "MNT",
            # V7-069 — Sonic chain native gas symbol. Sonic uses "S" (the
            # rebranded FTM) for L1 gas fees; without this entry the gas
            # preflight silently skips Sonic plans.
            "sonic": "S",
        }
        # DefiLlama oracle keys: (chain_slug, token_address). Native gas
        # priced via the canonical wrapped ERC-20 on each chain (oracle
        # has no "ETH" entry — it expects WETH9).
        _NATIVE_PRICE_LOOKUP: dict[str, tuple[str, str]] = {
            "ETH":   ("ethereum",  "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"),
            "BNB":   ("bsc",       "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"),
            "MATIC": ("polygon",   "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270"),
            "AVAX":  ("avalanche", "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7"),
            "SOL":   ("solana",    "So11111111111111111111111111111111111111112"),
            "MNT":   ("mantle",    "0x78c1b0c915c4faa5fffa6cabf0219da63d7f4cb8"),
            "S":     ("sonic",     "0x039e2fb66102314ce7b64ce5ce3e5183bc94ad38"),
        }
        _chain_key = (chain or "").lower()
        _native_sym = _NATIVE_BY_CHAIN.get(_chain_key)
        _est_gas_usd = 0.0
        for _step in plan.steps:
            try:
                _est_gas_usd += float(getattr(_step, "gas_estimate_usd", 0) or 0)
            except (TypeError, ValueError):
                pass
        if _native_sym and _est_gas_usd > 0:
            from src.data.price_oracle import fetch_price_usd as _fetch_price_usd
            import aiohttp as _aiohttp_oracle
            _native_usd: float | None = None
            _lookup = _NATIVE_PRICE_LOOKUP.get(_native_sym)
            if _lookup is not None:
                _llchain, _lladdr = _lookup
                try:
                    async with _aiohttp_oracle.ClientSession(
                        timeout=_aiohttp_oracle.ClientTimeout(total=5)
                    ) as _osess:
                        _native_usd = await _fetch_price_usd(_llchain, _lladdr, _osess)
                except Exception:
                    _native_usd = None
            if _native_usd is None or _native_usd <= 0:
                # V7-044 — no hardcoded fallback. Surface STALE_PRICE_FEED so
                # the recovery card can re-quote or warn the user before sign.
                plan.add_blocker(ExecutionBlocker(
                    code="STALE_PRICE_FEED",
                    severity="blocker",
                    title=f"Price feed unavailable for {_native_sym}",
                    detail=(
                        f"Live price oracle returned no USD for {_native_sym} "
                        f"on {chain}; gas-topup math cannot be confirmed. "
                        f"Plan held until the oracle recovers."
                    ),
                    affected_step_ids=[],
                    cta=(
                        f"Wait for the price feed to recover or refresh the "
                        f"plan to re-query the oracle."
                    ),
                ))
            else:
                _native_needed = (_est_gas_usd * 1.5) / _native_usd
                _native_have = float(_native_gas_by_chain.get(_chain_key, 0.0))
                if _native_have <= 0:
                    # Cross-fallback: chain-keyed lookup missed, fall back to
                    # symbol-keyed lookup so single-chain wallets still match.
                    _native_have = float(_wallet_balances.get(_native_sym, 0.0))
                if _native_have < _native_needed:
                    plan.add_blocker(ExecutionBlocker(
                        code="GAS_TOPUP_REQUIRED",
                        severity="blocker",
                        title=f"Not enough {_native_sym} for gas",
                        detail=(
                            f"Need ~{_native_needed:.6f} {_native_sym} "
                            f"(~${_est_gas_usd * 1.5:,.2f} at 1.5× headroom), "
                            f"wallet has {_native_have:.6f} {_native_sym}."
                        ),
                        affected_step_ids=[],
                        cta=(
                            f"Top up {_native_sym} on {chain} before signing "
                            f"(bridge from another chain or fund the wallet)."
                        ),
                    ))
        # Re-serialise after late blockers so the frontend sees them.
        plan_dict = plan.to_dict()
    except Exception:
        # Fail-soft: any failure in the preflight (import error, wallet
        # unreachable, scanner timeout, malformed response) keeps the
        # original `ready` plan path. The spec is explicit — current behaviour
        # is preserved when balance lookup throws or wallet is unset.
        pass

    # V7-007 — Spec §13 row 5 frozen-account preflight (Solana only).
    # For each Solana step that moves an SPL asset out of the user's wallet,
    # check the ATA AccountState via getTokenAccountsByOwner+getAccountInfo.
    # A frozen account causes signing to revert with 0x11 (AccountFrozen)
    # and burn the Phantom prep-swap gas, so we refuse to expose Confirm.
    try:
        if (chain or "").lower() in {"solana", "sol"} and user_address:
            # Symbol → SPL mint registry. Keep this in sync with the larger
            # _TOKEN_ADDRS table above (V7-007 only needs the assets the
            # plan actually moves on Solana, so a small inline registry is
            # fine; the validation harness pins this list).
            _SPL_MINTS: dict[str, str] = {
                "USDC":     "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "USDT":     "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "SOL":      "So11111111111111111111111111111111111111112",
                "WSOL":     "So11111111111111111111111111111111111111112",
                "MSOL":     "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
                "JITOSOL":  "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
                "BSOL":     "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",
                "BNSOL":    "BNso1VUJnh4zcfpZa6986Ea66P6TCp59hvtNJ8b1X85",
                "JUPSOL":   "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v",
                "INF":      "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",
                "JLP":      "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4",
                "JSOL":     "7Q2afV64in6N6SeZsAAB81TJzwDoD6zpqmHkzi9Dcavn",
                "BONK":     "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                "PYTH":     "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
                "JTO":      "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
                "RAY":      "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
                "ORCA":     "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
                "USDS":     "USDSwr9ApdHk5bvJKMjzff41FfuX8bSxdKcR81vTwcA",
                "PYUSD":    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo",
            }
            pairs: list[tuple[str, str]] = []
            tagged_steps: list[str] = []
            for _step in plan.steps:
                if str(_step.chain or "").lower() not in {"solana", "sol"}:
                    continue
                if _step.action not in {"swap", "supply", "stake", "deposit_lp",
                                        "bridge", "withdraw"}:
                    continue
                _sym = (_step.asset_in or "").upper()
                if not _sym:
                    continue
                _mint = _SPL_MINTS.get(_sym)
                # Caller might already have an explicit mint address in
                # asset_in (base58 ≥32 chars). Use it as-is.
                if not _mint and len(_sym) >= 32 and not _sym.startswith("0X"):
                    _mint = _sym
                if not _mint:
                    continue
                pairs.append((_mint, str(user_address)))
                tagged_steps.append(_step.step_id)

            if pairs:
                from src.config import settings as _settings
                from src.shield.preflight_solana import evaluate_solana_frozen_preflight
                _rpc_url = getattr(_settings, "solana_rpc_url", None) or \
                           "https://api.mainnet-beta.solana.com"
                _frozen_blockers = await evaluate_solana_frozen_preflight(
                    pairs=pairs,
                    rpc_url=str(_rpc_url),
                    affected_step_ids=tagged_steps,
                )
                for _blocker in _frozen_blockers:
                    plan.add_blocker(_blocker)
                if _frozen_blockers:
                    plan_dict = plan.to_dict()

                # V7-031 — Spec §13 row 4 Token-2022 transfer-hook gate.
                # For each mint surfaced above, fetch the mint account and
                # check the TLV extension stream. Untrusted hook → emit
                # TOKEN_2022_HOOK_UNTRUSTED blocker. Fail-soft on RPC errors.
                try:
                    from src.shield.spl_transfer_hook import check_transfer_hook
                    _seen_hook_mints: set[str] = set()
                    _hook_blockers: list[Any] = []
                    for _mint, _ in pairs:
                        if _mint in _seen_hook_mints:
                            continue
                        _seen_hook_mints.add(_mint)
                        _ok, _hook_addr = await check_transfer_hook(
                            _mint, rpc_url=str(_rpc_url),
                        )
                        if _ok:
                            continue
                        _short_mint = _mint[:8] + "…" if len(_mint) > 9 else _mint
                        _short_hook = (_hook_addr or "")[:8] + "…" if (_hook_addr or "") else "?"
                        _hook_blockers.append(ExecutionBlocker(
                            code="TOKEN_2022_HOOK_UNTRUSTED",
                            severity="blocker",
                            title=f"Token-2022 transfer-hook not allow-listed for mint {_short_mint}",
                            detail=(
                                f"Mint {_mint} declares a Token-2022 TransferHook "
                                f"extension whose program id ({_hook_addr}) is not on "
                                f"the trusted allowlist. Every transfer of this asset "
                                f"would CPI into {_short_hook}, which can refuse, "
                                f"redirect, or tax the transfer. Spec §13 row 4 "
                                f"refuses to surface a Confirm button until the hook "
                                f"is reviewed and explicitly allow-listed."
                            ),
                            affected_step_ids=list(tagged_steps),
                            recoverable=False,
                            cta=(
                                "Pick a different asset, or have the integrator add "
                                f"{_hook_addr} to TRUSTED_TRANSFER_HOOKS after a "
                                "security review."
                            ),
                        ))
                    for _blocker in _hook_blockers:
                        plan.add_blocker(_blocker)
                    if _hook_blockers:
                        plan_dict = plan.to_dict()
                except Exception:
                    # Fail-soft per module docstring.
                    pass
    except Exception:
        # Fail-soft: never let the frozen preflight crash the planner.
        pass

    return ok_envelope(
        data={"plan": plan_dict, "adapter_id": capability.adapter_id},
        card_type="execution_plan_v3",
        card_payload=plan_dict,
    )


def _inventory_from_dict(raw: dict[str, Any]) -> WalletInventory:
    balances = {}
    for entry in raw.get("balances") or []:
        try:
            chain = str(entry["chain"]).lower()
            asset = str(entry["asset"]).upper()
            amount = Decimal(str(entry.get("amount", 0)))
            balances[(chain, asset)] = amount
        except (KeyError, InvalidOperation, TypeError):
            continue
    native_gas = {}
    for entry in raw.get("native_gas") or []:
        try:
            chain = str(entry["chain"]).lower()
            amount = Decimal(str(entry.get("amount", 0)))
            native_gas[chain] = amount
        except (KeyError, InvalidOperation, TypeError):
            continue
    allowances = {}
    for entry in raw.get("allowances") or []:
        try:
            chain = str(entry["chain"]).lower()
            asset = str(entry["asset"]).upper()
            spender = str(entry["spender"]).lower()
            amount = Decimal(str(entry.get("amount", 0)))
            allowances[(chain, asset, spender)] = amount
        except (KeyError, InvalidOperation, TypeError):
            continue
    return WalletInventory(
        evm_address=raw.get("evm_address"),
        solana_address=raw.get("solana_address"),
        chain_id=raw.get("chain_id"),
        balances=balances,
        native_gas=native_gas,
        allowances=allowances,
    )
