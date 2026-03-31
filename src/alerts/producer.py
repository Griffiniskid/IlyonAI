"""Alert producer — generates alerts from existing data sources."""

import logging
from uuid import uuid4

from src.alerts.models import AlertRecord
from src.alerts.store import InMemoryAlertStore
from src.intel.rekt_database import RektDatabase
from src.storage.database import get_database

logger = logging.getLogger(__name__)


class AlertProducer:
    """Generates alerts by polling existing data sources."""

    def __init__(
        self,
        store: InMemoryAlertStore,
        whale_threshold_usd: float = 100_000,
    ):
        self.store = store
        self.whale_threshold_usd = whale_threshold_usd
        self._seen_whale_keys: set[str] = set()
        self._seen_rekt_ids: set[str] = set()

    async def check_whale_flows(self) -> None:
        """Generate alerts for whale transactions above threshold.

        Reads from the database (populated by WhaleTransactionPoller)
        instead of making separate Helius API calls.
        """
        try:
            db = get_database()
            overview = await db.get_whale_overview(hours=1, limit=20)
            txs = overview.get("transactions", [])
        except Exception as e:
            logger.warning(f"Alert producer: failed to fetch whale txs from DB: {e}")
            return

        for tx in txs:
            amount = float(tx.get("amount_usd", 0) or 0)
            if amount < self.whale_threshold_usd:
                continue
            wallet = tx.get("wallet_address") or tx.get("wallet") or "unknown"
            direction = tx.get("direction") or ("inflow" if str(tx.get("type", "")).lower() == "buy" else "outflow")
            dedup_key = f"{wallet}-{amount}-{direction}"
            if dedup_key in self._seen_whale_keys:
                continue
            self._seen_whale_keys.add(dedup_key)
            self.store.add_alert(AlertRecord(
                id=f"whale-{uuid4().hex[:8]}",
                state="new",
                severity="high" if amount >= 500_000 else "medium",
                title=f"Large {direction} detected: ${amount:,.0f} by {wallet[:12]}...",
                kind="whale_flow",
                subject_id=wallet,
            ))

    async def check_rekt_incidents(self) -> None:
        """Generate alerts for new rekt incidents."""
        rekt_db = RektDatabase()
        try:
            incidents = await rekt_db.get_incidents(limit=10)
        except Exception as e:
            logger.warning(f"Alert producer: failed to fetch rekt incidents: {e}")
            return
        finally:
            await rekt_db.close()

        for incident in incidents:
            incident_id = incident.get("id", "")
            if incident_id in self._seen_rekt_ids:
                continue
            self._seen_rekt_ids.add(incident_id)

            amount = incident.get("amount_usd", 0)
            name = incident.get("name", "Unknown")
            self.store.add_alert(AlertRecord(
                id=f"rekt-{uuid4().hex[:8]}",
                state="new",
                severity=incident.get("severity", "medium").lower(),
                title=f"Security incident: {name} (${amount:,.0f} affected)",
                kind="rekt_incident",
                subject_id=incident_id,
            ))

    async def run_cycle(self) -> None:
        """Run one full producer cycle."""
        await self.check_whale_flows()
        await self.check_rekt_incidents()
