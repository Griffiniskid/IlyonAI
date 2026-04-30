import json
import unittest
from unittest.mock import Mock, patch

from app.agents.crypto_agent import _build_bridge_tx, _build_stake_tx, _resolve_token_metadata, build_solana_swap, get_staking_options
from app.api.endpoints import _extract_chain_alias, _format_direct_swap_result, _try_direct_balance, _try_direct_bridge, _try_direct_stake, _try_direct_staking_info, _try_direct_swap, _try_direct_swap_clarification, _try_direct_transfer_clarification


class DirectStakingRoutingTests(unittest.TestCase):
    @patch("app.agents.crypto_agent._build_stake_tx")
    def test_direct_stake_maps_bnb_to_bsc(self, mocked_build_stake_tx):
        mocked_build_stake_tx.return_value = '{"status":"ok"}'

        _try_direct_stake("stake bnb", "0x1111111111111111111111111111111111111111", 1)

        raw, _user_address, effective_chain = mocked_build_stake_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token"], "BNB")
        self.assertEqual(payload["chain_id"], 56)
        self.assertEqual(effective_chain, 56)

    @patch("app.agents.crypto_agent._build_stake_tx")
    def test_direct_stake_routes_solana_amount_to_solana_wallet(self, mocked_build_stake_tx):
        mocked_build_stake_tx.return_value = '{"status":"ok"}'

        _try_direct_stake(
            "stake 0.2 sol",
            "0x1111111111111111111111111111111111111111",
            101,
            "SoL4naPubKey111111111111111111111111111111",
        )

        raw, _user_address, effective_chain, solana_wallet = mocked_build_stake_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token"], "SOL")
        self.assertEqual(payload["amount"], "0.2")
        self.assertEqual(payload["chain_id"], 101)
        self.assertEqual(effective_chain, 101)
        self.assertEqual(solana_wallet, "SoL4naPubKey111111111111111111111111111111")

    @patch("app.agents.crypto_agent.build_solana_swap")
    def test_build_stake_tx_solana_uses_jito_swap(self, mocked_build_solana_swap):
        mocked_build_solana_swap.return_value = json.dumps({
            "status": "ok",
            "type": "solana_swap_proposal",
            "chain_type": "solana",
            "swapTransaction": "base64tx",
            "out_amount": "123000000",
            "ui_out_amount": 0.123,
            "in_symbol": "SOL",
            "out_symbol": "JITO",
        })

        result = json.loads(_build_stake_tx(
            json.dumps({"token": "SOL", "protocol": "jito", "amount": "0.2", "chain_id": 101}),
            "",
            101,
            "SoL4naPubKey111111111111111111111111111111",
        ))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "stake")
        self.assertEqual(result["route_summary"], "Stake via Jito JitoSOL")
        self.assertEqual(result["protocol_url"], "https://www.jito.network/staking/")
        raw = mocked_build_solana_swap.call_args.args[0]
        payload = json.loads(raw)
        self.assertEqual(payload["sell_token"], "SOL")
        self.assertEqual(payload["buy_token"], "jito")
        self.assertEqual(payload["sell_amount"], "0.2")
        self.assertEqual(payload["user_pubkey"], "SoL4naPubKey111111111111111111111111111111")

    @patch("app.agents.crypto_agent.settings.enso_api_key", "test-key")
    @patch("app.agents.crypto_agent.httpx.get")
    @patch("app.agents.crypto_agent._resolve_token_metadata")
    def test_build_stake_tx_converts_decimal_bnb_amount_to_wei(self, mocked_resolve_token, mocked_get):
        mocked_resolve_token.side_effect = [
            ("0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", 18, 56),
            ("0x1bdd3Cf7F79cfB8EdbB955f20ad99211551BA275", 18, 56),
        ]
        mocked_get.return_value.raise_for_status.return_value = None
        mocked_get.return_value.json.return_value = {
            "tx": {"from": "0x1111111111111111111111111111111111111111", "to": "0x2222222222222222222222222222222222222222", "data": "0x", "value": "0x0"},
            "amountOut": "1",
        }

        result = json.loads(_build_stake_tx(
            json.dumps({"token": "BNB", "protocol": "binance", "amount": "0.01", "chain_id": 56}),
            "0x1111111111111111111111111111111111111111",
            56,
        ))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(mocked_get.call_args.kwargs["params"]["amountIn"], "10000000000000000")

    @patch("app.agents.crypto_agent.get_staking_options")
    def test_staking_link_query_uses_staking_options_helper(self, mocked_get_staking_options):
        mocked_get_staking_options.return_value = '{"type":"universal_cards","cards":[]}'

        result = _try_direct_staking_info("can you give me a link to protocol where i can stake bnb")

        self.assertEqual(result, '{"type":"universal_cards","cards":[]}')
        mocked_get_staking_options.assert_called_once()


