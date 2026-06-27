"""On-chain open-position detection (read-only, non-custodial).

Classifies a wallet's token holdings into open DeFi positions (liquid staking,
LP, lending, vault) purely from the balance data we already fetch via Helius
(Solana) and Moralis (EVM). No new provider calls, no DB, no execution-path
change — it only LABELS which holdings are positions vs plain spot tokens.

v1 scope: liquid-staking tokens (LSTs), known vault receipts (JLP / sDAI), and a
conservative set of EVM LST / LP / lending (aToken/cToken) receipts. Out of
scope (needs extra RPC, tracked as follow-ups): native Solana stake accounts,
CLMM position NFTs, exact LP underlying split, IL / fee-APR. This surfaces the
bulk of real positions a wallet actually holds.

Registries mirror values already in the repo so detection stays consistent with
how the agent builds these positions:
- Solana receipt mints — src/agent/tools/build_yield_execution_plan.py:_SPL_MINTS
- EVM LST addresses    — src/agent/tools/wallet_swap.py:_LST_ADDRESS_TO_LABEL
                         + src/data/asset_registry.py LST rows
"""
from __future__ import annotations

from typing import Any, Optional

# Solana receipt mints → (protocol, kind, underlying)
_SOLANA_RECEIPTS: dict[str, tuple[str, str, str]] = {
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": ("Marinade", "staking", "SOL"),
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": ("Jito", "staking", "SOL"),
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1": ("BlazeStake", "staking", "SOL"),
    "BNso1VUJnh4zcfpZa6986Ea66P6TCp59hvtNJ8b1X85": ("Binance", "staking", "SOL"),
    "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdosWBjx93v": ("Jupiter", "staking", "SOL"),
    "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm": ("Sanctum", "staking", "SOL"),   # INF
    "7Q2afV64in6N6SeZsAAB81TJzwDoD6zpqmHkzi9Dcavn": ("JPool", "staking", "SOL"),      # JSOL
    "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4": ("Jupiter Perps", "vault", "JLP"),  # JLP
}

_SOLANA_SPOT_SOL = {"SOL", "WSOL"}

# EVM receipt addresses (lowercased) → (protocol, kind, underlying)
_EVM_RECEIPTS: dict[str, tuple[str, str, str]] = {
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": ("Lido", "staking", "ETH"),         # stETH
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": ("Lido", "staking", "ETH"),         # wstETH
    "0xae78736cd615f374d3085123a210448e74fc6393": ("Rocket Pool", "staking", "ETH"),  # rETH
    "0xbe9895146f7af43049ca1c1ae358b0541ea49704": ("Coinbase", "staking", "ETH"),     # cbETH
    "0xcd5fe23c85820f7b72d0926fc9b05b43e359b7ee": ("EtherFi", "staking", "ETH"),      # weETH
    "0xbf5495efe5db9ce00f80364c8b423567e58d2110": ("Renzo", "staking", "ETH"),        # ezETH
    "0xac3e018457b222d93114458476f3e3416abbe38f": ("Frax", "staking", "ETH"),         # sfrxETH
    "0xb0b84d294e0c75a6abe60171b70edeb2efd14a1b": ("Lista DAO", "staking", "BNB"),    # slisBNB
    "0xfa68fb4628dff1028cfec22b4162fccd0d45efb6": ("Stader", "staking", "MATIC"),     # MATICX
    "0x2b2c81e08f1af8835a78bb2a90ae924ace0ea4be": ("Benqi", "staking", "AVAX"),       # sAVAX
    "0x83f20f44975d03b1b09e64809b757c47f942beea": ("MakerDAO", "vault", "DAI"),       # sDAI
}

_EVM_LST_SYMBOLS = {
    "STETH", "WSTETH", "RETH", "CBETH", "WEETH", "EZETH", "SFRXETH",
    "SLISBNB", "MATICX", "SAVAX", "RSETH", "OSETH", "ANKRETH",
}

