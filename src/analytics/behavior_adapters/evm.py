from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List

from src.analytics.time_series import calculate_repeat_wallet_share


class EVMBehaviorAdapter:
    def adapt(self, transactions: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
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

        for tx in txs:
            amount = float(tx.get("amount_usd", 0.0) or 0.0)
            wallet = str(tx.get("wallet_address") or "")
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
            total_abs_amount += abs(amount)

        top_wallet_share = (max(wallet_totals.values()) / total_abs_amount) if total_abs_amount else 0.0
        repeat_wallet_share = calculate_repeat_wallet_share(
            [str(tx.get("wallet_address") or "") for tx in txs]
        )

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
