"""Verify the READY address-resolved plans are actually SIGNABLE: freshness +
calldata-hash bind (what the wallet hook enforces) + on-chain eth_call."""
import json
import hashlib
import time
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
RPC = {1: "https://eth.drpc.org", 56: "https://bsc.drpc.org"}

CASES = [
    ("add 25 usdc to 0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7", "Curve 3pool eth"),
    ("execute pool 0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16 with 15 busd", "PancakeSwap BUSD/WBNB bsc"),
    ("i want to add 20 usdc to this pool 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc on ethereum", "Uni V2 USDC/WETH eth"),
    ("put 10 usdc into 0x397FF1542f962076d0BFE58eA045FfA2d347ACa0", "SushiSwap USDC/WETH eth"),
]


def fe_hash(tx):
    p = {k: str(tx[k]) for k in ("data", "to", "value") if tx.get(k) is not None}
    return hashlib.sha256(json.dumps(p, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def eth_call(cid, tx):
    rpc = RPC.get(cid)
    if not rpc:
        return "no-rpc"
    val = tx.get("value") or "0x0"
    if not str(val).startswith("0x"):
        val = "0x0"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [
        {"from": EVM, "to": tx.get("to"), "data": tx.get("data"), "value": val}, "latest"]}).encode()
    try:
        req = urllib.request.Request(rpc, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read())
        return "exec-ok" if "result" in d else "revert:" + ((d.get("error") or {}).get("message") or "")[:50]
    except Exception as e:
        return "rpc-err:" + str(e)[:35]


def ask(msg, i):
    body = json.dumps({"message": msg, "session_id": "asv-%d" % i,
                       "wallet": {"kind": "evm", "address": EVM}, "evm_wallet": EVM}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    step = None
    with urllib.request.urlopen(req, timeout=120) as resp:
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
            if e.get("card_type") == "execution_plan_v3":
                for s in (e["payload"].get("steps") or []):
                    if s.get("status") == "ready" and (s.get("transaction") or {}).get("to"):
                        step = s
                        break
    return step


def main():
    print("=" * 90)
    for i, (msg, what) in enumerate(CASES):
        step = ask(msg, i)
        if not step:
            print("\n%s -> no ready step" % what)
            continue
        tx = step["transaction"]
        sa = tx.get("simulated_at")
        sh = tx.get("simulated_calldata_hash")
        fresh = isinstance(sa, (int, float)) and sa > 0 and (time.time() - sa) < 180
        hash_ok = bool(sh) and sh == fe_hash(tx)
        oc = eth_call(tx.get("chain_id"), tx)
        signable = fresh and hash_ok and tx.get("to") and tx.get("data")
        print("\n%s" % what)
        print("   fresh=%s hash_bound=%s chain_id=%s  => SIGNABLE=%s | on-chain=%s" % (
            fresh, hash_ok, tx.get("chain_id"), signable, oc))


if __name__ == "__main__":
    main()
