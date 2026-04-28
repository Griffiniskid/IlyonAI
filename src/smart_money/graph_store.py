from uuid import uuid4
from dataclasses import dataclass


@dataclass
class EntityRecord:
    wallets: list[str]
    reason: str


class GraphStore:
    def __init__(self) -> None:
        self.entities: dict[str, EntityRecord] = {}
        self.wallet_to_entity: dict[str, str] = {}

    def link_wallets(self, wallets: list[str], reason: str) -> str:
        for wallet in wallets:
            previous_entity_id = self.wallet_to_entity.get(wallet)
            if previous_entity_id is None:
                continue
            previous_wallets = self.entities[previous_entity_id].wallets
            if wallet in previous_wallets:
                previous_wallets.remove(wallet)

        entity_id = f"entity-{uuid4().hex[:8]}"
        self.entities[entity_id] = EntityRecord(wallets=list(wallets), reason=reason)
        for wallet in wallets:
            self.wallet_to_entity[wallet] = entity_id
        return entity_id

    def get_entity_id_for_wallet(self, wallet: str) -> str | None:
        return self.wallet_to_entity.get(wallet)

    def get_wallets_for_entity(self, entity_id: str) -> list[str]:
        entity = self.entities.get(entity_id)
        if entity is None:
            return []
        return list(entity.wallets)

    def get_link_reason_for_entity(self, entity_id: str) -> str | None:
        entity = self.entities.get(entity_id)
        if entity is None:
            return None
        return entity.reason
