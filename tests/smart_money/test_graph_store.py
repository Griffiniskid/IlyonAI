def test_graph_store_links_wallets_into_entity_cluster():
    from src.smart_money.graph_store import GraphStore

    store = GraphStore()
    entity_id = store.link_wallets(["w1", "w2"], reason="shared_funding")

    assert entity_id.startswith("entity-")
    assert store.get_wallets_for_entity(entity_id) == ["w1", "w2"]
    assert store.get_link_reason_for_entity(entity_id) == "shared_funding"


def test_graph_store_exposes_mapping_and_cluster_queries():
    from src.smart_money.graph_store import GraphStore

    store = GraphStore()
    entity_id = store.link_wallets(["w1", "w2"], reason="shared_funding")

    assert store.get_entity_id_for_wallet("w1") == entity_id
    assert store.get_entity_id_for_wallet("w2") == entity_id
    assert store.get_wallets_for_entity(entity_id) == ["w1", "w2"]
    assert store.get_link_reason_for_entity(entity_id) == "shared_funding"


def test_graph_store_relink_moves_wallet_out_of_previous_entity():
    from src.smart_money.graph_store import GraphStore

    store = GraphStore()
    first_entity_id = store.link_wallets(["w1", "w2"], reason="shared_funding")
    second_entity_id = store.link_wallets(["w2", "w3"], reason="coordinated_trading")

    assert first_entity_id != second_entity_id
    assert store.get_wallets_for_entity(first_entity_id) == ["w1"]
    assert store.get_entity_id_for_wallet("w2") == second_entity_id
    assert store.get_wallets_for_entity(second_entity_id) == ["w2", "w3"]
