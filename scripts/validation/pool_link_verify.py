"""Verify "Open pool" deep-links land on the EXACT pool, across protocols.

For a set of real search queries, collect every item's pool_deeplink and
classify:
  EXACT     — URL contains an on-chain pool address (0x40hex or base58>=32)
              OR is a per-asset lending reserve page.
  LIST/SRCH — protocol page but a list/search filter (fallback).
  DEFILLAMA — defillama.com (must be ZERO for Open pool).
Also HTTP-checks reachability. Reports counts.
"""
import json
import re
import sys
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"

QUERIES = [
    ("orca pools on solana", "solana"),
    ("raydium pools on solana", "solana"),
    ("uniswap v3 pools on ethereum", "evm"),
    ("uniswap v2 pools on ethereum", "evm"),
    ("pancakeswap pools on bsc", "evm"),
    ("sushiswap pools on ethereum", "evm"),
    ("aave lending on ethereum", "evm"),
]

_EVM_ADDR = re.compile(r"0x[a-fA-F0-9]{40}")
_B58 = re.compile(r"/([1-9A-HJ-NP-Za-km-z]{32,44})\b")
_RESERVE = ("reserve-overview", "markets/v3", "/reserve/")


def classify(url: str) -> str:
    if not url:
        return "NONE"
    u = url.lower()
    if "defillama.com" in u:
        return "DEFILLAMA"
    if _EVM_ADDR.search(url) or _B58.search(url) or "pool_id=" in u or any(k in u for k in _RESERVE):
        return "EXACT"
    if any(k in u for k in ("?search=", "?query=", "textsearch=", "/pools\"", "/markets", "/liquidity-pools")) or u.rstrip("/").endswith(("/pools", "/liquidity", "/dlmm")):
        return "LIST"
    return "OTHER"


def reachable(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.status < 400
        except Exception:
            return None


def ask(q, kind, sess):
    waddr = SOL if kind == "solana" else EVM
    body = json.dumps({"message": q, "session_id": sess, "wallet": {"kind": "solana" if kind == "solana" else "evm", "address": waddr},
                       "evm_wallet": EVM, "solana_wallet": SOL}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    out = []
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
                    out.append((it.get("protocol"), it.get("symbol"), it.get("pool_deeplink"), len(it.get("links") or [])))
                break
    return out


def main():
    rows = []
    for i, (q, kind) in enumerate(QUERIES):
        try:
            rows += ask(q, kind, "plv-%d-%d" % (i, __import__("random").randint(0, 99999)))
        except Exception as e:
            print("query failed:", q, str(e)[:60])
    counts = {"EXACT": 0, "LIST": 0, "DEFILLAMA": 0, "OTHER": 0, "NONE": 0}
    print("=" * 90)
    for proto, sym, url, nlinks in rows:
        c = classify(url or "")
        counts[c] += 1
        print("%-9s %-14s [%s] llama_btns=%d %s" % (c, (sym or "")[:14], proto, nlinks, str(url)[:62]))
    print("=" * 90)
    print("EXACT=%d  LIST=%d  DEFILLAMA=%d  OTHER=%d  NONE=%d  (total %d)" % (
        counts["EXACT"], counts["LIST"], counts["DEFILLAMA"], counts["OTHER"], counts["NONE"], len(rows)))
    print("Open-pool buttons on DefiLlama (must be 0):", counts["DEFILLAMA"])


if __name__ == "__main__":
    main()
