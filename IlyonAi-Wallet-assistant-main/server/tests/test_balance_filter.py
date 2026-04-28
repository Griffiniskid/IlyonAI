import unittest
import tempfile
from pathlib import Path

from app.agents.crypto_agent import _passes_balance_filter, _load_moralis_api_key


class BalanceFilterTests(unittest.TestCase):
    def test_filters_possible_spam_even_when_value_is_high(self):
        self.assertFalse(
            _passes_balance_filter({"possible_spam": True}, trusted_usd=100.0, ui_bal=1000.0)
        )

    def test_keeps_micro_heavyweight_tokens_with_real_usd_value(self):
        self.assertTrue(
            _passes_balance_filter({"possible_spam": False}, trusted_usd=0.05, ui_bal=0.00002)
        )

    def test_keeps_large_balance_zero_price_meme_tokens(self):
        self.assertTrue(
            _passes_balance_filter({"possible_spam": False}, trusted_usd=0.0, ui_bal=1250000.0)
        )

    def test_filters_true_dust_without_value(self):
        self.assertFalse(
            _passes_balance_filter({"possible_spam": False}, trusted_usd=0.0, ui_bal=0.0)
        )

    def test_load_moralis_api_key_from_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("MORALIS_API_KEY=test-key-from-env\n")
            self.assertEqual(_load_moralis_api_key(env_path), "test-key-from-env")


if __name__ == "__main__":
    unittest.main()