class DirectBalanceRoutingTests(unittest.TestCase):
    @patch("app.agents.crypto_agent.get_smart_wallet_balance")
    def test_balance_query_uses_direct_balance_handler(self, mocked_balance):
        mocked_balance.return_value = '{"type":"balance_report","balances":[]}'

        result = _try_direct_balance("💰 My balance", "0x1111111111111111111111111111111111111111", "")

        self.assertEqual(result, '{"type":"balance_report","balances":[]}')
        mocked_balance.assert_called_once_with("0x1111111111111111111111111111111111111111", "0x1111111111111111111111111111111111111111", "")


class DirectSwapRoutingTests(unittest.TestCase):
    def test_bsc_eth_symbol_resolves_to_binance_peg_eth(self):
        address, decimals, chain_id = _resolve_token_metadata("ETH", 56)

        self.assertEqual(address, "0x2170Ed0880ac9A755fd29B2688956BD959F933F8")
        self.assertEqual(decimals, 18)
        self.assertEqual(chain_id, 56)

    def test_avalanche_usdc_resolves_to_avalanche_registry(self):
        address, decimals, chain_id = _resolve_token_metadata("USDC", 43114)

        self.assertEqual(address, "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E")
        self.assertEqual(decimals, 6)
        self.assertEqual(chain_id, 43114)

    @patch("app.agents.crypto_agent._build_swap_tx")
    def test_direct_swap_keeps_bnb_to_eth_on_bsc(self, mocked_build_swap_tx):
        mocked_build_swap_tx.return_value = '{"status":"ok","chain_type":"evm"}'

        result = _try_direct_swap(
            "swap 0.003 bnb for eth",
            "0x1111111111111111111111111111111111111111",
            "SoL4naPubKey111111111111111111111111111111",
            1,
        )

        self.assertEqual(result, '{"status":"ok","chain_type":"evm"}')
        raw, _user_address, effective_chain = mocked_build_swap_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token_in"], "BNB")
        self.assertEqual(payload["token_out"], "ETH")
        self.assertEqual(payload["amount"], "3000000000000000")
        self.assertEqual(payload["chain_id"], 56)
        self.assertEqual(effective_chain, 56)

    @patch("app.agents.crypto_agent._build_swap_tx")
    def test_direct_swap_keeps_binance_peg_eth_input_on_bsc(self, mocked_build_swap_tx):
        mocked_build_swap_tx.return_value = '{"status":"ok","chain_type":"evm"}'

        _try_direct_swap(
            "swap 0.003 eth for bnb",
            "0x1111111111111111111111111111111111111111",
            "",
            56,
        )

        raw, _user_address, effective_chain = mocked_build_swap_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token_in"], "ETH")
        self.assertEqual(payload["token_out"], "BNB")
        self.assertEqual(payload["chain_id"], 56)
        self.assertEqual(effective_chain, 56)

    @patch("app.agents.crypto_agent._build_swap_tx")
    def test_direct_swap_all_eth_for_bnb_stays_on_bsc(self, mocked_build_swap_tx):
        mocked_build_swap_tx.return_value = '{"status":"ok","chain_type":"evm"}'

        _try_direct_swap(
            "swap all eth for bnb",
            "0x1111111111111111111111111111111111111111",
            "",
            56,
        )

        raw, _user_address, effective_chain = mocked_build_swap_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token_in"], "ETH")
        self.assertEqual(payload["token_out"], "BNB")
        self.assertEqual(payload["chain_id"], 56)
        self.assertEqual(effective_chain, 56)

    @patch("app.agents.crypto_agent.build_solana_swap")
    def test_direct_swap_uses_solana_path_for_sol_pairs(self, mocked_build_solana_swap):
        mocked_build_solana_swap.return_value = '{"status":"ok","chain_type":"solana"}'

        result = _try_direct_swap(
            "swap 0.2 SOL to USDC",
            "0x1111111111111111111111111111111111111111",
            "SoL4naPubKey111111111111111111111111111111",
            56,
        )

        self.assertEqual(result, '{"status":"ok","chain_type":"solana"}')
        raw = mocked_build_solana_swap.call_args.args[0]
        payload = json.loads(raw)
        self.assertEqual(payload["sell_token"], "SOL")
        self.assertEqual(payload["buy_token"], "USDC")
        self.assertEqual(payload["sell_amount"], "0.2")
        self.assertEqual(payload["user_pubkey"], "SoL4naPubKey111111111111111111111111111111")

    def test_direct_solana_swap_error_formats_as_user_message(self):
        result = _format_direct_swap_result(
            '{"status":"error","chain_type":"solana","message":"No WBTC balance on Solana."}'
        )

        self.assertEqual(result, "No WBTC balance on Solana.")

    def test_direct_evm_swap_error_formats_as_user_message(self):
        result = _format_direct_swap_result(
            '{"status":"error","message":"Enso API 429: rate limit"}'
        )

        self.assertEqual(result, "Enso API 429: rate limit")

    def test_amountless_swap_asks_for_amount_before_agent_can_guess(self):
        result = _try_direct_swap_clarification("swap sol to usdc")

        self.assertIn("specify", result.lower())
        self.assertIn("amount", result.lower())

    def test_ambiguous_send_all_tokens_asks_for_token_and_recipient(self):
        result = _try_direct_transfer_clarification("send all my tokens to this address")

        self.assertIn("which token", result.lower())
        self.assertIn("recipient", result.lower())


