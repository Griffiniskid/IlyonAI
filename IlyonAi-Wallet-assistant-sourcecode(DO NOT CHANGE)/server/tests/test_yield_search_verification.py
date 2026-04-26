import json
import unittest
from unittest.mock import Mock, patch

from app.agents.crypto_agent import get_defi_analytics
from app.api.endpoints import _try_direct_yield_search


class DirectYieldRoutingTests(unittest.TestCase):
    @patch("app.agents.crypto_agent.get_defi_analytics")
    def test_pair_apr_query_uses_verified_supported_search(self, mocked_analytics):
        mocked_analytics.return_value = '{"type":"universal_cards","cards":[]}'

        _try_direct_yield_search("find the highest apr liquidity pool for usdt/usdc")

        mocked_analytics.assert_called_once_with(
            "USDT/USDC sort:apr",
            supported_only=True,
            verified_only=True,
        )

    @patch("app.agents.crypto_agent.get_defi_analytics")
    def test_pair_apy_query_still_uses_apy_sort(self, mocked_analytics):
        mocked_analytics.return_value = '{"type":"universal_cards","cards":[]}'

        _try_direct_yield_search("find the highest apy liquidity pool for usdt/usdc")

        mocked_analytics.assert_called_once_with(
            "USDT/USDC sort:apy",
            supported_only=True,
            verified_only=True,
        )

    @patch("app.agents.crypto_agent.get_defi_analytics")
    def test_sol_pair_query_does_not_force_solana_chain_alias(self, mocked_analytics):
        mocked_analytics.return_value = '{"type":"universal_cards","cards":[]}'

        _try_direct_yield_search("give me liquidity pools with highest apr for sol/usdc")

        mocked_analytics.assert_called_once_with(
            "SOL/USDC sort:apr",
            supported_only=True,
            verified_only=True,
        )


