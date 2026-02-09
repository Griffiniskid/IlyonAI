#!/usr/bin/env python3
"""
Command-line interface for log analysis.

Usage:
    python -m src.logging.utils.cli stats      # Show statistics
    python -m src.logging.utils.cli errors     # Show recent errors
    python -m src.logging.utils.cli cost       # Show cost analysis
    python -m src.logging.utils.cli tail       # Tail JSON logs
"""

import sys
import argparse
import json
from pathlib import Path
from src.logging.utils.analyzer import LogAnalyzer


def cmd_stats(args):
    """Show log statistics."""
    analyzer = LogAnalyzer(args.log_file)
    analyzer.print_summary()


def cmd_errors(args):
    """Show recent errors."""
    analyzer = LogAnalyzer(args.log_file)
    analyzer.load_logs(limit=args.limit)

    error_summary = analyzer.get_error_summary()

    print("\n" + "="*70)
    print("RECENT ERRORS")
    print("="*70 + "\n")

    for error in error_summary.get('recent_errors', []):
        print(f"⏰ {error['timestamp']}")
        print(f"📦 Logger: {error['logger']}")
        print(f"🔴 {error['error_type']}: {error['message']}")
        print(f"💥 Exit Code: {error['exit_code']}")
        print("-" * 70)


def cmd_cost(args):
    """Show cost analysis."""
    analyzer = LogAnalyzer(args.log_file)
    analyzer.load_logs()

    cost_analysis = analyzer.get_cost_analysis(hours=args.hours)

    print("\n" + "="*70)
    print(f"AI COST ANALYSIS (Last {args.hours} hours)")
    print("="*70 + "\n")

    if "error" in cost_analysis:
        print(f"❌ {cost_analysis['error']}")
        return

    print(f"💰 Total Cost: ${cost_analysis['total_cost_usd']:.6f}\n")
    print("Breakdown by Provider/Model:")
    print("-" * 70)

    for model, data in cost_analysis.get('breakdown', {}).items():
        print(f"\n📊 {model}:")
        print(f"   Cost: ${data['cost_usd']:.6f}")
        print(f"   Tokens: {data['tokens']:,}")
        print(f"   Requests: {data['requests']}")
        print(f"   Cost/Request: ${data['cost_per_request']:.6f}")


def cmd_tail(args):
    """Tail JSON logs."""
    analyzer = LogAnalyzer(args.log_file)
    analyzer.load_logs(limit=args.limit)

    print("\n" + "="*70)
    print(f"RECENT LOG ENTRIES (Last {args.limit})")
    print("="*70 + "\n")

    recent_logs = analyzer.get_recent_logs(level=args.level, limit=args.limit)

    for log in recent_logs:
        timestamp = log.get('timestamp', 'N/A')
        level = log.get('level', 'INFO')
        logger = log.get('logger', 'unknown')
        message = log.get('message', '')

        # Color codes
        colors = {
            'DEBUG': '\033[36m',
            'INFO': '\033[32m',
            'WARNING': '\033[33m',
            'ERROR': '\033[31m',
            'CRITICAL': '\033[35m'
        }
        color = colors.get(level, '')
        reset = '\033[0m'

        print(f"{color}{timestamp} | {level:8} | {logger:30} | {message}{reset}")

        # Show extra context if available
        if 'ai_metadata' in log:
            meta = log['ai_metadata']
            print(f"  → Tokens: {meta.get('tokens_total', 0)} | Latency: {meta.get('latency_ms', 0)}ms | Cost: ${meta.get('cost_usd', 0):.4f}")

        if 'exit_code' in log:
            print(f"  → Exit Code: {log['exit_code']}")

        print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Ilyon AI Log Analysis CLI")
    parser.add_argument('--log-file', default='logs/ilyon_ai.json', help='Path to JSON log file')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Stats command
    subparsers.add_parser('stats', help='Show log statistics and summary')

    # Errors command
    parser_errors = subparsers.add_parser('errors', help='Show recent errors')
    parser_errors.add_argument('--limit', type=int, default=1000, help='Number of logs to analyze')

    # Cost command
    parser_cost = subparsers.add_parser('cost', help='Show AI cost analysis')
    parser_cost.add_argument('--hours', type=int, default=24, help='Time period in hours')

    # Tail command
    parser_tail = subparsers.add_parser('tail', help='Tail recent log entries')
    parser_tail.add_argument('--limit', type=int, default=20, help='Number of entries to show')
    parser_tail.add_argument('--level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help='Filter by log level')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    commands = {
        'stats': cmd_stats,
        'errors': cmd_errors,
        'cost': cmd_cost,
        'tail': cmd_tail
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        try:
            cmd_func(args)
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            sys.exit(1)


if __name__ == '__main__':
    main()
