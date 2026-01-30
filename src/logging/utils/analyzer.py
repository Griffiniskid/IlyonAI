"""
Log analyzer for parsing and analyzing JSON logs.

Provides tools for:
- AI performance metrics
- Error analysis
- Cost tracking
- Provider comparison
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict, Counter
from datetime import datetime


logger = logging.getLogger(__name__)


class LogAnalyzer:
    """Analyzer for structured JSON logs."""

    def __init__(self, log_file: str = "logs/ai_sentinel.json"):
        """
        Initialize log analyzer.

        Args:
            log_file: Path to JSON log file
        """
        self.log_file = Path(log_file)
        self.logs: List[Dict[str, Any]] = []

    def load_logs(self, limit: Optional[int] = None) -> int:
        """
        Load logs from file.

        Args:
            limit: Maximum number of logs to load (newest first)

        Returns:
            Number of logs loaded
        """
        if not self.log_file.exists():
            logger.warning(f"Log file not found: {self.log_file}")
            return 0

        self.logs = []
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line.strip())
                    self.logs.append(log_entry)
                except json.JSONDecodeError:
                    continue

        # Reverse to get newest first
        self.logs.reverse()

        # Apply limit
        if limit:
            self.logs = self.logs[:limit]

        return len(self.logs)

    def get_ai_metrics(self) -> Dict[str, Any]:
        """
        Get AI performance metrics.

        Returns:
            Dictionary with AI metrics
        """
        ai_logs = [log for log in self.logs if log.get('logger', '').startswith('ai.')]

        if not ai_logs:
            return {"error": "No AI logs found"}

        # Group by provider
        by_provider = defaultdict(list)
        for log in ai_logs:
            provider = log.get('provider', 'unknown')
            by_provider[provider].append(log)

        metrics = {}
        for provider, logs in by_provider.items():
            # Calculate metrics
            total_requests = sum(1 for log in logs if 'ai_metadata' in log)
            total_tokens = sum(log.get('ai_metadata', {}).get('tokens_total', 0) for log in logs)
            total_cost = sum(log.get('ai_metadata', {}).get('cost_usd', 0) for log in logs)

            latencies = [log.get('latency_ms', 0) for log in logs if 'latency_ms' in log]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0

            # Success rate
            successes = sum(1 for log in logs if log.get('exit_code') == 0)
            success_rate = (successes / len(logs) * 100) if logs else 0

            metrics[provider] = {
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "success_rate": round(success_rate, 2),
                "error_count": len(logs) - successes
            }

        return metrics

    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get error frequency analysis.

        Returns:
            Dictionary with error statistics
        """
        error_logs = [log for log in self.logs if log.get('level') == 'ERROR']

        if not error_logs:
            return {"total_errors": 0, "message": "No errors found"}

        # Group by error type
        error_types = Counter(log.get('error_type', 'Unknown') for log in error_logs)

        # Group by logger
        by_logger = Counter(log.get('logger', 'unknown') for log in error_logs)

        # Group by exit code
        exit_codes = Counter(log.get('exit_code', -1) for log in error_logs)

        # Recent errors
        recent_errors = [
            {
                "timestamp": log.get('timestamp'),
                "logger": log.get('logger'),
                "error_type": log.get('error_type'),
                "message": log.get('message'),
                "exit_code": log.get('exit_code')
            }
            for log in error_logs[:10]
        ]

        return {
            "total_errors": len(error_logs),
            "error_types": dict(error_types.most_common(10)),
            "errors_by_logger": dict(by_logger.most_common(10)),
            "exit_codes": dict(exit_codes.most_common(10)),
            "recent_errors": recent_errors
        }

    def get_cost_analysis(self, hours: int = 24) -> Dict[str, Any]:
        """
        Calculate AI costs over time period.

        Args:
            hours: Time period in hours

        Returns:
            Cost breakdown by provider and model
        """
        ai_logs = [
            log for log in self.logs
            if log.get('logger', '').startswith('ai.') and 'ai_metadata' in log
        ]

        if not ai_logs:
            return {"error": "No AI cost data found"}

        # Group by provider and model
        costs = defaultdict(lambda: {"cost": 0, "tokens": 0, "requests": 0})

        for log in ai_logs:
            metadata = log.get('ai_metadata', {})
            provider = log.get('provider', 'unknown')
            model = metadata.get('model', 'unknown')
            key = f"{provider}/{model}"

            costs[key]["cost"] += metadata.get('cost_usd', 0)
            costs[key]["tokens"] += metadata.get('tokens_total', 0)
            costs[key]["requests"] += 1

        # Convert to regular dict and round
        cost_breakdown = {}
        total_cost = 0
        for key, data in costs.items():
            cost_breakdown[key] = {
                "cost_usd": round(data["cost"], 6),
                "tokens": data["tokens"],
                "requests": data["requests"],
                "cost_per_request": round(data["cost"] / data["requests"], 6) if data["requests"] > 0 else 0
            }
            total_cost += data["cost"]

        return {
            "total_cost_usd": round(total_cost, 6),
            "period_hours": hours,
            "breakdown": cost_breakdown
        }

    def get_provider_comparison(self) -> Dict[str, Any]:
        """
        Compare AI provider performance.

        Returns:
            Comparison metrics for all providers
        """
        ai_logs = [log for log in self.logs if log.get('logger', '').startswith('ai.')]

        if not ai_logs:
            return {"error": "No AI logs for comparison"}

        providers = {}

        for provider in ['openai', 'gemini', 'grok']:
            provider_logs = [log for log in ai_logs if log.get('provider') == provider]

            if not provider_logs:
                continue

            # Calculate metrics
            latencies = [log.get('latency_ms', 0) for log in provider_logs if 'latency_ms' in log]
            costs = [log.get('ai_metadata', {}).get('cost_usd', 0) for log in provider_logs]
            tokens = [log.get('ai_metadata', {}).get('tokens_total', 0) for log in provider_logs]

            successes = sum(1 for log in provider_logs if log.get('exit_code') == 0)

            providers[provider] = {
                "requests": len(provider_logs),
                "success_rate": round((successes / len(provider_logs) * 100), 2),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
                "total_cost_usd": round(sum(costs), 6),
                "total_tokens": sum(tokens),
                "avg_cost_per_request": round(sum(costs) / len(provider_logs), 6) if provider_logs else 0
            }

        return providers

    def get_recent_logs(self, level: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent log entries.

        Args:
            level: Filter by log level (INFO, WARNING, ERROR)
            limit: Number of entries to return

        Returns:
            List of log entries
        """
        logs = self.logs

        if level:
            logs = [log for log in logs if log.get('level') == level.upper()]

        return logs[:limit]

    def print_summary(self):
        """Print a summary of log analysis to console."""
        print("\n" + "="*70)
        print("AI SENTINEL LOG ANALYSIS SUMMARY")
        print("="*70 + "\n")

        # Load logs
        count = self.load_logs()
        print(f"📊 Loaded {count} log entries\n")

        # AI Metrics
        print("🤖 AI PERFORMANCE METRICS:")
        print("-" * 70)
        ai_metrics = self.get_ai_metrics()
        for provider, metrics in ai_metrics.items():
            if provider != "error":
                print(f"\n  {provider.upper()}:")
                for key, value in metrics.items():
                    print(f"    {key}: {value}")

        # Error Summary
        print("\n\n❌ ERROR SUMMARY:")
        print("-" * 70)
        error_summary = self.get_error_summary()
        print(f"  Total Errors: {error_summary.get('total_errors', 0)}")

        if error_summary.get('error_types'):
            print("\n  Top Error Types:")
            for error_type, count in list(error_summary['error_types'].items())[:5]:
                print(f"    {error_type}: {count}")

        # Cost Analysis
        print("\n\n💰 COST ANALYSIS:")
        print("-" * 70)
        cost_analysis = self.get_cost_analysis()
        if "error" not in cost_analysis:
            print(f"  Total Cost: ${cost_analysis.get('total_cost_usd', 0):.6f}")
            print("\n  Breakdown:")
            for model, data in cost_analysis.get('breakdown', {}).items():
                print(f"    {model}:")
                print(f"      Cost: ${data['cost_usd']:.6f}")
                print(f"      Requests: {data['requests']}")
                print(f"      Cost/Request: ${data['cost_per_request']:.6f}")

        print("\n" + "="*70 + "\n")
