from src.scoring.shield_gate import shield_for_transaction


def test_shield_warns_for_high_slippage():
    verdict = shield_for_transaction({"slippage_bps": 800, "spender": "Enso"})

    assert verdict.verdict == "RISKY"
    assert verdict.grade == "D"
    assert "High slippage" in verdict.reasons


def test_shield_blocks_known_malicious_destination():
    verdict = shield_for_transaction({"to": "0x000000000000000000000000000000000000dEaD"})

    assert verdict.verdict == "SCAM"
    assert verdict.grade == "F"
    assert "Known malicious destination" in verdict.reasons