_PROTO_BY_SYMBOL = {
    "MSOL": "Marinade", "JITOSOL": "Jito", "BSOL": "BlazeStake", "BNSOL": "Binance",
    "JUPSOL": "Jupiter", "INF": "Sanctum", "JSOL": "JPool", "STSOL": "Lido",
    "STETH": "Lido", "WSTETH": "Lido", "RETH": "Rocket Pool", "CBETH": "Coinbase",
    "WEETH": "EtherFi", "EZETH": "Renzo", "SFRXETH": "Frax", "SLISBNB": "Lista DAO",
    "MATICX": "Stader", "SAVAX": "Benqi",
}


def _proto_from_symbol(sym: str) -> str:
    return _PROTO_BY_SYMBOL.get(sym, "Liquid staking")


def classify_token(address: str, symbol: str, chain: str) -> Optional[dict[str, Any]]:
    """Return a position descriptor {kind, protocol, underlying} for a holding,
    or None if it is a plain spot token. Known mint/address lookups are
    authoritative; symbol heuristics are a conservative fallback to avoid
    mislabeling spot tokens."""
    addr = (address or "").strip()
    sym = (symbol or "").strip().upper()
    ch = (chain or "").strip().lower()
    is_solana = ch in ("", "solana", "sol") and not addr.startswith("0x")

    if is_solana:
        hit = _SOLANA_RECEIPTS.get(addr)
        if hit:
            return {"kind": hit[1], "protocol": hit[0], "underlying": hit[2]}
        # *SOL liquid-staking tokens (stSOL, hSOL, …) but not SOL / WSOL
        if sym.endswith("SOL") and sym not in _SOLANA_SPOT_SOL and 3 < len(sym) <= 8:
            return {"kind": "staking", "protocol": _proto_from_symbol(sym), "underlying": "SOL"}
        return None

    # EVM
    hit = _EVM_RECEIPTS.get(addr.lower())
    if hit:
        return {"kind": hit[1], "protocol": hit[0], "underlying": hit[2]}
    if sym in _EVM_LST_SYMBOLS:
        return {"kind": "staking", "protocol": _proto_from_symbol(sym), "underlying": "ETH"}
    # Aave v3 aTokens are chain-prefixed: aEthUSDC, aBasUSDC, aArbWETH, aPolUSDC, aOptUSDC, aAvaUSDC
    if any(sym.startswith(p) for p in ("AETH", "ABAS", "AARB", "APOL", "AOPT", "AAVA")):
        return {"kind": "lending", "protocol": "Aave V3", "underlying": (sym[4:] or None)}
    # Compound v3 cTokens: cUSDCv3, cWETHv3
    if sym.startswith("C") and sym.endswith("V3") and len(sym) > 4:
        return {"kind": "lending", "protocol": "Compound V3", "underlying": (sym[1:-2] or None)}
    # DEX LP tokens
    if "UNI-V2" in sym or sym.endswith("-LP") or sym in ("SLP", "CAKE-LP") or "/" in sym:
        return {"kind": "lp", "protocol": "DEX LP", "underlying": None}
    return None


def derive_positions(tokens: list[dict], chain: Optional[str] = None) -> list[dict]:
    """Classify a list of balance dicts (from portfolio.get_wallet_tokens) into
    open positions. Each balance dict has mint/symbol/amount/value_usd/price_usd
    (+ optional 'chain' for EVM). Returns position rows sorted by value; skips
    plain spot tokens."""
    positions: list[dict] = []
    for t in tokens or []:
        addr = str(t.get("mint") or t.get("address") or "")
        sym = str(t.get("symbol") or "")
        ch = str(t.get("chain") or chain or "")
        cls = classify_token(addr, sym, ch)
        if not cls:
            continue
        amount = t.get("amount")
        value_usd = t.get("value_usd")
        if (value_usd or 0) <= 0 and (amount or 0) <= 0:
            continue  # dust / zero balance — not an open position
        positions.append({
            "kind": cls["kind"],
            "protocol": cls["protocol"],
            "underlying": cls.get("underlying"),
            "symbol": sym or None,
            "address": addr or None,
            "chain": (ch or "solana").lower(),
            "amount": amount,
            "value_usd": value_usd,
            "price_usd": t.get("price_usd"),
            "source": "onchain",
        })
    positions.sort(key=lambda p: (p.get("value_usd") or 0), reverse=True)
    return positions
