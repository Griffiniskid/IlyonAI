def test_normalizer_emits_canonical_flow_event_for_solana_swap():
    from src.smart_money.normalizer import normalize_event
    event = normalize_event({"chain": "solana", "type": "swap", "wallet": "abc"})
    assert event.chain == "solana"
    assert event.event_type == "swap"


def test_solana_adapter_emits_canonical_flow_event_with_default_chain():
    from src.data.solana import to_canonical_flow_event

    event = to_canonical_flow_event({"type": "swap", "wallet": "abc"})

    assert event.chain == "solana"
    assert event.event_type == "swap"
    assert event.wallet == "abc"


def test_evm_adapter_accepts_canonical_flow_events():
    from src.analytics.behavior_adapters.evm import EVMBehaviorAdapter
    from src.smart_money.normalizer import normalize_event

    adapter = EVMBehaviorAdapter()
    result = adapter.adapt(
        [
            normalize_event(
                {
                    "chain": "ethereum",
                    "type": "buy",
                    "wallet": "0xaaa",
                    "amount_usd": 100,
                }
            ),
            normalize_event(
                {
                    "chain": "ethereum",
                    "type": "sell",
                    "wallet": "0xbbb",
                    "amount_usd": 40,
                }
            ),
        ]
    )

    assert result["whale_summary"]["buy_count"] == 1
    assert result["whale_summary"]["sell_count"] == 1
    assert result["whale_summary"]["net_flow_usd"] == 60


def test_evm_adapter_repeat_wallet_share_uses_canonical_payload_wallet_fallback():
    from src.analytics.behavior_adapters.evm import EVMBehaviorAdapter
    from src.smart_money.models import CanonicalFlowEvent

    adapter = EVMBehaviorAdapter()
    result = adapter.adapt(
        [
            CanonicalFlowEvent(
                chain="ethereum",
                event_type="buy",
                wallet="",
                payload={"wallet": "0xaaa", "amount_usd": 100},
            ),
            CanonicalFlowEvent(
                chain="ethereum",
                event_type="buy",
                wallet="",
                payload={"wallet": "0xaaa", "amount_usd": 50},
            ),
            CanonicalFlowEvent(
                chain="ethereum",
                event_type="sell",
                wallet="",
                payload={"wallet": "0xbbb", "amount_usd": 40},
            ),
        ]
    )

    assert result["whale_summary"]["repeat_wallet_share"] == 2 / 3


def test_normalizer_payload_is_shallow_copy():
    from src.smart_money.normalizer import normalize_event

    raw = {"chain": "solana", "type": "swap", "wallet": "abc", "amount_usd": 42}
    event = normalize_event(raw)
    raw["amount_usd"] = 100

    assert event.payload["amount_usd"] == 42
