import unittest

from app.agents.crypto_agent import _protocol_url


class ProtocolUrlTests(unittest.TestCase):
    def test_orca_uses_live_pools_page(self):
        self.assertEqual(_protocol_url("orca-dex", "solana"), "https://www.orca.so/pools")


if __name__ == "__main__":
    unittest.main()
