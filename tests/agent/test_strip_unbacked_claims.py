"""V6 safety guard pin tests — refuse contextual-fallback prose that
fabricates execution-plan card text, tx hashes, calldata, bridge fees, or
session-key state assertions without a deterministic tool producing the card.

Surfaced in Pass-4 hand-read across F/G/H/I/E/C categories: LLM-only "Status:
ready · 3 signature(s) required" with empty card_ids, fake `0x3f8a…c1d2` tx
hashes, "auto-compound is confirmed" without any Phase-D broadcast oracle,
and ~1.5KB blobs of fabricated Curve add_liquidity calldata.
"""
from src.agent.simple_runtime import _strip_unbacked_claims


def test_strip_fake_status_ready_with_no_card():
    """C01 t3, G03 t2-4, D08 t4 — LLM writes 'Status: ready · N signatures' prose."""
    txt = (
        "**Aave V3 Supply** — Supply 250.0 USDC via Aave V3 on Optimism. \n"
        "Status: `ready` · 2 signature(s) required.\n\n"
        "**Steps** \n"
        "▶ Step 1 — approve 250 USDC on optimism via aave-v3 (ready) \n"
        "▶ Step 2 — supply 250 USDC on optimism via aave-v3 (ready)\n\n"
        "Open the Execution Plan card above and sign step 1 in your wallet."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert "Status: `ready`" not in out
    assert "Execution Plan card above" not in out
    assert "deterministic Sentinel tool" in out


def test_strip_fake_tx_hash():
    """H04 t2-4, H10 t4, D04 t4, E10 t4 — fabricated tx hashes."""
    txt = (
        "Bridge leg: 100 USDC transferred from Ethereum to Solana via deBridge "
        "(tx 0x3f8a…c1d2). The tokens arrived on Solana."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert "0x3f8a" not in out


def test_strip_etherscan_link():
    """H10 t4 — fake Etherscan URL with fabricated hash."""
    txt = (
        "Swap submitted:\n"
        "- **Tx:** 0x3e7a1c9d4f6b8a2c5e0d9f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1 \n"
        "- **Etherscan:** https://etherscan.io/tx/0x3e7a1c9d4f6b8a2c5e0d9f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1"
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_strip_session_key_state_assertion():
    """I02 t3-t4, I04 t3-t4 — Phase-D session-key state assertion without oracle."""
    txt = (
        "Your Marinade auto-compound is confirmed: 0.1 SOL will be restaked every 7 days."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert "is confirmed" not in out


def test_strip_revoked_assertion():
    """I02 t4 — fake 'policy already revoked' without on-chain proof."""
    txt = (
        "The autonomous rebalancing policy and its $100-per-day spend cap "
        "have already been revoked. No active approvals remain."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True
    assert "already been revoked" not in out


def test_strip_fabricated_calldata_blob():
    """H07 t2 — 1.5KB of fake Curve add_liquidity calldata."""
    txt = "Calldata: 0x" + "a" * 200 + "..."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_strip_fabricated_bridge_fee():
    """H06 t2/t4 — invented bridge-fee numbers."""
    txt = (
        "Bridge fee for 0.1 ETH via deBridge from Arbitrum to Base is about "
        "0.0005 ETH (~ $0.9 at current prices)."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is True


def test_preserve_when_real_card_emitted():
    """When deterministic tool produced a card, trust the prose summary."""
    txt = (
        "**Aave V3 Supply** — Supply 100.0 USDC via Aave V3 on Base.\n"
        "Status: `ready` · 2 signature(s) required."
    )
    out, stripped = _strip_unbacked_claims(txt, has_real_card=True)
    assert stripped is False
    assert out == txt


def test_preserve_legit_short_content():
    """Plain informational text with no fabrication should pass through."""
    txt = "USDC on Base is supported via Aave V3, Compound V3, and Morpho Blue."
    out, stripped = _strip_unbacked_claims(txt, has_real_card=False)
    assert stripped is False
    assert out == txt


def test_strip_empty_passthrough():
    """Empty content is a no-op."""
    out, stripped = _strip_unbacked_claims("", has_real_card=False)
    assert stripped is False
    assert out == ""
