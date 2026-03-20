def test_profile_service_builds_basic_wallet_profile_from_graph_store():
    from src.smart_money.graph_store import GraphStore
    from src.smart_money.profile_service import ProfileService

    store = GraphStore()
    entity_id = store.link_wallets(["w1", "w2"], reason="shared_funding")
    service = ProfileService(store)

    profile = service.get_wallet_profile("w1")

    assert profile["wallet"] == "w1"
    assert profile["entity_id"] == entity_id
    assert profile["linked_wallets"] == ["w2"]
    assert profile["link_reason"] == "shared_funding"


def test_profile_service_returns_empty_profile_when_wallet_not_found():
    from src.smart_money.graph_store import GraphStore
    from src.smart_money.profile_service import ProfileService

    service = ProfileService(GraphStore())

    profile = service.get_wallet_profile("missing")

    assert profile == {
        "wallet": "missing",
        "entity_id": None,
        "linked_wallets": [],
        "link_reason": None,
    }
