"""Tests for spec §6g receipt-verification registry."""
from __future__ import annotations

from src.defi.verification import RECEIPT_TABLE, ReceiptKind, verifier_for
from src.defi.verification.receipt_table import list_receipt_kinds


def test_registry_covers_every_kind():
    # 20 spec rows. Module currently surfaces 20 ReceiptKind enum members.
    assert len(ReceiptKind) >= 20
    # Every enum member has a table entry.
    for k in ReceiptKind:
        assert k in RECEIPT_TABLE, f"ReceiptKind.{k.name} missing from RECEIPT_TABLE"


def test_each_entry_has_required_fields():
    for kind, spec in RECEIPT_TABLE.items():
        assert spec.kind == kind
        assert spec.chain_family in {"evm", "solana"}
        assert spec.rpc_method, f"{kind.name} missing rpc_method"
        assert spec.success_predicate, f"{kind.name} missing success_predicate"


def test_evm_kinds_match_chain_family():
    evm_kinds = {
        ReceiptKind.LP_ERC20, ReceiptKind.BPT, ReceiptKind.V3_NFT,
        ReceiptKind.V4_NFT, ReceiptKind.ATOKEN, ReceiptKind.ERC4626_SHARE,
        ReceiptKind.LST_ERC20, ReceiptKind.LRT_ERC20, ReceiptKind.CTOKEN,
        ReceiptKind.PENDLE_PT_YT, ReceiptKind.STARGATE_SHARE,
    }
    for k in evm_kinds:
        assert RECEIPT_TABLE[k].chain_family == "evm"


def test_solana_kinds_match_chain_family():
    solana_kinds = {
        ReceiptKind.KTOKEN, ReceiptKind.POSITION_PDA, ReceiptKind.POSITION_PDA_WITH_NFT,
        ReceiptKind.LP_MINT_SPL, ReceiptKind.JLP, ReceiptKind.MSOL, ReceiptKind.JITOSOL,
        ReceiptKind.INF, ReceiptKind.OBLIGATION_STATE,
    }
    for k in solana_kinds:
        assert RECEIPT_TABLE[k].chain_family == "solana"


def test_v3_nft_says_liquidity_gt_0():
    spec = verifier_for(ReceiptKind.V3_NFT)
    assert "liquidity > 0" in spec.success_predicate.lower()
    assert "ticklower/upper" in spec.success_predicate.lower()


def test_atoken_supply_delta():
    spec = verifier_for("ATOKEN")
    assert "delta" in spec.success_predicate.lower()
    assert "supply_amount" in spec.success_predicate.lower()


def test_raydium_amm_v4_note_warns_redemption_path():
    spec = verifier_for(ReceiptKind.LP_MINT_SPL)
    assert spec.note
    assert "raydium" in spec.note.lower() or "jupiter" in spec.note.lower()


def test_kamino_lend_uses_obligation_state_not_spl():
    spec = verifier_for(ReceiptKind.OBLIGATION_STATE)
    assert spec.note and "no spl" in spec.note.lower()


def test_verifier_for_string_input():
    spec = verifier_for("V3_NFT")
    assert spec is not None
    assert spec.kind == ReceiptKind.V3_NFT


def test_verifier_for_unknown_returns_none():
    assert verifier_for("not_a_real_kind") is None


def test_list_receipt_kinds_is_complete():
    kinds = list_receipt_kinds()
    assert len(kinds) == len(ReceiptKind)
    assert "V3_NFT" in kinds
    assert "MSOL" in kinds
