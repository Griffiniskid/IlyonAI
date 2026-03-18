from src.analytics.wallet_forensics import WalletForensicsEngine


def test_wallet_forensics_detects_simple_deployer_and_insider_heuristics():
    engine = WalletForensicsEngine()

    heuristics = engine.detect_entity_heuristics(
        deployer_wallet="deployer-1",
        top_holders=[
            {"address": "deployer-1", "share": 0.22},
            {"address": "wallet-a", "share": 0.11},
            {"address": "wallet-b", "share": 0.109},
        ],
    )

    codes = {heuristic.code for heuristic in heuristics}

    assert "deployer_retained_supply" in codes
    assert "possible_insider_cluster" in codes
