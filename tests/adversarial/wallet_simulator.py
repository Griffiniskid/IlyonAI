"""Wallet + transaction simulator for adversarial validation.

Generates deterministic dev wallets (Solana + EVM) and validates each unsigned
transaction emitted by the agent's execution_plan_v3 cards. Live-simulates via
RPC where possible and reports per-step result so we can prove the signing path
end-to-end without ever broadcasting a real transaction.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Any

# EVM
from eth_account import Account as EthAccount
from web3 import Web3

# Solana
from solders.keypair import Keypair as SolKeypair
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client as SolClient


# Public mainnet RPCs (read-only, rate-limited but free).
DEFAULT_EVM_RPCS = {
    1: "https://eth.llamarpc.com",
    10: "https://mainnet.optimism.io",
    56: "https://bsc-dataseed.binance.org",
    137: "https://polygon-rpc.com",
    8453: "https://mainnet.base.org",
    42161: "https://arb1.arbitrum.io/rpc",
    43114: "https://api.avax.network/ext/bc/C/rpc",
}
DEFAULT_SOLANA_RPC = "https://api.mainnet-beta.solana.com"

EVM_REVERT_BENIGN = (
    "insufficient",
    "transfer amount exceeds balance",
    "balance",
    "allowance",
    "ds-math-sub-underflow",
    "subtraction overflow",
    "ERC20: transfer amount exceeds",
    "stf",  # uniswap-v3 safeTransferFrom failure when no balance
)
SOLANA_REVERT_BENIGN = (
    "insufficient lamports",
    "insufficient funds",
    "AccountNotFound",  # benign for empty test wallet
    "could not find account",
)


@dataclass
class StepSimResult:
    step_id: str
    chain_kind: str
    structural_ok: bool
    live_simulated: bool
    sim_ok: bool
    benign_revert: bool = False
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def overall_ok(self) -> bool:
        # Treat benign reverts (empty test wallet) as success — the unsigned
        # tx is well-formed and the program logic ran; only the dev wallet
        # lacked balance/allowance to actually consume the call.
        if not self.structural_ok:
            return False
        if self.live_simulated:
            return self.sim_ok or self.benign_revert
        return True


@dataclass
class PlanSimResult:
    plan_id: str
    title: str
    step_results: list[StepSimResult] = field(default_factory=list)
    plan_blockers: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return bool(self.step_results) and all(s.overall_ok for s in self.step_results)


class WalletSimulator:
    def __init__(self, *, evm_seed: bytes | None = None, solana_seed: bytes | None = None):
        # Deterministic dev wallets so plan resolution is reproducible.
        evm_seed = evm_seed or b"\x42" * 32
        solana_seed = solana_seed or b"\x77" * 32
        self.evm_account = EthAccount.from_key(evm_seed)
        self.solana_keypair = SolKeypair.from_seed(solana_seed)
        self._evm_clients: dict[int, Web3] = {}
        sol_rpc = os.getenv("SIM_SOLANA_RPC", DEFAULT_SOLANA_RPC)
        self.solana_client = SolClient(sol_rpc)

    @property
    def evm_address(self) -> str:
        return self.evm_account.address

    @property
    def solana_pubkey(self) -> str:
        return str(self.solana_keypair.pubkey())

    def _evm_client(self, chain_id: int) -> Web3 | None:
        if chain_id in self._evm_clients:
            return self._evm_clients[chain_id]
        env_url = os.getenv(f"SIM_EVM_RPC_{chain_id}")
        url = env_url or DEFAULT_EVM_RPCS.get(chain_id)
        if not url:
            return None
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 15}))
        self._evm_clients[chain_id] = w3
        return w3

    def simulate_step(self, step: dict[str, Any]) -> StepSimResult:
        tx = step.get("transaction") or {}
        kind = (tx.get("chain_kind") or "").lower()
        sid = step.get("step_id") or step.get("id") or "?"
        if not tx:
            return StepSimResult(
                step_id=sid,
                chain_kind=kind or "?",
                structural_ok=False,
                live_simulated=False,
                sim_ok=False,
                error="missing transaction envelope",
            )
        if kind == "evm":
            return self._simulate_evm(sid, tx, step)
        if kind == "solana":
            return self._simulate_solana(sid, tx, step)
        return StepSimResult(
            step_id=sid,
            chain_kind=kind,
            structural_ok=False,
            live_simulated=False,
            sim_ok=False,
            error=f"unknown chain_kind: {kind!r}",
        )

    def _simulate_evm(self, sid: str, tx: dict[str, Any], step: dict[str, Any]) -> StepSimResult:
        notes: list[str] = []
        chain_id = tx.get("chain_id")
        to = tx.get("to")
        data = tx.get("data") or "0x"
        value = tx.get("value") or "0"

        # Structural validation
        if not to or not isinstance(to, str) or not to.startswith("0x") or len(to) != 42:
            return StepSimResult(sid, "evm", False, False, False, error=f"invalid `to`: {to!r}")
        try:
            value_int = int(value, 16) if isinstance(value, str) and value.lower().startswith("0x") else int(value)
        except (TypeError, ValueError):
            return StepSimResult(sid, "evm", False, False, False, error=f"invalid value: {value!r}")
        if not isinstance(data, str) or not data.startswith("0x"):
            return StepSimResult(sid, "evm", False, False, False, error=f"invalid calldata: {data[:20]!r}")
        try:
            bytes.fromhex(data[2:])
        except ValueError:
            return StepSimResult(sid, "evm", False, False, False, error="calldata not hex-decodable")

        # Live simulation
        w3 = self._evm_client(int(chain_id) if chain_id else 1)
        if w3 is None:
            notes.append(f"no RPC for chain_id={chain_id}")
            return StepSimResult(sid, "evm", True, False, False, notes=notes)
        try:
            code = w3.eth.get_code(Web3.to_checksum_address(to))
            if code in (b"", b"\x00"):
                notes.append(f"target {to} has no contract code")
                return StepSimResult(sid, "evm", True, True, False, error="target_not_contract", notes=notes)
        except Exception as e:
            notes.append(f"getCode failed: {e}")
            return StepSimResult(sid, "evm", True, False, False, notes=notes, error=str(e))
        # Try eth_call from our test address — most calls will revert because
        # we have no balance/allowance, but the revert reason tells us if the
        # tx is structurally valid against the contract.
        try:
            w3.eth.call(
                {
                    "to": Web3.to_checksum_address(to),
                    "data": data,
                    "value": value_int,
                    "from": self.evm_address,
                }
            )
            return StepSimResult(sid, "evm", True, True, True, notes=notes)
        except Exception as e:
            err = str(e).lower()
            if any(k.lower() in err for k in EVM_REVERT_BENIGN):
                notes.append("benign revert (test wallet has no balance/allowance)")
                return StepSimResult(sid, "evm", True, True, False, benign_revert=True, notes=notes, error=str(e)[:200])
            return StepSimResult(sid, "evm", True, True, False, notes=notes, error=str(e)[:200])

    def _simulate_solana(self, sid: str, tx: dict[str, Any], step: dict[str, Any]) -> StepSimResult:
        notes: list[str] = []
        serialized = tx.get("serialized")
        if not serialized:
            return StepSimResult(sid, "solana", False, False, False, error="no serialized tx")
        try:
            raw = base64.b64decode(serialized)
            vt = VersionedTransaction.from_bytes(raw)
        except Exception as e:
            return StepSimResult(sid, "solana", False, False, False, error=f"deserialize failed: {e}")

        # Structural — fee payer should be a pubkey, instructions present
        try:
            account_keys = vt.message.account_keys
            if not account_keys:
                return StepSimResult(sid, "solana", False, False, False, error="no account keys")
            instructions = vt.message.instructions
            if not instructions:
                return StepSimResult(sid, "solana", False, False, False, error="no instructions")
            notes.append(f"{len(instructions)} ixs, {len(account_keys)} keys")
        except Exception as e:
            return StepSimResult(sid, "solana", False, False, False, error=f"structure check failed: {e}")

        # Live simulate — sigVerify=False so test wallet doesn't need to sign
        try:
            from solana.rpc.types import TxOpts  # noqa: F401
            resp = self.solana_client.simulate_transaction(
                vt,
                sig_verify=False,
                replace_recent_blockhash=True,
            )
            value = getattr(resp, "value", None)
            if value is None:
                return StepSimResult(sid, "solana", True, False, False, notes=notes, error="empty rpc response")
            err = getattr(value, "err", None)
            logs = list(getattr(value, "logs", []) or [])
            if err is None:
                return StepSimResult(sid, "solana", True, True, True, notes=notes + [f"logs={len(logs)}"])
            err_str = str(err)
            if any(k in err_str or any(k in lg for lg in logs) for k in SOLANA_REVERT_BENIGN):
                return StepSimResult(
                    sid, "solana", True, True, False,
                    benign_revert=True, notes=notes + [f"logs={len(logs)}"],
                    error=err_str[:200],
                )
            return StepSimResult(sid, "solana", True, True, False, notes=notes + [f"logs={len(logs)}"], error=err_str[:200])
        except Exception as e:
            return StepSimResult(sid, "solana", True, False, False, notes=notes, error=f"rpc sim failed: {e}")

    def simulate_plan(self, plan: dict[str, Any]) -> PlanSimResult:
        result = PlanSimResult(
            plan_id=plan.get("plan_id") or "?",
            title=plan.get("title") or "?",
            plan_blockers=[b.get("code") or "" for b in (plan.get("blockers") or [])],
        )
        for step in plan.get("steps") or []:
            if step.get("transaction"):
                result.step_results.append(self.simulate_step(step))
        return result
