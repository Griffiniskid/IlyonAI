"""Strong user-fidelity simulation: run the REAL search endpoint many times
per query (like a user reloading), and measure — per pool — whether "Open
pool" CONSISTENTLY lands on the exact pool, or flips (the timeout flakiness).

Reports per-pool: ALWAYS-EXACT / FLAKY / NEVER-EXACT, plus the distinct URLs
seen across runs (so flakiness is visible). This is the honest measure of
'what actually works', not a single lucky snapshot.
"""
import json
import re
import urllib.request
from collections import defaultdict

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"
RUNS = 5

QUERIES = [
    ("orca pools on solana", "solana"),
    ("raydium pools on solana", "solana"),
    ("uniswap v3 pools on ethereum", "evm"),
    ("uniswap v2 pools on ethereum", "evm"),
    ("pancakeswap pools on bsc", "evm"),
    ("sushiswap pools on ethereum", "evm"),
    ("curve pools on ethereum", "evm"),
    ("aave lending on ethereum", "evm"),
]

_EVM_ADDR = re.compile(r"0x[a-fA-F0-9]{40}")
_B58 = re.compile(r"/([1-9A-HJ-NP-Za-km-z]{32,44})")


def is_exact(url: str) -> bool:
    """DIRECT link to the exact pool: protocol-native (has address/id) OR the
    DefiLlama pool page (always the exact pool). NOT a generic list/search."""
    if not url:
        return False
    u = url.lower()
    # DefiLlama POOL page = exact pool (direct). DefiLlama protocol/yields list = not.
    if "defillama.com/yields/pool/" in u:
        return True
    if "defillama.com" in u:
        return False
    if "?search=" in u or "?query=" in u or "textsearch=" in u:
        return False
    if u.rstrip("/").endswith(("/pools", "/liquidity", "/pool", "/dlmm", "/markets")):
        return False
    if "reserve-overview" in u or "pool_id=" in u:
        return True
    return bool(_EVM_ADDR.search(url) or _B58.search(url))


def ask(q, kind, sess):
    waddr = SOL if kind == "solana" else EVM
    body = json.dumps({"message": q, "session_id": sess,
                       "wallet": {"kind": "solana" if kind == "solana" else "evm", "address": waddr},
                       "evm_wallet": EVM, "solana_wallet": SOL}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    out = {}
    try:
        with urllib.request.urlopen(req, timeout=130) as resp:
            for raw in resp:
                l = raw.decode("utf-8", "replace").strip()
                if not l.startswith("data:"):
                    continue
                p = l[5:].strip()
                if not p or p == "[DONE]":
                    continue
                try:
                    e = json.loads(p)
                except json.JSONDecodeError:
                    continue
                items = (e.get("payload") or {}).get("items") or []
                if items:
                    for it in items[:5]:
                        key = "%s|%s" % (it.get("protocol"), it.get("symbol"))
                        out[key] = it.get("pool_deeplink")
                    break
    except Exception:
        pass
    return out


def main():
    import random
    seen = defaultdict(list)  # key -> [url per run]
    for i, (q, kind) in enumerate(QUERIES):
        for r in range(RUNS):
            res = ask(q, kind, "sps-%d-%d-%d" % (i, r, random.randint(0, 999999)))
            for key, url in res.items():
                seen[key].append(url)
    always = flaky = never = 0
    print("=" * 96)
    for key, urls in sorted(seen.items()):
        exacts = [is_exact(u) for u in urls]
        n_exact = sum(exacts)
        n = len(urls)
        distinct = len(set(urls))
        if n_exact == n:
            verdict = "ALWAYS-EXACT"
            always += 1
        elif n_exact == 0:
            verdict = "NEVER-EXACT"
            never += 1
        else:
            verdict = "FLAKY(%d/%d)" % (n_exact, n)
            flaky += 1
        print("%-14s %-26s runs=%d exact=%d distinct_urls=%d" % (verdict, key[:26], n, n_exact, distinct))
    print("=" * 96)
    tot = always + flaky + never
    print("ALWAYS-EXACT=%d  FLAKY=%d  NEVER-EXACT=%d  (pools=%d)" % (always, flaky, never, tot))
    print("Consistently exact: %.0f%%" % (100.0 * always / tot if tot else 0))


if __name__ == "__main__":
    main()
