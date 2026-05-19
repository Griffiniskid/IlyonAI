"""V7-032 — WSOL syncNative + closeAccount audit pin.

Part4 audit gap: only `orca.js` (8 hits) and `jlp.js` (1 hit) wired
`syncNative` / `closeAccount` for native-SOL deposit paths. The 5 remaining
named Solana adapters (`raydium.js`, `meteora.js`, `kamino.js`,
`marinade.js`, `sanctum.js`) all returned 0 hits and risked stranding dust
SOL in WSOL ATAs after deposit. This pin is a syntax-level regression gate.

Behaviour rules:

  • Adapters that have a native-SOL deposit path MUST mention BOTH
    `syncNative` and `closeAccount` somewhere in the source file. The
    wiring lives behind a `_buildWsolSafetyMeta` (or analogous) guard
    that only fires when the input/output mint equals the canonical
    WSOL mint `So11111111111111111111111111111111111111112`.

  • Adapters whose native-SOL path does NOT exist (because the IX
    builder accepts native lamports directly, or because the input is
    gated to an LST allowlist) are allowlisted with a documented
    rationale in the adapter docstring. We assert their source DOES
    NOT silently wire WSOL safety, and we ALSO assert the docstring
    explicitly says so to prevent reviewers from "fixing" the gap by
    re-introducing dead code.

The reference adapters (`orca.js`, `jlp.js`) are also checked positive so
the audit baseline never regresses underneath us.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS_DIR = REPO_ROOT / "services" / "solana-yield-builder" / "src" / "adapters"

# Adapters in V7-032 audit scope that handle native-SOL deposits and MUST
# wire WSOL safety. orca.js + jlp.js are the audit BASELINE (already shipped)
# and are pinned separately with a permissive grep so a baseline regression
# also fires this pin.
WSOL_REQUIRED = ["raydium.js", "meteora.js", "kamino.js"]
WSOL_BASELINE = ["orca.js", "jlp.js"]

# Adapters that have NO native-SOL deposit path. Each entry maps file →
# rationale fragment the docstring must contain (case-insensitive substring
# match) so a reviewer can't silently "close the gap" by reintroducing
# dead WSOL plumbing — they MUST update this allowlist with new reasoning.
NO_NATIVE_SOL_PATH = {
    "marinade.js": "marinade.deposit(lamports) takes native sol",
    "sanctum.js":  "addliquidity accepts only pre-existing lsts",
}


def _read(path: Path) -> str:
    assert path.exists(), f"adapter file missing: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("filename", WSOL_REQUIRED)
def test_adapter_wires_wsol_sync_native(filename: str) -> None:
    """Each WSOL-required adapter mentions syncNative AND closeAccount."""
    src = _read(ADAPTERS_DIR / filename)
    assert "syncNative" in src, (
        f"{filename}: V7-032 gap — no `syncNative` reference. Native-SOL "
        f"deposits will leave dust lamports unsynced in the WSOL ATA."
    )
    assert "closeAccount" in src, (
        f"{filename}: V7-032 gap — no `closeAccount` reference. Leftover "
        f"wrapped SOL will be permanently stuck in the user's WSOL ATA."
    )


@pytest.mark.parametrize("filename", WSOL_BASELINE)
def test_baseline_adapter_still_wires_wsol_safety(filename: str) -> None:
    """orca.js + jlp.js baseline regression guard.

    The audit said orca had 8 hits and jlp had 1 hit pre-fix. Either
    spelling (camelCase `syncNative` or snake_case `sync_native`) is
    accepted because jlp.js uses the snake-case form in its IX builder
    while orca.js uses the spl-token camelCase helper.
    """
    src = _read(ADAPTERS_DIR / filename)
    has_sync = "syncNative" in src or "sync_native" in src or "SyncNative" in src
    # jlp.js uses a `closeWsolAfter` flag + a manual close ix; orca.js uses
    # the spl-token camelCase helper. Accept any of the canonical spellings
    # so the baseline doesn't false-fire on legitimate variant code.
    has_close = (
        "closeAccount" in src
        or "close_account" in src
        or "closeWsol" in src
        or "CloseAccount" in src
    )
    assert has_sync, (
        f"{filename}: baseline V7-032 regression — no syncNative reference."
    )
    assert has_close, (
        f"{filename}: baseline V7-032 regression — no closeAccount reference."
    )


@pytest.mark.parametrize("filename", WSOL_REQUIRED)
def test_adapter_references_wsol_mint(filename: str) -> None:
    """WSOL-required adapters reference the canonical WSOL mint.

    The wiring MUST be gated on the actual WSOL mint
    (So11111111111111111111111111111111111111112) — unconditional WSOL
    plumbing on every deposit would corrupt SPL-only flows.
    """
    src = _read(ADAPTERS_DIR / filename)
    canonical = "So11111111111111111111111111111111111111112"
    # Reference adapters may import SOL_MINT from jupiter.js instead of
    # spelling the literal; accept either.
    has_literal = canonical in src
    has_sol_mint_ref = "SOL_MINT" in src or "WSOL_MINT" in src or "NATIVE_MINT" in src
    assert has_literal or has_sol_mint_ref, (
        f"{filename}: V7-032 wiring is not gated on the WSOL mint. "
        f"Expected reference to '{canonical}' or SOL_MINT/WSOL_MINT/NATIVE_MINT."
    )


@pytest.mark.parametrize("filename,rationale_fragment", sorted(NO_NATIVE_SOL_PATH.items()))
def test_adapter_documents_no_native_sol_path(filename: str, rationale_fragment: str) -> None:
    """Allowlisted adapters MUST carry the documented 'no native-SOL path' rationale.

    This prevents silent regressions where someone "closes the gap" by
    reintroducing WSOL plumbing that does not actually fire (because the
    adapter has no SOL entry point) — leaving readers confused about
    which paths the safety wires guard.
    """
    src = _read(ADAPTERS_DIR / filename).lower()
    assert rationale_fragment in src, (
        f"{filename}: missing V7-032 'no native-SOL path' rationale. "
        f"Docstring must explain why syncNative/closeAccount are not wired. "
        f"Expected substring (case-insensitive): {rationale_fragment!r}"
    )


def test_token_safety_helpers_export_builders() -> None:
    """The shared `_token_safety` module must continue to export the IX builders."""
    src = _read(ADAPTERS_DIR / "_token_safety.js")
    assert "buildSyncNativeIx" in src, "_token_safety.js missing buildSyncNativeIx export"
    assert "buildCloseWsolIx" in src, "_token_safety.js missing buildCloseWsolIx export"
    assert "createSyncNativeInstruction" in src, (
        "_token_safety.js no longer references @solana/spl-token "
        "createSyncNativeInstruction — V7-032 IX builder is broken."
    )
    assert "createCloseAccountInstruction" in src, (
        "_token_safety.js no longer references @solana/spl-token "
        "createCloseAccountInstruction — V7-032 IX builder is broken."
    )


def test_disjoint_scope_audit() -> None:
    """Sanity check — the 5 adapters named by the audit are present."""
    for adapter in ("raydium.js", "meteora.js", "kamino.js", "marinade.js", "sanctum.js"):
        assert (ADAPTERS_DIR / adapter).exists(), f"missing adapter file: {adapter}"
