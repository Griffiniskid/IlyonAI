"""V2 zap asset-correctness check on an Anvil mainnet fork.

status==1 is NOT enough for a V2 LP deposit: a broken zap can succeed on-chain
yet deposit the wrong asset / leave the LP unminted. This proves the deposit is
REAL by asserting the user's LP-token (pair) balance strictly INCREASES after
broadcasting the plan — which only happens when addLiquidity added BOTH legs.

Single ethereum uni-v2 pool (USDC/WETH). Requires anvil on PATH (foundry).
"""
import json
import os
import subprocess
import time
import urllib.request

os.environ["PATH"] = os.path.expanduser("~/.foundry/bin") + ":" + os.environ.get("PATH", "")
ENDPOINT = "http://localhost:8080/api/v1/agent"
PORT = 8546
RPC = "http://localhost:%d" % PORT
WHALE = "0x28C6c06298d514Db089934071355E5743bf21d60"
FORK_URL = "https://ethereum-rpc.publicnode.com"

# (label, deposit_sym, token_addr, balanceOf storage slot, decimals, deposit_amt, pair_addr)
# deposit_sym MUST match the funded token_addr (we fund the token we deposit).
CASES = [
    ("USDC/WETH", "usdc", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 9, 6, 100,
     "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"),
    ("DAI/WETH", "dai", "0x6B175474E89094C44Da98b954EedeAC495271d0F", 2, 18, 100,
     "0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11"),
    ("WETH/USDT", "usdt", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 2, 6, 100,
     "0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852"),
]
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"


def cast(*a):
    return subprocess.run(["cast", *a], capture_output=True, text=True, timeout=90)


def rpc(method, *params):
    cast("rpc", method, *params, "--rpc-url", RPC)


def bal(token, who):
    r = cast("call", token, "balanceOf(address)(uint256)", who, "--rpc-url", RPC)
    return int(r.stdout.strip().split()[0]) if r.stdout.strip() else 0


def run_case(label, sym, token, slot, decimals, amt, pair):
    rpc("anvil_setBalance", WHALE, "0x3635c9adc5dea00000")  # 1000 ETH
    key = cast("index", "address", WHALE, str(slot)).stdout.strip()
    val = "0x" + hex(10_000 * 10**decimals)[2:].rjust(64, "0")
    rpc("anvil_setStorageAt", token, key, val)

    body = json.dumps({
        "message": "add %d %s to this pool %s on ethereum" % (amt, sym, pair),
        "session_id": "v2zap-" + label, "wallet": {"kind": "evm", "address": WHALE},
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    steps, status = [], None
    for raw in urllib.request.urlopen(req, timeout=90):
        line = raw.decode().strip()
        if not line.startswith("data:"):
            continue
        try:
            o = json.loads(line[5:].strip())
        except Exception:
            continue
        if o.get("card_type") == "execution_plan_v3":
            status = o["payload"].get("status")
            steps = o["payload"].get("steps") or []
    if not steps:
        print("[%s] status=%s steps=0 -> deep-linked (no broadcast)" % (label, status))
        return None

    lp_before = bal(pair, WHALE)
    for s in steps:
        to = (s.get("transaction") or {}).get("to")
        if to:
            cast("send", "--unlocked", "--from", WHALE, "--rpc-url", RPC, token,
                 "approve(address,uint256)", to, str(2**256 - 1))
    cast("send", "--unlocked", "--from", WHALE, "--rpc-url", RPC, token,
         "approve(address,uint256)", PERMIT2, str(2**256 - 1))
    for s in steps:
        tx = s.get("transaction") or {}
        v = tx.get("value") or "0"
        if isinstance(v, str) and v.startswith("0x"):
            v = str(int(v, 16))
        cast("send", "--unlocked", "--from", WHALE, "--rpc-url", RPC, tx.get("to"), "--value", v, tx.get("data"))
    lp_after = bal(pair, WHALE)
    ok = lp_after > lp_before
    print("[%s] status=%s steps=%d LP delta=%d -> %s" % (
        label, status, len(steps), lp_after - lp_before, "PASS (both legs)" if ok else "FAIL (no LP)"))
    return ok


def main():
    anvil = subprocess.Popen(
        ["anvil", "--fork-url", FORK_URL, "--port", str(PORT), "--auto-impersonate", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(30):
            if cast("chain-id", "--rpc-url", RPC).returncode == 0:
                break
            time.sleep(1)
        results = []
        for c in CASES:
            # Public RPC / Enso bursts intermittently 429 — the build then
            # safely deep-links (verify-on-commit). Space requests + retry so
            # the asset-correctness check isn't defeated by transient flake.
            r = None
            for attempt in range(3):
                try:
                    r = run_case(*c)
                except Exception as e:  # noqa: BLE001
                    print("[%s] EXC %s" % (c[0], str(e)[:80]))
                    r = False
                if r is not None:
                    break
                time.sleep(8)  # deep-linked (transient) → wait + retry
            results.append(r)
            time.sleep(5)
        ok = sum(1 for r in results if r is True)
        print("\n==== %d/%d V2 zaps minted LP (both legs verified) ====" % (ok, len(results)))
    finally:
        anvil.terminate()


if __name__ == "__main__":
    main()
