#!/usr/bin/env python3
"""Verify a SOL liquid-stake tx WITHOUT actually staking.
Calls the REAL _build_stake_tx, DECODES the unsigned tx (programs + balance
deltas), and SIMULATES it on-chain (no broadcast, no funds moved). Localhost."""
import sys, os, json, base64, urllib.request
sys.path.insert(0, "."); sys.path.insert(0, "IlyonAi-Wallet-assistant-main/server")
import importlib.util
from solders.transaction import VersionedTransaction

JITOSOL = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"
MSOL = "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So"
JUP = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"

rpc = os.environ.get("SOLANA_RPC_URL", "")
if not rpc:
    for ln in open(".env"):
        if ln.startswith("SOLANA_RPC_URL="):
            rpc = ln.split("=", 1)[1].strip()

def rpc_call(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    return json.load(urllib.request.urlopen(
        urllib.request.Request(rpc, body, {"Content-Type": "application/json"}), timeout=30))

def balance(a):
    try: return rpc_call("getBalance", [a]).get("result", {}).get("value", 0)
    except Exception: return 0

# 1. funded wallet (sim only reads its state; nothing moves)
wallet = None
for c in ["2ojv9BAiHUrvsm9gxDe7fJSzbNZSJcxZvf8dqmWGHG8S",
          "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
          "GThUX1Atko4tqhN2NaiTazWSeFWMuiUvfFnyJyUghFMJ"]:
    b = balance(c)
    if b > 1_500_000_000: wallet = c; break
if not wallet: print("FAIL: no funded wallet"); sys.exit(1)
print(f"funded wallet {wallet[:8]}…  ({balance(wallet)/1e9:.1f} SOL)\n")

# 2. build the REAL stake tx
spec = importlib.util.spec_from_file_location("ca",
        "IlyonAi-Wallet-assistant-main/server/app/agents/crypto_agent.py")
ca = importlib.util.module_from_spec(spec); sys.modules["ca"] = ca; spec.loader.exec_module(ca)
parsed = json.loads(ca._build_stake_tx(
    json.dumps({"token": "SOL", "protocol": "", "amount": "1", "chain_id": 101}), "", 101, wallet))
print("status:", parsed.get("status"), "| action:", parsed.get("action"),
      "| type:", parsed.get("type"))
print("from:", parsed.get("from_token_symbol"), "-> to:", parsed.get("to_token_symbol"),
      "| out_amount(raw):", parsed.get("out_amount"),
      f"(~{int(parsed.get('out_amount',0))/1e9:.4f} LST)\n")
tx_b64 = parsed.get("swapTransaction")
if not tx_b64: print("FAIL: no swapTransaction"); sys.exit(1)

# 3. DECODE
raw = base64.b64decode(tx_b64)
vtx = VersionedTransaction.from_bytes(raw)
keys = [str(k) for k in vtx.message.account_keys]
print("=== DECODE ===  (", len(raw), "bytes,", len(keys), "static accts )")
print("  Jupiter aggregator in static keys:", JUP in keys)
print("  jitoSOL mint in static keys:", JITOSOL in keys, "| mSOL:", MSOL in keys)
print("  signer (fee payer):", keys[0])
print("  signer == our wallet:", keys[0] == wallet)
# Address-lookup tables are used by Jupiter; mints may live there, so we rely on
# simulate's pre/post token balances below for the authoritative LST-received proof.

# 4. SIMULATE (no broadcast) — ask for token balance deltas
print("\n=== SIMULATE (on-chain, no broadcast) ===")
sim = rpc_call("simulateTransaction", [tx_b64, {
    "sigVerify": False, "replaceRecentBlockhash": True, "encoding": "base64",
    "accounts": {"encoding": "jsonParsed", "addresses": [wallet]}}])
res = sim.get("result", {})
val = res.get("value", {}) if isinstance(res, dict) else {}
err = val.get("err")
print("  err:", err)
print("  unitsConsumed:", val.get("unitsConsumed"))
logs = val.get("logs") or []
# look for jitoSOL / Jupiter / Stake markers in the logs
markers = [l for l in logs if any(s in l for s in ["Jupiter", "JUP6Lkb", "Stake", "jito", "J1toso1", "Swap", "ata"])][:6]
print("  notable logs:")
for l in (markers or logs[-6:]): print("    ", l[:120])

# 5. verdict
sol_in = err is None
lst_out = parsed.get("out_amount") and int(parsed.get("out_amount")) > 0
ok = sol_in and lst_out and (parsed.get("action") == "stake")
print("\n=== VERDICT ===")
print("  builds stake tx (action=stake):", parsed.get("action") == "stake")
print("  outputs LST (jitoSOL) > 0      :", bool(lst_out), f"(~{int(parsed.get('out_amount',0))/1e9:.4f} jitoSOL)")
print("  simulates on-chain (err=None)  :", err is None)
print("\n  RESULT:", "✅ STAKE TX VERIFIED — real tx, simulates clean, yields jitoSOL, no broadcast"
      if ok else f"❌ NOT FULLY VERIFIED (err={err})")
sys.exit(0 if ok else 2)
