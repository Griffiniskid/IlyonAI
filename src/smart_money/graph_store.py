"""
Entity graph store with smart linking heuristics.

Maintains a graph of wallet entities with automated linking
via cross-chain address matching, funding source analysis,
and temporal clustering.
"""

from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class EntityRecord:
    wallets: list[str]
    reason: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tags: list[str] = field(default_factory=list)
    label: Optional[str] = None
    risk_level: Optional[str] = None
    total_volume_usd: float = 0.0
    last_active: Optional[str] = None
    chains: list[str] = field(default_factory=list)


class GraphStore:
    def __init__(self) -> None:
        self.entities: dict[str, EntityRecord] = {}
        self.wallet_to_entity: dict[str, str] = {}
        self._funding_sources: dict[str, str] = {}  # wallet -> funding source wallet

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

    def get_entity_record(self, entity_id: str) -> EntityRecord | None:
        return self.entities.get(entity_id)

    def update_entity_metadata(
        self,
        entity_id: str,
        label: str | None = None,
        tags: list[str] | None = None,
        risk_level: str | None = None,
        total_volume_usd: float | None = None,
        last_active: str | None = None,
        chains: list[str] | None = None,
    ) -> bool:
        """Update metadata on an existing entity."""
        entity = self.entities.get(entity_id)
        if entity is None:
            return False
        if label is not None:
            entity.label = label
        if tags is not None:
            entity.tags = tags
        if risk_level is not None:
            entity.risk_level = risk_level
        if total_volume_usd is not None:
            entity.total_volume_usd = total_volume_usd
        if last_active is not None:
            entity.last_active = last_active
        if chains is not None:
            entity.chains = chains
        return True

    def merge_entities(self, entity_id_a: str, entity_id_b: str, reason: str) -> str | None:
        """Merge two entities into one, combining all wallets."""
        entity_a = self.entities.get(entity_id_a)
        entity_b = self.entities.get(entity_id_b)
        if entity_a is None or entity_b is None:
            return None

        combined_wallets = list(set(entity_a.wallets + entity_b.wallets))
        combined_reason = f"{entity_a.reason}; {entity_b.reason}; merged: {reason}"
        combined_tags = list(set(entity_a.tags + entity_b.tags))
        combined_chains = list(set(entity_a.chains + entity_b.chains))

        new_entity_id = f"entity-{uuid4().hex[:8]}"
        self.entities[new_entity_id] = EntityRecord(
            wallets=combined_wallets,
            reason=combined_reason,
            tags=combined_tags,
            label=entity_a.label or entity_b.label,
            risk_level=entity_a.risk_level or entity_b.risk_level,
            total_volume_usd=entity_a.total_volume_usd + entity_b.total_volume_usd,
            last_active=max(
                entity_a.last_active or "",
                entity_b.last_active or "",
            ) or None,
            chains=combined_chains,
        )

        for wallet in combined_wallets:
            self.wallet_to_entity[wallet] = new_entity_id

        # Clean up old entities
        del self.entities[entity_id_a]
        del self.entities[entity_id_b]

        return new_entity_id

    def add_wallet_to_entity(self, entity_id: str, wallet: str, reason: str = "") -> bool:
        """Add a wallet to an existing entity."""
        entity = self.entities.get(entity_id)
        if entity is None:
            return False

        # Remove from previous entity if any
        prev = self.wallet_to_entity.get(wallet)
        if prev and prev in self.entities:
            prev_entity = self.entities[prev]
            if wallet in prev_entity.wallets:
                prev_entity.wallets.remove(wallet)

        if wallet not in entity.wallets:
            entity.wallets.append(wallet)
        self.wallet_to_entity[wallet] = entity_id

        if reason:
            entity.reason = f"{entity.reason}; added {wallet}: {reason}"
        return True

    def register_funding_source(self, wallet: str, funder: str) -> None:
        """Record that 'wallet' was funded by 'funder'."""
        self._funding_sources[wallet.lower()] = funder.lower()

    def resolve_cross_chain(self, address: str, chains: list[str]) -> str:
        """
        Auto-link the same address across multiple chains.

        Same address on Ethereum, BSC, Polygon, etc. is almost certainly
        the same entity since EVM uses the same address derivation.
        """
        address_lower = address.lower()
        existing_entity = self.wallet_to_entity.get(address_lower)

        # Create chain-tagged wallet identifiers
        chain_wallets = [f"{address_lower}" for _ in chains]

        if existing_entity:
            entity = self.entities[existing_entity]
            entity.chains = list(set(entity.chains + chains))
            return existing_entity

        entity_id = self.link_wallets(
            [address_lower],
            f"Cross-chain EVM address active on: {', '.join(chains)}",
        )
        entity = self.entities[entity_id]
        entity.chains = chains
        return entity_id

    def resolve_by_funding_source(self) -> list[str]:
        """
        Link wallets that share the same funding source.

        Returns list of newly created entity IDs.
        """
        # Group wallets by funding source
        funder_groups: dict[str, list[str]] = {}
        for wallet, funder in self._funding_sources.items():
            funder_groups.setdefault(funder, []).append(wallet)

        new_entities = []
        for funder, wallets in funder_groups.items():
            if len(wallets) < 2:
                continue

            # Check if these wallets are already in the same entity
            entity_ids = set()
            for w in wallets:
                eid = self.wallet_to_entity.get(w)
                if eid:
                    entity_ids.add(eid)

            if len(entity_ids) <= 1 and entity_ids:
                continue

            # Link them together
            all_wallets = list(set(wallets + [funder]))
            entity_id = self.link_wallets(
                all_wallets,
                f"Shared funding source: {funder} funded {len(wallets)} wallets",
            )
            entity = self.entities[entity_id]
            entity.tags.append("shared_funding")
            new_entities.append(entity_id)

        return new_entities

    def get_stats(self) -> dict:
        """Get summary statistics about the entity graph."""
        total_wallets = len(self.wallet_to_entity)
        total_entities = len(self.entities)
        avg_wallets = total_wallets / total_entities if total_entities > 0 else 0
        largest_entity = max(
            (len(e.wallets) for e in self.entities.values()),
            default=0,
        )
        tagged_count = sum(1 for e in self.entities.values() if e.tags)
        labeled_count = sum(1 for e in self.entities.values() if e.label)

        return {
            "total_entities": total_entities,
            "total_wallets_tracked": total_wallets,
            "average_wallets_per_entity": round(avg_wallets, 2),
            "largest_entity_size": largest_entity,
            "tagged_entities": tagged_count,
            "labeled_entities": labeled_count,
            "funding_sources_tracked": len(self._funding_sources),
        }