class DefiAnalyticsVerificationTests(unittest.TestCase):
    @patch("app.agents.crypto_agent._resolve_pool_address")
    @patch("app.agents.crypto_agent._requests.get")
    def test_apr_search_omits_apr_and_shows_verified_apy_links_and_address(self, mocked_get, mocked_resolve):
        mocked_resolve.side_effect = [
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        ]
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            "data": [
                {
                    "chain": "Aptos",
                    "project": "hyperion",
                    "symbol": "USDT-USDC",
                    "tvlUsd": 6338492,
                    "apyBase": 13.91,
                    "apy": 13.91,
                    "apyReward": None,
                    "pool": "aptos-hyperion-pool",
                    "outlier": False,
                    "poolMeta": None,
                    "stablecoin": True,
                    "volumeUsd1d": 150000,
                },
                {
                    "chain": "Ethereum",
                    "project": "uniswap-v3",
                    "symbol": "USDC-USDT",
                    "tvlUsd": 692586,
                    "apyBase": 12.31793,
                    "apyBase7d": 5.14187,
                    "apy": 12.31793,
                    "apyMean30d": 2.78114,
                    "apyReward": None,
                    "pool": "40e2054c-779d-4499-845f-95b4a31277f7",
                    "outlier": False,
                    "poolMeta": "0.05%",
                    "stablecoin": True,
                    "volumeUsd1d": 467464.46101,
                    "volumeUsd7d": 906763.84559,
                },
                {
                    "chain": "Ethereum",
                    "project": "uniswap-v3",
                    "symbol": "USDC-USDT",
                    "tvlUsd": 23072135,
                    "apyBase": 3.92861,
                    "apyBase7d": 3.63763,
                    "apy": 3.92861,
                    "apyMean30d": 1.89621,
                    "apyReward": None,
                    "pool": "e737d721-f45c-40f0-9793-9f56261862b9",
                    "outlier": False,
                    "poolMeta": "0.01%",
                    "stablecoin": True,
                    "volumeUsd1d": 24833254.47357,
                    "volumeUsd7d": 100939608.14818,
                },
            ]
        }
        mocked_get.return_value = mocked_response

        raw = get_defi_analytics(
            "USDT/USDC sort:apr",
            supported_only=True,
            verified_only=True,
        )
        payload = json.loads(raw)

        self.assertEqual(payload["type"], "universal_cards")
        self.assertIn("supported chains", payload["message"])
        self.assertIn("APR is omitted", payload["message"])
        self.assertEqual(len(payload["cards"]), 2)
        top_card = payload["cards"][0]
        self.assertEqual(top_card["subtitle"], "Uniswap V3 · Ethereum")
        self.assertEqual(top_card["details"]["APY (30d avg)"], "2.78%")
        self.assertEqual(top_card["details"]["APY (current)"], "12.32%")
        self.assertEqual(top_card["details"]["Pool Meta"], "0.05%")
        self.assertEqual(top_card["details"]["Pool Address"], "0x1111111111111111111111111111111111111111")
        self.assertNotIn("Fee APR (7d avg)", top_card["details"])
        self.assertEqual(top_card["button_text"], "View Pool")
        self.assertEqual(top_card["defillama_button_text"], "View in DefiLlama")
        self.assertEqual(top_card["defillama_url"], "https://defillama.com/yields/pool/40e2054c-779d-4499-845f-95b4a31277f7")

    @patch("app.agents.crypto_agent._resolve_pool_address")
    @patch("app.agents.crypto_agent._requests.get")
    def test_uniswap_uuid_pool_gets_resolved_protocol_link(self, mocked_get, mocked_resolve):
        mocked_resolve.return_value = "0x0B7AFAC1e504239fdFBfe353F05172ecf6cfd9B5"
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            "data": [
                {
                    "chain": "Arbitrum",
                    "project": "uniswap-v3",
                    "symbol": "USDC-USDT",
                    "tvlUsd": 2403009,
                    "apyBase": 6.0,
                    "apyBase7d": 4.8,
                    "apy": 6.0,
                    "apyMean30d": 3.2,
                    "apyReward": None,
                    "pool": "ba3fb5f5-684e-4834-afca-d58668395b02",
                    "outlier": False,
                    "poolMeta": "0.01%",
                    "stablecoin": True,
                    "volumeUsd1d": 3951647,
                    "volumeUsd7d": 21342920,
                    "underlyingTokens": [
                        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                        "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
                    ],
                }
            ]
        }
        mocked_get.return_value = mocked_response

        raw = get_defi_analytics("USDT/USDC arbitrum sort:apr", supported_only=False, verified_only=True)
        payload = json.loads(raw)

        card = payload["cards"][0]
        self.assertEqual(card["button_text"], "View Pool")
        self.assertEqual(card["url"], "https://app.uniswap.org/explore/pools/arbitrum/0x0B7AFAC1e504239fdFBfe353F05172ecf6cfd9B5")
        self.assertEqual(card["defillama_url"], "https://defillama.com/yields/pool/ba3fb5f5-684e-4834-afca-d58668395b02")
        self.assertEqual(card["details"]["Pool Address"], "0x0B7AFAC1e504239fdFBfe353F05172ecf6cfd9B5")

    @patch("app.agents.crypto_agent._resolve_pool_address")
    @patch("app.agents.crypto_agent._requests.get")
    def test_native_token_query_matches_wrapped_pool_symbols(self, mocked_get, mocked_resolve):
        mocked_resolve.return_value = "So11111111111111111111111111111111111111112"
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            "data": [
                {
                    "chain": "Solana",
                    "project": "raydium-amm",
                    "symbol": "WSOL-USDC",
                    "tvlUsd": 2400000,
                    "apyBase": 8.7,
                    "apyBase7d": 7.8,
                    "apy": 8.7,
                    "apyMean30d": 6.2,
                    "apyReward": None,
                    "pool": "sol-usdc-pool",
                    "outlier": False,
                    "poolMeta": "Concentrated - 0.25%",
                    "stablecoin": False,
                    "volumeUsd1d": 420000,
                    "volumeUsd7d": 2800000,
                    "underlyingTokens": [
                        "So11111111111111111111111111111111111111112",
                        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    ],
                }
            ]
        }
        mocked_get.return_value = mocked_response

        raw = get_defi_analytics("SOL/USDC sort:apr", supported_only=True, verified_only=True)
        payload = json.loads(raw)

        self.assertEqual(payload["type"], "universal_cards")
        self.assertEqual(len(payload["cards"]), 1)
        self.assertEqual(payload["cards"][0]["title"], "WSOL-USDC Pool")


if __name__ == "__main__":
    unittest.main()
