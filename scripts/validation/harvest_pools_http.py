import json
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"

QUERIES = [
    "show uniswap liquidity pools on ethereum",
    "show pancakeswap liquidity pools on bsc",
    "show curve liquidity pools on ethereum",
    "show aave lending pools on arbitrum",
    "show aave lending pools on base",
    "show balancer pools on ethereum",
    "show sushiswap pools on ethereum",
    "show orca liquidity pools on solana",
    "show raydium liquidity pools on solana",
    "show liquidity pools on polygon",
]


def harvest(q, session):
    body = json.dumps({"message": q, "session_id": session, "wallet": {"kind": "evm", "address": EVM},
                       "evm_wallet": EVM, "solana_wallet": SOL}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    found = []
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                p = line[5:].strip()
                if not p or p == "[DONE]":
                    continue
                try:
                    evt = json.loads(p)
                except json.JSONDecodeError:
                    continue
                pl = evt.get("payload") or {}
                items = pl.get("opportunities") or pl.get("items") or []
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    if it.get("pool_id") or it.get("pool"):
                        found.append({
                            "protocol": it.get("protocol"),
                            "chain": it.get("chain"),
                            "symbol": it.get("symbol") or it.get("pool_symbol"),
                            "pool_id": it.get("pool_id") or it.get("pool"),
                            "addresses": it.get("underlying_tokens") or it.get("token_addresses"),
                            "executable": it.get("executable"),
                            "apy": it.get("apy") or it.get("apy_pct"),
                        })
    except Exception as e:  # noqa: BLE001
        return [{"query": q, "ERROR": "{}: {}".format(type(e).__name__, str(e)[:80])}]
    return found


def main():
    allp = []
    for i, q in enumerate(QUERIES):
        res = harvest(q, "harv-%d" % i)
        print("\n## {}  -> {} pools".format(q, len([r for r in res if "ERROR" not in r])))
        for r in res:
            print("  ", json.dumps(r, default=str))
        allp.extend([r for r in res if "ERROR" not in r])
    print("\nTOTAL pools harvested:", len(allp))
    with open("/app/harvested_pools.json", "w") as f:
        json.dump(allp, f, indent=1, default=str)


if __name__ == "__main__":
    main()
