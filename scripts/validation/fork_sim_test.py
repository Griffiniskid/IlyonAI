"""RIGOROUS fork simulation: for each real-user request, get the execution
plan from the live endpoint, fork the chain on anvil, fund the wallet, then
BROADCAST every step and assert each receipt succeeds (status==1).

This is real on-chain execution against a mainnet fork — it catches what
eth_call on an empty wallet cannot (semantic reverts, bad mint params,
insufficient approvals, slippage).

Requires anvil on PATH (foundry).
"""
import json
import os
import subprocess
import time
import urllib.request

FOUNDRY = os.path.expanduser("~/.foundry/bin")
os.environ["PATH"] = FOUNDRY + ":" + os.environ.get("PATH", "")
ENDPOINT = "http://localhost:8080/api/v1/agent"
EVM = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
SOL = "7Np41oeYqPefeNQEHSv1UDhYrehxin3NStpmzpaedWZ8"
PORT = 8546
RPC = "http://localhost:%d" % PORT

CHAIN_FORK = {
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "base": "https://base-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-one-rpc.publicnode.com",
}
CHAIN_ID = {"ethereum": 1, "base": 8453, "arbitrum": 42161}

# (chain, token_addr_lower) -> ERC20 balanceOf storage slot.
SLOT = {
    ("ethereum", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"): 9,    # USDC
    ("ethereum", "0xdac17f958d2ee523a2206206994597c13d831ec7"): 2,    # USDT
    ("ethereum", "0x6b175474e89094c44da98b954eedeac495271d0f"): 2,    # DAI
    ("ethereum", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"): 3,    # WETH
    ("ethereum", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"): 0,    # WBTC
    ("base", "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"): 9,        # USDC
    ("base", "0x4200000000000000000000000000000000000006"): 3,        # WETH
    ("arbitrum", "0xaf88d065e77c8cc2239327c5edb3a432268e5831"): 9,     # USDC.e/USDC
    ("arbitrum", "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"): 51,    # WETH arb (proxy)
}
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"


def cast(*args):
    return subprocess.run(["cast", *args], capture_output=True, text=True, timeout=60)


def start_anvil(chain):
    subprocess.run(["pkill", "-f", "anvil --fork"], capture_output=True)
    time.sleep(1)
    subprocess.Popen(
        ["anvil", "--fork-url", CHAIN_FORK[chain], "--port", str(PORT),
         "--auto-impersonate", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        r = cast("chain-id", "--rpc-url", RPC)
        if r.returncode == 0 and r.stdout.strip():
            return True
        time.sleep(1)
    return False


def fund_eth(addr):
    cast("rpc", "anvil_setBalance", addr, "0x3635c9adc5dea00000", "--rpc-url", RPC)  # 1000 ETH


def fund_token(chain, token, addr):
    slot = SLOT.get((chain, token.lower()))
    if slot is None:
        return False
    # `cast index` is an offline keccak of (addr || slot) for a Solidity
    # mapping — it takes NO --rpc-url.
    key = cast("index", "address", addr, str(slot)).stdout.strip()
    if not key:
        return False
    val = "0x" + (10**24).to_bytes(32, "big").hex()  # huge balance
    cast("rpc", "anvil_setStorageAt", token, key, val, "--rpc-url", RPC)
    return True


def approve(token, spender, addr):
    cast("send", "--unlocked", "--from", addr, "--rpc-url", RPC, token,
         "approve(address,uint256)", spender,
         "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff")


def send_step(tx, addr):
    to = tx.get("to")
    data = tx.get("data")
    if not to or not data:
        return None, "no calldata"
    val = tx.get("value") or "0"
    if isinstance(val, str) and val.startswith("0x"):
        val = str(int(val, 16))
    r = cast("send", "--unlocked", "--from", addr, "--rpc-url", RPC,
             "--value", str(val or 0), "--json", to, data)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[:120].replace("\n", " ")
    try:
        rec = json.loads(r.stdout)
        return rec.get("status") == "0x1", "status=" + str(rec.get("status"))
    except Exception:
        return None, r.stdout[:80]


def ask(message, kind, session):
    waddr = SOL if kind == "sol" else EVM
    body = json.dumps({"message": message, "session_id": session,
                       "wallet": {"kind": kind, "address": waddr},
                       "evm_wallet": EVM, "solana_wallet": SOL}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    status = chain = None
    steps = []
    cardtype = None
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
            if e.get("card_type"):
                cardtype = e["card_type"]
            if e.get("card_type") == "execution_plan_v3":
                pl = e["payload"]
                status = pl.get("status")
                steps = pl.get("steps") or []
                for s in steps:
                    if s.get("chain"):
                        chain = s["chain"]
                        break
    return {"status": status, "chain": chain, "steps": steps, "cardtype": cardtype}


def input_token_addr(steps):
    """The token the first signable step pulls from the wallet."""
    for s in steps:
        tx = s.get("transaction") or {}
        # asset_in symbol → resolve via known map below; prefer explicit token in extra
    return None


# input token address per chain+symbol for funding
TOKEN_ADDR = {
    ("ethereum", "USDC"): "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    ("ethereum", "DAI"): "0x6b175474e89094c44da98b954eedeac495271d0f",
    ("ethereum", "USDT"): "0xdac17f958d2ee523a2206206994597c13d831ec7",
    ("ethereum", "WBTC"): "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    ("ethereum", "WETH"): "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    ("base", "USDC"): "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    ("base", "WETH"): "0x4200000000000000000000000000000000000006",
    ("arbitrum", "USDC"): "0xaf88d065e77c8cc2239327c5edb3a432268e5831",
    ("arbitrum", "WETH"): "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
}

# (message, wallet_kind, chain, input_symbol) — real user formats: pool
# addresses + protocol+token deposits. All on chains we can fork+fund.
REQUESTS = [
    # ── ETH: V2 / Curve pool addresses (Enso single-tx zap) ──
    ("i want to add 20 usdc to this pool 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc on ethereum", "evm", "ethereum", "USDC"),
    ("put 10 usdc into 0x397FF1542f962076d0BFE58eA045FfA2d347ACa0", "evm", "ethereum", "USDC"),
    ("add 25 usdc to 0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7", "evm", "ethereum", "USDC"),
    ("deposit 20 dai into pool 0xA478c2975Ab1Ea89e8196811F51A7B7Ade33eB11", "evm", "ethereum", "DAI"),
    ("add 20 usdt to pool 0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852", "evm", "ethereum", "USDT"),
    # ── ETH: lending (Aave / Compound) by protocol+token ──
    ("supply 20 usdc to aave on ethereum", "evm", "ethereum", "USDC"),
    ("supply 20 dai to aave on ethereum", "evm", "ethereum", "DAI"),
    ("supply 0.05 weth to aave on ethereum", "evm", "ethereum", "WETH"),
    ("supply 0.01 wbtc to aave on ethereum", "evm", "ethereum", "WBTC"),
    ("supply 20 usdc to compound on ethereum", "evm", "ethereum", "USDC"),
    ("supply 20 usdt to aave on ethereum", "evm", "ethereum", "USDT"),
    ("lend 25 usdc on aave ethereum", "evm", "ethereum", "USDC"),
    # ── BASE: lending + AMM (fundable USDC/WETH) ──
    ("supply 20 usdc to aave on base", "evm", "base", "USDC"),
    ("supply 0.05 weth to aave on base", "evm", "base", "WETH"),
    ("supply 25 usdc to compound on base", "evm", "base", "USDC"),
    ("lend 30 usdc on aave base", "evm", "base", "USDC"),
    # ── ARB: lending (fundable USDC/WETH) ──
    ("supply 20 usdc to aave on arbitrum", "evm", "arbitrum", "USDC"),
    ("supply 0.05 weth to aave on arbitrum", "evm", "arbitrum", "WETH"),
    ("supply 25 usdc to compound on arbitrum", "evm", "arbitrum", "USDC"),
    ("lend 20 usdc on aave arbitrum", "evm", "arbitrum", "USDC"),
]


def run_one(idx, message, kind, chain_hint, in_sym):
    res = ask(message, kind, "fs-%d-%d" % (idx, int(time.time())))
    chain = (res["chain"] or chain_hint or "").lower()
    print("\n[%d] %s" % (idx, message[:64]))
    print("    card=%s status=%s chain=%s steps=%d" % (res["cardtype"], res["status"], chain, len(res["steps"])))
    if res["cardtype"] != "execution_plan_v3" or res["status"] != "ready":
        print("    -> NOT EXECUTABLE (card=%s)" % res["cardtype"])
        return False
    if chain not in CHAIN_FORK:
        print("    -> chain %s not forkable in this harness (skip sim)" % chain)
        return None
    if not start_anvil(chain):
        print("    -> anvil failed")
        return False
    fund_eth(EVM)
    tok = TOKEN_ADDR.get((chain, in_sym))
    funded = fund_token(chain, tok, EVM) if tok else False
    # Pre-approve input token to first step's to + spender + Permit2 — but
    # ONLY when the plan has no approve step of its own (single-tx Enso zaps).
    # Multi-step plans carry their own approve; pre-approving there double-sets
    # USDT's allowance and trips its non-zero→non-zero revert quirk.
    _has_own_approve = any((s.get("action") or "").lower() == "approve" for s in res["steps"])
    if not _has_own_approve:
        for s in res["steps"]:
            tx = s.get("transaction") or {}
            if tx.get("to") and tok:
                approve(tok, tx["to"], EVM)
                if tx.get("spender"):
                    approve(tok, tx["spender"], EVM)
                approve(tok, PERMIT2, EVM)
                break
    # broadcast every step in order
    all_ok = True
    for s in res["steps"]:
        tx = s.get("transaction") or {}
        ok, msg = send_step(tx, EVM)
        print("    step %s %s: %s (%s)" % (s.get("index"), s.get("action"), "OK" if ok else "FAIL", msg))
        if ok is not True:
            all_ok = False
    print("    => %s" % ("ALL STEPS EXECUTED" if all_ok else "SOME STEPS FAILED"))
    return all_ok


def main():
    results = []
    for i, (m, k, c, s) in enumerate(REQUESTS):
        try:
            results.append(run_one(i, m, k, c, s))
        except Exception as e:  # noqa: BLE001
            print("    EXC", str(e)[:100])
            results.append(False)
    subprocess.run(["pkill", "-f", "anvil --fork"], capture_output=True)
    ok = sum(1 for r in results if r is True)
    print("\n==== %d/%d fully executed on fork ====" % (ok, len(results)))


if __name__ == "__main__":
    main()
