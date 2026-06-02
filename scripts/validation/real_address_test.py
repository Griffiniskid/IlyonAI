"""Test REAL on-chain pool contract addresses (what users actually paste from
DexScreener/Etherscan), not DefiLlama UUIDs. Varied phrasing."""
import json
import urllib.request

ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"

# (question, wallet_kind, real_pool, what_it_is)
CASES = [
    ("deposit 10 usdc into pool 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640", "evm",
     "Uniswap V3 USDC/WETH 0.05% (ethereum)"),
    ("add 25 usdc to 0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7", "evm",
     "Curve 3pool (ethereum)"),
    ("execute pool 0x58F876857a02D6762E0101bb5C46A8c1ED44Dc16 with 15 busd", "evm",
     "PancakeSwap V2 BUSD/WBNB (bsc)"),
    ("i want to add 20 usdc to this pool 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc on ethereum", "evm",
     "Uniswap V2 USDC/WETH (ethereum)"),
    ("put 10 usdc into 0x397FF1542f962076d0BFE58eA045FfA2d347ACa0", "evm",
     "SushiSwap USDC/WETH (ethereum)"),
    ("deposit 1 sol into pool 58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2", "sol",
     "Raydium SOL/USDC AMM (solana)"),
]


_SEQ = [0]


def ask(message, kind):
    waddr = SOL if kind == "sol" else EVM
    _SEQ[0] += 1
    body = json.dumps({"message": message, "session_id": "addr-%d-%d" % (_SEQ[0], hash(message) % 99999),
                       "wallet": {"kind": kind, "address": waddr},
                       "evm_wallet": EVM, "solana_wallet": SOL}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    status = proto = chain = None
    blk = []
    final = ""
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
                    e = json.loads(p)
                except json.JSONDecodeError:
                    continue
                if e.get("card_type") == "execution_plan_v3":
                    pl = e["payload"]
                    status = pl.get("status")
                    blk = [b.get("code") for b in (pl.get("blockers") or [])]
                    for s in (pl.get("steps") or []):
                        proto = s.get("protocol")
                        chain = s.get("chain")
                        break
                    if not proto:
                        proto = pl.get("title")
                if e.get("content"):
                    final += e["content"]
    except Exception as ex:  # noqa: BLE001
        final = "ERROR " + str(ex)[:80]
    return status, proto, chain, blk, final


def main():
    print("=" * 96)
    print("REAL ON-CHAIN POOL ADDRESS TEST")
    print("=" * 96)
    resolved = 0
    for q, kind, what in CASES:
        status, proto, chain, blk, final = ask(q, kind)
        ok = status == "ready"
        if ok:
            resolved += 1
        print("\nQ: %s" % q)
        print("   (%s)" % what)
        print("   status=%s proto=%s chain=%s blockers=%s" % (status, (proto or "")[:34], chain, blk))
        if not status:
            print("   no-card answer: %s" % final[-220:].replace("\n", " "))
    print("\nEXECUTABLE with a real pool address: %d/%d" % (resolved, len(CASES)))


if __name__ == "__main__":
    main()
