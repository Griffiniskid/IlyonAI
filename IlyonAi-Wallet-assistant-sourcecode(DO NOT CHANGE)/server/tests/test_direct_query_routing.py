import unittest

from app.api.endpoints import _normalize_short_swap_query


class QueryNormalizationTests(unittest.TestCase):
    def test_normalizes_swap_quick_prompt(self):
        text = _normalize_short_swap_query("🔄 Swap BNB → USDT")
        self.assertEqual(text, "Swap 0.01 BNB to USDT")

    def test_preserves_non_swap_messages(self):
        text = _normalize_short_swap_query("Hello there")
        self.assertEqual(text, "Hello there")


if __name__ == "__main__":
    unittest.main()
