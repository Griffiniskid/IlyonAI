from src.smart_money.graph_store import GraphStore


class ProfileService:
    def __init__(self, graph_store: GraphStore) -> None:
        self.graph_store = graph_store

    def get_wallet_profile(self, wallet: str) -> dict[str, object]:
        entity_id = self.graph_store.get_entity_id_for_wallet(wallet)
        if entity_id is None:
            return {
                "wallet": wallet,
                "entity_id": None,
                "linked_wallets": [],
                "link_reason": None,
            }

        wallets = self.graph_store.get_wallets_for_entity(entity_id)
        linked_wallets = [candidate for candidate in wallets if candidate != wallet]

        return {
            "wallet": wallet,
            "entity_id": entity_id,
            "linked_wallets": linked_wallets,
            "link_reason": self.graph_store.get_link_reason_for_entity(entity_id),
        }
