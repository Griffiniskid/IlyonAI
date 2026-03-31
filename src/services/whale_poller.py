"""Background poller that accumulates whale transactions from Helius."""

import asyncio
import logging
from datetime import datetime

from src.config import settings
from src.data.solana import SolanaClient
from src.platform.stream_hub import get_stream_hub
from src.storage.database import Database

logger = logging.getLogger(__name__)

TOPIC = "whale-transactions"
DEFAULT_INTERVAL = 300  # 5 minutes — prevents Helius credit drain (~40K calls/day at 15s)
BACKOFF_INTERVAL = 600  # 10 minutes after circuit break
MAX_CONSECUTIVE_FAILURES = 5


class WhaleTransactionPoller:
    """Polls Helius for large DEX swaps and persists them."""

    def __init__(
        self,
        db: Database,
        stream_hub=None,
        poll_interval: int = DEFAULT_INTERVAL,
    ):
        self._db = db
        self._stream_hub = stream_hub or get_stream_hub()
        self._base_interval = poll_interval
        self.poll_interval = poll_interval
        self._consecutive_failures = 0
        self._task: asyncio.Task | None = None

    async def poll_once(self) -> None:
        """Execute a single poll cycle: fetch -> persist -> broadcast -> cleanup."""
        try:
            async with SolanaClient(
                rpc_url=settings.solana_rpc_url,
                helius_api_key=settings.helius_api_key,
            ) as client:
                transactions = await client.get_recent_large_transactions(
                    min_amount_usd=10000, limit=200,
                )
        except Exception as e:
            logger.warning(f"Whale poller: Helius fetch failed: {e}")
            self._record_failure()
            return

        if not transactions:
            self._record_success()
            await self._db.cleanup_old_whale_transactions(hours=24)
            return

        try:
            new_sigs = await self._db.insert_whale_transactions(transactions)
        except Exception as e:
            logger.error(f"Whale poller: DB insert failed: {e}")
            self._record_failure()
            return

        # Broadcast only genuinely new transactions
        new_sig_set = set(new_sigs)
        for tx in transactions:
            if tx.get("signature") in new_sig_set:
                await self._stream_hub.publish(TOPIC, {
                    "signature": tx.get("signature"),
                    "wallet_address": tx.get("wallet_address", ""),
                    "wallet_label": tx.get("wallet_label"),
                    "token_address": tx.get("token_address", ""),
                    "token_symbol": tx.get("token_symbol", "???"),
                    "token_name": tx.get("token_name", "Unknown"),
                    "direction": "inflow" if tx.get("type", "buy") == "buy" else "outflow",
                    "amount_usd": float(tx.get("amount_usd", 0)),
                    "amount_tokens": float(tx.get("amount_tokens", 0)),
                    "price_usd": float(tx.get("price_usd", 0)),
                    "dex_name": tx.get("dex_name", "Unknown"),
                    "timestamp": tx.get("timestamp", ""),
                    "chain": "solana",
                })

        self._record_success()
        await self._db.cleanup_old_whale_transactions(hours=24)
        if new_sigs:
            logger.info(f"Whale poller: {len(new_sigs)} new transactions persisted")

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            self.poll_interval = BACKOFF_INTERVAL
            logger.warning(f"Whale poller: circuit breaker open, backing off to {BACKOFF_INTERVAL}s")

    def _record_success(self):
        self._consecutive_failures = 0
        self.poll_interval = self._base_interval

    async def run_forever(self) -> None:
        """Main loop - runs until cancelled."""
        logger.info(f"Whale poller started (interval={self.poll_interval}s)")
        while True:
            await self.poll_once()
            await asyncio.sleep(self.poll_interval)