class _MockResponse:
    def __init__(self, data, ok=True, status_code=200):
        self._data = data
        self.ok = ok
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self):
        return self._data


class SolanaSwapBuilderTests(unittest.TestCase):
    @patch("app.agents.crypto_agent._requests.post")
    @patch("app.agents.crypto_agent._requests.get")
    def test_ray_amount_uses_mint_decimals_not_default_nine(self, mocked_get, mocked_post):
        mocked_get.return_value = _MockResponse({"outAmount": "800000"})
        mocked_post.return_value = _MockResponse({"swapTransaction": "base64-tx"})

        result = json.loads(build_solana_swap(json.dumps({
            "sell_token": "RAY",
            "buy_token": "USDC",
            "sell_amount": "1",
            "user_pubkey": "EE8f92KTgEega5zhWX6UPYBv12WowmwS3TkgoxpUvEgM",
        })))

        quote_params = mocked_get.call_args.kwargs["params"]
        self.assertEqual(quote_params["amount"], 1_000_000)
        self.assertEqual(result["ui_in_amount"], 1.0)
        self.assertEqual(result["ui_out_amount"], 0.8)
        self.assertEqual(result["in_symbol"], "RAY")
        self.assertEqual(result["out_symbol"], "USDC")

    @patch("app.agents.crypto_agent._requests.get")
    @patch("app.agents.crypto_agent._get_solana_spl_balance")
    def test_all_wbtc_without_balance_returns_direct_solana_error(self, mocked_balance, mocked_get):
        mocked_balance.return_value = 0

        result = json.loads(build_solana_swap(json.dumps({
            "sell_token": "WBTC",
            "buy_token": "SOL",
            "sell_amount": "all",
            "user_pubkey": "EE8f92KTgEega5zhWX6UPYBv12WowmwS3TkgoxpUvEgM",
        })))

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["chain_type"], "solana")
        self.assertIn("No WBTC balance", result["message"])
        mocked_get.assert_not_called()


class DirectYieldRoutingTests(unittest.TestCase):
    def test_sol_pair_does_not_imply_solana_chain(self):
        self.assertEqual(_extract_chain_alias("give me liquidity pools with highest apr for sol/usdc"), "")
        self.assertEqual(_extract_chain_alias("give me liquidity pools with highest apr for sol/usdc on solana"), "solana")


