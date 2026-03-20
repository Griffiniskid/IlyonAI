from collections import Counter, defaultdict
from typing import Any, Dict, Iterable

from src.analytics.time_series import calculate_repeat_wallet_share
from src.smart_money.models import CanonicalFlowEvent


class EVMBehaviorAdapter:
    def adapt(
        self, transactions: Iterable[Dict[str, Any] | CanonicalFlowEvent]
    ) -> Dict[str, Dict[str, float]]:
        txs = list(transactions)
        if not txs:
            return {
                "whale_summary": {
                    "net_flow_usd": 0.0,
                    "buy_count": 0,
                    "sell_count": 0,
                    "repeat_wallet_share": 0.0,
                },
                "concentration": {"top_wallet_share": 0.0},
            }

        buy_count = 0
        sell_count = 0
        net_flow = 0.0
        wallet_totals = defaultdict(float)
        wallet_counts: Counter[str] = Counter()
        total_abs_amount = 0.0
        wallets: list[str] = []

        for tx in txs:
            if isinstance(tx, CanonicalFlowEvent):
                payload = tx.payload
                amount = float(payload.get("amount_usd", 0.0) or 0.0)
                wallet = str(tx.wallet or payload.get("wallet") or payload.get("wallet_address") or "")
                tx_type = tx.event_type.lower()
            else:
                amount = float(tx.get("amount_usd", 0.0) or 0.0)
                wallet = str(tx.get("wallet_address") or tx.get("wallet") or "")
                tx_type = str(tx.get("type") or "buy").lower()

            if tx_type == "sell":
                sell_count += 1
                net_flow -= amount
            else:
                buy_count += 1
                net_flow += amount

            if wallet:
                wallet_totals[wallet] += abs(amount)
                wallet_counts[wallet] += 1
                wallets.append(wallet)
            total_abs_amount += abs(amount)

        top_wallet_share = (max(wallet_totals.values()) / total_abs_amount) if (wallet_totals and total_abs_amount) else 0.0
        repeat_wallet_share = calculate_repeat_wallet_share(wallets)

        return {
            "whale_summary": {
                "net_flow_usd": net_flow,
                "buy_count": buy_count,
                "sell_count": sell_count,
                "repeat_wallet_share": repeat_wallet_share,
            },
            "concentration": {
                "top_wallet_share": top_wallet_share,
            },
        }
