"""Spec §13 Row 15 — Address Lookup Table (ALT) split warning detector.

Verifies the JS-side `checkTxAccountCount` helper returns `needsSplit=true`
for a v0 VersionedTransaction whose static-key list exceeds the configured
threshold (default 28). Hardware wallets (Ledger Solana app) cannot blind-sign
tx beyond this account-count without ALTs, so the sidecar must emit a warning
on every native b64 it ships.

The helper is invoked via Node — uses the sidecar's own node_modules when
present, otherwise falls back to a tests-only @solana/web3.js install at
/tmp/altsplit-test-deps (auto-bootstrapped on first run).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDE_CAR = REPO_ROOT / "services" / "solana-yield-builder"
ALT_HELPER = SIDE_CAR / "src" / "adapters" / "altSplit.js"
# Cross-platform: /tmp on Linux/Mac, %TEMP% on Windows.
FALLBACK_DEPS = Path(tempfile.gettempdir()) / "altsplit-test-deps"


def _has_sidecar_web3() -> bool:
    pkg = SIDE_CAR / "node_modules" / "@solana" / "web3.js" / "package.json"
    return pkg.is_file()


def _has_fallback_web3() -> bool:
    pkg = FALLBACK_DEPS / "node_modules" / "@solana" / "web3.js" / "package.json"
    return pkg.is_file()


def _bootstrap_fallback_deps() -> bool:
    """Best-effort install of @solana/web3.js into /tmp; returns True on success."""
    if _has_fallback_web3():
        return True
    if shutil.which("npm") is None:
        return False
    FALLBACK_DEPS.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund",
             "--loglevel", "error", "@solana/web3.js@^1.95.0"],
            cwd=str(FALLBACK_DEPS),
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return _has_fallback_web3()


def _node_available() -> bool:
    return (
        shutil.which("node") is not None
        and ALT_HELPER.exists()
        and (_has_sidecar_web3() or _bootstrap_fallback_deps())
    )


def _run_node(body: str) -> dict:
    """Run a node -e script and return the JSON it prints."""
    # Always import the helper via its absolute path so deps resolve relative
    # to the helper's own location when sidecar deps exist; otherwise we
    # prepend the fallback node_modules via NODE_PATH so `require` finds it.
    env = os.environ.copy()
    # node -e runs from CWD; CWD lacks a node_modules so we must point
    # NODE_PATH at whichever install actually has @solana/web3.js. Prefer
    # the sidecar's tree, fall back to the test-only tmp install.
    if _has_sidecar_web3():
        env["NODE_PATH"] = str(SIDE_CAR / "node_modules")
    else:
        env["NODE_PATH"] = str(FALLBACK_DEPS / "node_modules")
    full_script = (
        f"const {{ checkTxAccountCount }} = require({json.dumps(str(ALT_HELPER))});\n"
        f"{body}"
    )
    result = subprocess.run(
        ["node", "-e", full_script],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"node script failed: rc={result.returncode}\nstderr={result.stderr}\nstdout={result.stdout}"
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(not _node_available(), reason="node + @solana/web3.js sidecar deps required")
def test_check_tx_account_count_warns_above_threshold():
    """A synthetic v0 message with 30 static keys → needsSplit=true at threshold=28."""
    body = textwrap.dedent(
        r"""
        const {
          Keypair,
          MessageV0,
          VersionedTransaction,
        } = require("@solana/web3.js");
        // Build a v0 message directly with 30 static accounts and no IXs so
        // the wire-format account-keys section overflows the 28 threshold
        // without tripping the 1232-byte transaction-size cap that bites
        // when each account requires its own transfer instruction.
        const N = 30;
        const keys = [];
        for (let i = 0; i < N; i++) keys.push(Keypair.generate().publicKey);
        const message = new MessageV0({
          header: {
            numRequiredSignatures: 1,
            numReadonlySignedAccounts: 0,
            numReadonlyUnsignedAccounts: 0,
          },
          staticAccountKeys: keys,
          recentBlockhash: Keypair.generate().publicKey.toBase58(),
          compiledInstructions: [],
          addressTableLookups: [],
        });
        const vtx = new VersionedTransaction(message);
        const b64 = Buffer.from(vtx.serialize()).toString("base64");
        const sz = checkTxAccountCount(b64, 28);
        process.stdout.write(JSON.stringify(sz));
        """
    ).strip()
    payload = _run_node(body)
    assert payload["ok"] is True, payload
    assert payload["accounts"] == 30, payload
    assert payload["needsSplit"] is True, payload


@pytest.mark.skipif(not _node_available(), reason="node + @solana/web3.js sidecar deps required")
def test_check_tx_account_count_quiet_below_threshold():
    """A small tx with ≤ 28 static keys returns needsSplit=false."""
    body = textwrap.dedent(
        r"""
        const {
          Keypair,
          MessageV0,
          VersionedTransaction,
        } = require("@solana/web3.js");
        const N = 5;
        const keys = [];
        for (let i = 0; i < N; i++) keys.push(Keypair.generate().publicKey);
        const message = new MessageV0({
          header: {
            numRequiredSignatures: 1,
            numReadonlySignedAccounts: 0,
            numReadonlyUnsignedAccounts: 0,
          },
          staticAccountKeys: keys,
          recentBlockhash: Keypair.generate().publicKey.toBase58(),
          compiledInstructions: [],
          addressTableLookups: [],
        });
        const vtx = new VersionedTransaction(message);
        const b64 = Buffer.from(vtx.serialize()).toString("base64");
        const sz = checkTxAccountCount(b64, 28);
        process.stdout.write(JSON.stringify(sz));
        """
    ).strip()
    payload = _run_node(body)
    assert payload["ok"] is True
    assert payload["accounts"] == 5
    assert payload["needsSplit"] is False, payload


@pytest.mark.skipif(not _node_available(), reason="node + @solana/web3.js sidecar deps required")
def test_check_tx_account_count_handles_malformed_b64():
    """Invalid b64 returns ok=false, needsSplit=false (fail-soft, no warning leak)."""
    body = textwrap.dedent(
        r"""
        const sz = checkTxAccountCount("not-a-real-base64-blob", 28);
        process.stdout.write(JSON.stringify(sz));
        """
    ).strip()
    payload = _run_node(body)
    assert payload["ok"] is False
    assert payload["needsSplit"] is False
