"""BSC on-chain proof for the EXECUTE button — Anvil BSC mainnet fork.

`eth_call` sim passing is NOT proof the deposit lands both legs. This forks BSC,
funds the deposit token (storage slot auto-detected), broadcasts the built plan,
and asserts the pool's LP-token balance strictly INCREASES (both legs added) for
PancakeSwap zaps. Aave supply is asserted via the deposit token balance dropping
(single asset, no LP). Requires anvil on PATH (foundry).
"""
import json
import os
import subprocess
import time
import urllib.request

os.environ["PATH"] = os.path.expanduser("~/.foundry/bin") + ":" + os.environ.get("PATH", "")
ENDPOINT = "http://localhost:8080/api/v1/agent"
PORT = 8547
RPC = "http://localhost:%d" % PORT
WHALE = "0xc9f1000000000000000000000000000000009c43"
FORK_URL = "https://bsc-dataseed.binance.org"

USDT = "0x55d398326f99059fF775485246999027B3197955"  # BSC USDT, 18 dec
USDC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"  # BSC USDC, 18 dec

# (label, pool_uuid, deposit_sym, deposit_token, decimals, kind, lp_or_none)
#   kind="lp"     → assert pair LP balance increases (pair addr in lp_or_none)
#   kind="supply" → assert deposit-token balance decreases
CASES = [
    ("PancakeSwap USDT-WBNB", "a3878e88-0c9f-49ef-adbc-da5fe048192d", "usdt", USDT, 18, "lp",
     "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae"),
    ("PancakeSwap ETH-USDC", "7ad86bde-60f1-4647-96ae-2ae15389d814", "usdc", USDC, 18, "lp",
     "0xea26b78255df2bbc31c1ebf60010d78670185bd0"),
    ("Aave USDT supply", "29be6a85-414f-4a66-b075-98863278912a", "usdt", USDT, 18, "supply", None),
]
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"


def cast(*a):
    return subprocess.run(["cast", *a], capture_output=True, text=True, timeout=120)


def rpc(method, *params):
    cast("rpc", method, *params, "--rpc-url", RPC)


def bal(token, who):
    r = cast("call", token, "balanceOf(address)(uint256)", who, "--rpc-url", RPC)
    try:
        return int(r.stdout.strip().split()[0])
    except (ValueError, IndexError):
        return 0


def fund_token(token, who, decimals):
    """Auto-detect the balanceOf storage slot (BEP20 layouts vary) and fund."""
    target = 100_000 * 10**decimals
    val = "0x" + hex(target)[2:].rjust(64, "0")
    for slot in range(0, 6):
        key = cast("index", "address", who, str(slot)).stdout.strip()
        if not key:
            continue
        rpc("anvil_setStorageAt", token, key, val)
        if bal(token, who) >= target:
            return slot
        rpc("anvil_setStorageAt", token, key, "0x" + "0" * 64)  # revert miss
    return None


def get_plan(uuid, sym, amt=30):
    body = json.dumps({
        "message": "Execute deposit into pool %s with %d %s" % (uuid, amt, sym.upper()),
        "session_id": "bscv-" + uuid[:8], "wallet": {"kind": "evm", "address": WHALE},
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
    return status, steps


def run_case(label, uuid, sym, token, decimals, kind, lp):
    slot = fund_token(token, WHALE, decimals)
    if slot is None:
        print("[%s] FAIL: could not fund %s (slot not found)" % (label, sym.upper()))
        return False
    rpc("anvil_setBalance", WHALE, "0x3635c9adc5dea00000")  # 1000 BNB for gas
    status, steps = get_plan(uuid, sym)
    if not steps:
        print("[%s] status=%s steps=0 -> deep-linked (not executable)" % (label, status))
        return None
    for s in steps:
        to = (s.get("transaction") or {}).get("to")
        if to:
            cast("send", "--unlocked", "--from", WHALE, "--rpc-url", RPC, token, "approve(address,uint256)", to, str(2**256 - 1))
    cast("send", "--unlocked", "--from", WHALE, "--rpc-url", RPC, token, "approve(address,uint256)", PERMIT2, str(2**256 - 1))

    lp_before = bal(lp, WHALE) if kind == "lp" else 0
    tok_before = bal(token, WHALE)
    for s in steps:
        tx = s.get("transaction") or {}
        v = tx.get("value") or "0"
        if isinstance(v, str) and v.startswith("0x"):
            v = str(int(v, 16))
        cast("send", "--unlocked", "--from", WHALE, "--rpc-url", RPC, tx.get("to"), "--value", v, tx.get("data"))

    if kind == "lp":
        delta = bal(lp, WHALE) - lp_before
        ok = delta > 0
        print("[%s] steps=%d LP delta=%d -> %s" % (label, len(steps), delta, "PASS (both legs)" if ok else "FAIL (no LP)"))
        return ok
    spent = tok_before - bal(token, WHALE)
    ok = spent > 0
    print("[%s] steps=%d spent=%d -> %s" % (label, len(steps), spent, "PASS (supplied)" if ok else "FAIL (nothing spent)"))
    return ok


def main():
    anvil = subprocess.Popen(
        ["anvil", "--fork-url", FORK_URL, "--port", str(PORT), "--auto-impersonate", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            if cast("chain-id", "--rpc-url", RPC).returncode == 0:
                break
            time.sleep(1)
        results = []
        for c in CASES:
            try:
                results.append(run_case(*c))
            except Exception as e:  # noqa: BLE001
                print("[%s] EXC %s" % (c[0], str(e)[:90]))
                results.append(False)
            time.sleep(4)
        ok = sum(1 for r in results if r is True)
        print("\n==== %d/%d BSC pools proven on-chain ====" % (ok, len(results)))
    finally:
        anvil.terminate()


if __name__ == "__main__":
    main()
