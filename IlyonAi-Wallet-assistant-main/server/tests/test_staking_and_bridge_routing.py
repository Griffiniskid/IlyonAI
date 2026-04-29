import json
import unittest
from unittest.mock import Mock, patch

from app.agents.crypto_agent import _build_bridge_tx, _build_stake_tx, _resolve_token_metadata, get_staking_options
from app.api.endpoints import _extract_chain_alias, _try_direct_balance, _try_direct_bridge, _try_direct_stake, _try_direct_staking_info, _try_direct_swap


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


if __name__ == "__main__":
    unittest.main()