class DirectBridgeRoutingTests(unittest.TestCase):
    @patch("app.agents.crypto_agent._build_bridge_tx")
    def test_direct_bridge_inferrs_solana_to_ethereum(self, mocked_build_bridge_tx):
        mocked_build_bridge_tx.return_value = '{"status":"ok","type":"bridge_proposal"}'

        result = _try_direct_bridge(
            "bridge 0.2 sol to eth chain",
            "0x1111111111111111111111111111111111111111",
            "SoL4naPubKey111111111111111111111111111111",
            101,
        )

        self.assertEqual(result, '{"status":"ok","type":"bridge_proposal"}')
        raw, evm_wallet, default_chain, solana_wallet = mocked_build_bridge_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token_in"], "SOL")
        self.assertEqual(payload["amount"], "0.2")
        self.assertEqual(payload["src_chain_id"], 101)
        self.assertEqual(payload["dst_chain_id"], 1)
        self.assertEqual(evm_wallet, "0x1111111111111111111111111111111111111111")
        self.assertEqual(default_chain, 101)
        self.assertEqual(solana_wallet, "SoL4naPubKey111111111111111111111111111111")

    @patch("app.agents.crypto_agent._build_bridge_tx")
    def test_direct_bridge_without_amount_defaults_to_all_token(self, mocked_build_bridge_tx):
        mocked_build_bridge_tx.return_value = '{"status":"ok","type":"bridge_proposal"}'

        result = _try_direct_bridge(
            "bridge usdt from sol chain to eth",
            "0x1111111111111111111111111111111111111111",
            "SoL4naPubKey111111111111111111111111111111",
            101,
        )

        self.assertEqual(result, '{"status":"ok","type":"bridge_proposal"}')
        raw, _evm_wallet, default_chain, _solana_wallet = mocked_build_bridge_tx.call_args.args
        payload = json.loads(raw)
        self.assertEqual(payload["token_in"], "USDT")
        self.assertEqual(payload["amount"], "all")
        self.assertEqual(payload["src_chain_id"], 101)
        self.assertEqual(payload["dst_chain_id"], 1)
        self.assertEqual(default_chain, 101)

    @patch("app.agents.crypto_agent._build_bridge_tx")
    def test_direct_bridge_respects_explicit_from_chain(self, mocked_build_bridge_tx):
        mocked_build_bridge_tx.return_value = '{"status":"ok","type":"bridge_proposal"}'

        _try_direct_bridge(
            "bridge 0.2 sol from sol chain to eth chain",
            "0x1111111111111111111111111111111111111111",
            "SoL4naPubKey111111111111111111111111111111",
            56,
        )

        payload = json.loads(mocked_build_bridge_tx.call_args.args[0])
        self.assertEqual(payload["src_chain_id"], 101)
        self.assertEqual(payload["dst_chain_id"], 1)

    @patch("app.agents.crypto_agent._build_bridge_tx")
    def test_direct_bridge_sol_to_bnb_chain(self, mocked_build_bridge_tx):
        mocked_build_bridge_tx.return_value = '{"status":"ok","type":"bridge_proposal"}'

        _try_direct_bridge(
            "bridge 0.2 sol to bnb chain",
            "0x1111111111111111111111111111111111111111",
            "SoL4naPubKey111111111111111111111111111111",
            101,
        )

        payload = json.loads(mocked_build_bridge_tx.call_args.args[0])
        self.assertEqual(payload["src_chain_id"], 101)
        self.assertEqual(payload["dst_chain_id"], 56)


