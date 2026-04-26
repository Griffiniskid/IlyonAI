import unittest

from app.agents.crypto_agent import clear_session_memory, hydrate_session_memory, has_session_memory, compact_session_memory


class SessionMemoryTests(unittest.TestCase):
    def test_hydrate_session_memory_restores_transcript(self):
        session_id = "test-session-memory"
        clear_session_memory(session_id)

    def test_compact_session_memory_shrinks_large_tx_payloads(self):
        session_id = "test-session-compact"
        clear_session_memory(session_id)

        huge_hex = "0x" + ("ab" * 4000)
        assistant_payload = (
            '{"status":"ok","type":"evm_action_proposal","tx":{"to":"0x123","data":"'
            + huge_hex
            + '","value":"0x0"}}'
        )

        hydrate_session_memory(
            session_id,
            [
                ("user", "swap 0.1 bnb to usdt"),
                ("assistant", assistant_payload),
            ],
        )

        compact_session_memory(session_id)

        from app.agents.crypto_agent import _get_or_create_memory

        history = _get_or_create_memory(session_id).load_memory_variables({})["chat_history"]
        self.assertEqual(len(history), 2)
        self.assertIn("omitted", history[1].content)
        self.assertLess(len(history[1].content), 2500)

        clear_session_memory(session_id)

        hydrate_session_memory(
            session_id,
            [
                ("user", "swap these tokens for USDC"),
                ("assistant", "Which amounts do you want to swap?"),
                ("user", "all tokens"),
                ("assistant", "Got it, I will use the balances from your wallet."),
            ],
        )

        self.assertTrue(has_session_memory(session_id))

        from app.agents.crypto_agent import _get_or_create_memory

        history = _get_or_create_memory(session_id).load_memory_variables({})["chat_history"]
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0].content, "swap these tokens for USDC")
        self.assertEqual(history[1].content, "Which amounts do you want to swap?")
        self.assertEqual(history[2].content, "all tokens")
        self.assertEqual(history[3].content, "Got it, I will use the balances from your wallet.")

        clear_session_memory(session_id)


if __name__ == "__main__":
    unittest.main()
