import json
import unittest

from app.agents.crypto_agent import _build_bridge_tx, _build_swap_tx
from app.core.config import settings


class TransactionConfigTests(unittest.TestCase):
    def test_build_swap_tx_returns_clear_error_when_enso_key_missing(self):
        old_key = settings.enso_api_key
        try:
            settings.enso_api_key = ""
            result = _build_swap_tx(
                json.dumps(
                    {
                        "chain": "evm",
                        "token_in": "native",
                        "token_out": "USDT",
                        "amount": "100000000000000000",
                        "chain_id": 56,
                    }
                ),
                user_address="0xc9f19704a645880b8cfff2637499b25453739c43",
                chain_id=56,
            )
            self.assertIn("ENSO_API_KEY", result)
        finally:
            settings.enso_api_key = old_key

    def test_build_bridge_tx_rejects_invalid_solana_destination_address(self):
        result = _build_bridge_tx(
            json.dumps(
                {
                    "src_chain_id": 56,
                    "dst_chain_id": 7565164,
                    "token_in": "native",
                    "token_out": "SOL",
                    "amount": "100000000000000000",
                    "recipient": "not-a-solana-address",
                }
            ),
            user_address="0xc9f19704a645880b8cfff2637499b25453739c43",
            default_chain_id=56,
            solana_address="",
        )
        self.assertIn("valid Solana recipient address", result)


if __name__ == "__main__":
    unittest.main()