class StakingOptionsTests(unittest.TestCase):
    def test_get_staking_options_returns_direct_bnb_protocol_cards(self):
        payload = json.loads(get_staking_options("where can I stake BNB"))

        self.assertEqual(payload["type"], "universal_cards")
        titles = [card["title"] for card in payload["cards"]]
        urls = [card["url"] for card in payload["cards"]]
        self.assertTrue(any("Binance" in title for title in titles))
        self.assertTrue(any("Ankr" in title for title in titles))
        self.assertIn("https://www.binance.com/en/staked-bnb", urls)
        self.assertIn("https://www.ankr.com/staking/stake/bnb/", urls)

    def test_get_staking_options_returns_direct_sol_protocol_cards(self):
        payload = json.loads(get_staking_options("where can I stake SOL"))

        self.assertEqual(payload["type"], "universal_cards")
        titles = [card["title"] for card in payload["cards"]]
        urls = [card["url"] for card in payload["cards"]]
        self.assertTrue(any("Jito" in title for title in titles))
        self.assertTrue(any("Marinade" in title for title in titles))
        self.assertIn("https://www.jito.network/staking/", urls)
        self.assertIn("https://marinade.finance/app/staking", urls)


class BridgeBuilderTests(unittest.TestCase):
    @patch("app.agents.crypto_agent._requests.get")
    def test_build_bridge_tx_accepts_solana_source_and_returns_solana_bridge_proposal(self, mocked_get):
        mocked_response = Mock()
        mocked_response.status_code = 200
        mocked_response.json.return_value = {
            "tx": {
                "data": "0x00ff",
            },
            "orderId": "sol-bridge-order",
            "order": {
                "approximateFulfillmentDelay": 12,
            },
            "estimatedTransactionFee": {
                "total": "24162360",
            },
            "usdPriceImpact": -0.92,
            "estimation": {
                "srcChainTokenIn": {
                    "symbol": "SOL",
                    "decimals": 9,
                    "amount": "213448716",
                },
                "srcChainTokenOut": {
                    "symbol": "USDC",
                    "decimals": 6,
                    "amount": "18075884",
                },
                "dstChainTokenOut": {
                    "symbol": "BNB",
                    "decimals": 18,
                    "amount": "1230000000000000",
                }
            },
        }
        mocked_get.return_value = mocked_response

        raw = json.dumps({
            "token_in": "SOL",
            "amount": "200000000",
            "src_chain_id": 101,
            "dst_chain_id": 1,
        })
        result = json.loads(_build_bridge_tx(raw, "", 56, "11111111111111111111111111111111,0x1111111111111111111111111111111111111111"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["type"], "bridge_proposal")
        self.assertEqual(result["chain_type"], "solana")
        self.assertEqual(result["src_chain_id"], 101)
        self.assertEqual(result["dst_chain_id"], 1)
        self.assertEqual(result["from_token_symbol"], "SOL")
        self.assertEqual(result["to_token_symbol"], "ETH")
        self.assertTrue(result["tx"]["serialized"])
        self.assertEqual(result["requested_amount_display"], 0.2)
        self.assertGreater(result["amount_in_display"], result["requested_amount_display"])
        self.assertEqual(result["source_execution_symbol"], "USDC")
        self.assertTrue(result["warnings"])
        self.assertIn("USDC", " ".join(result["warnings"]))

        debridge_params = mocked_get.call_args.kwargs["params"]
        self.assertEqual(debridge_params["srcChainId"], 7565164)
        self.assertEqual(debridge_params["dstChainId"], 1)
        self.assertEqual(debridge_params["srcChainTokenIn"], "11111111111111111111111111111111")
        self.assertEqual(debridge_params["dstChainTokenOut"], "0x0000000000000000000000000000000000000000")

    @patch("app.agents.crypto_agent._requests.get")
    @patch("app.agents.crypto_agent._requests.post")
    def test_build_bridge_tx_all_spl_uses_exact_solana_token_balance(self, mocked_post, mocked_get):
        mocked_balance_response = Mock()
        mocked_balance_response.json.return_value = {
            "result": {
                "value": [{
                    "account": {
                        "data": {
                            "parsed": {
                                "info": {
                                    "tokenAmount": {"amount": "1234567"}
                                }
                            }
                        }
                    }
                }]
            }
        }
        mocked_post.return_value = mocked_balance_response

        mocked_debridge_response = Mock()
        mocked_debridge_response.status_code = 200
        mocked_debridge_response.json.return_value = {
            "tx": {"data": "0x00ff"},
            "orderId": "spl-bridge-order",
            "order": {"approximateFulfillmentDelay": 12},
            "estimatedTransactionFee": {"total": "24162360"},
            "estimation": {
                "srcChainTokenIn": {"symbol": "USDC", "decimals": 6, "amount": "1234567"},
                "dstChainTokenOut": {"symbol": "USDC", "decimals": 6, "amount": "1200000"},
            },
        }
        mocked_get.return_value = mocked_debridge_response

        raw = json.dumps({
            "token_in": "USDC",
            "amount": "all",
            "src_chain_id": 101,
            "dst_chain_id": 1,
        })
        result = json.loads(_build_bridge_tx(
            raw,
            "0x1111111111111111111111111111111111111111",
            101,
            "11111111111111111111111111111111",
        ))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["type"], "bridge_proposal")
        debridge_params = mocked_get.call_args.kwargs["params"]
        self.assertEqual(debridge_params["srcChainTokenInAmount"], "1234567")
        self.assertEqual(debridge_params["srcChainTokenIn"], "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")


class BridgeChainInferenceTests(unittest.TestCase):
    @patch("app.api.endpoints._get_wallet_token_chains")
    def test_infer_bridge_src_chain_finds_wbtc_on_solana(self, mocked_get_chains):
        mocked_get_chains.return_value = [101]

        from app.api.endpoints import _infer_bridge_src_chain
        result = _infer_bridge_src_chain("WBTC", 56, "SoL4naPubKey111111111111111111111111111111")

        self.assertEqual(result, 101)

    @patch("app.api.endpoints._get_wallet_token_chains")
    def test_infer_bridge_src_chain_falls_back_to_active_when_no_wallet_data(self, mocked_get_chains):
        mocked_get_chains.return_value = []

        from app.api.endpoints import _infer_bridge_src_chain
        result = _infer_bridge_src_chain("WBTC", 56, "")

        self.assertEqual(result, 56)

    @patch("app.api.endpoints._get_wallet_token_chains")
    def test_infer_bridge_src_chain_prefers_native_token_mapping(self, mocked_get_chains):
        mocked_get_chains.return_value = [56]

        from app.api.endpoints import _infer_bridge_src_chain
        result = _infer_bridge_src_chain("SOL", 56, "SoL4naPubKey111111111111111111111111111111")

        self.assertEqual(result, 101)


class CompoundActionTests(unittest.TestCase):
    def test_compound_swap_and_bridge_detected(self):
        from app.api.endpoints import _is_compound_action

        result = _is_compound_action(
            "swap 0.2 sol for usdc and then bridge them to eth chain"
        )

        self.assertTrue(result)

    def test_simple_swap_not_compound(self):
        from app.api.endpoints import _is_compound_action

        result = _is_compound_action(
            "swap 0.2 sol for usdc"
        )

        self.assertFalse(result)

    def test_simple_bridge_not_compound(self):
        from app.api.endpoints import _is_compound_action

        result = _is_compound_action(
            "bridge wbtc to eth chain"
        )

        self.assertFalse(result)


class BridgeWalletErrorTests(unittest.TestCase):
    def test_bridge_evm_to_solana_without_evm_wallet_returns_helpful_error(self):
        result = json.loads(_build_bridge_tx(
            json.dumps({
                "token_in": "BNB",
                "amount": "100000000000000000",
                "src_chain_id": 56,
                "dst_chain_id": 101,
            }),
            "",  # No EVM wallet
            56,
            "SoL4naPubKey111111111111111111111111111111",
        ))

        self.assertEqual(result["status"], "error")
        self.assertIn("connect", result["message"].lower())
        self.assertIn("metamask", result["message"].lower())

    def test_bridge_solana_to_evm_without_solana_wallet_returns_helpful_error(self):
        result = json.loads(_build_bridge_tx(
            json.dumps({
                "token_in": "SOL",
                "amount": "200000000",
                "src_chain_id": 101,
                "dst_chain_id": 1,
            }),
            "0x1111111111111111111111111111111111111111",
            56,
            "",  # No Solana wallet
        ))

        self.assertEqual(result["status"], "error")
        self.assertIn("connect", result["message"].lower())
        self.assertIn("phantom", result["message"].lower())


if __name__ == "__main__":
    unittest.main()
