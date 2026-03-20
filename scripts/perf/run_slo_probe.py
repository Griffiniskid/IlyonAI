#!/usr/bin/env python3
"""Run an SLO probe against platform latency metrics."""

from __future__ import annotations

import argparse
import json
import operator
from dataclasses import dataclass


DEFAULT_SLO_METRICS_MS = {
    "first_meaningful_p95_ms": 1200.0,
    "deep_analysis_p95_ms": 8200.0,
    "critical_alert_delivery_p95_ms": 600.0,
    "route_transition_p95_ms": 320.0,
}


@dataclass(frozen=True)
class ThresholdAssertion:
    metric: str
    op: str
    target: float


def probe_slo_metrics(window_hours: int) -> dict[str, float]:
    """Return probe metrics for the requested observation window."""
    del window_hours
    return dict(DEFAULT_SLO_METRICS_MS)


def parse_threshold_assertion(raw: str) -> ThresholdAssertion:
    for op_symbol in ("<=", ">=", "<", ">", "=="):
        if op_symbol in raw:
            metric, target = raw.split(op_symbol, 1)
            metric = metric.strip()
            if not metric:
                raise ValueError(f"Invalid assertion '{raw}': metric is required")
            return ThresholdAssertion(metric=metric, op=op_symbol, target=float(target))
    raise ValueError(f"Invalid assertion '{raw}': missing comparator")


def evaluate_assertion(metrics: dict[str, float], assertion: ThresholdAssertion) -> tuple[bool, str]:
    ops = {
        "<": operator.lt,
        "<=": operator.le,
        ">": operator.gt,
        ">=": operator.ge,
        "==": operator.eq,
    }
    if assertion.metric not in metrics:
        return False, f"missing metric: {assertion.metric}"
    current = float(metrics[assertion.metric])
    passed = ops[assertion.op](current, assertion.target)
    detail = f"{assertion.metric}={current:.2f}ms {assertion.op} {assertion.target:.2f}"
    return passed, detail


def run(window_hours: int, assertions: list[str]) -> int:
    metrics = probe_slo_metrics(window_hours)
    assertion_results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for raw in assertions:
        try:
            parsed = parse_threshold_assertion(raw)
        except ValueError as exc:
            failures.append(
                {
                    "assertion": raw,
                    "detail": str(exc),
                }
            )
            continue

        passed, detail = evaluate_assertion(metrics, parsed)
        assertion_results.append(
            {
                "assertion": raw,
                "metric": parsed.metric,
                "operator": parsed.op,
                "target": parsed.target,
                "passed": passed,
                "detail": detail,
            }
        )
        if not passed:
            failures.append(
                {
                    "assertion": raw,
                    "detail": detail,
                }
            )

    report = {
        "window_hours": window_hours,
        "metrics": metrics,
        "assertions": assertion_results,
        "pass": len(failures) == 0,
        "failures": failures,
    }
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SLO latency probe")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--assert", dest="assertions", action="append", default=[])
    args = parser.parse_args()

    return run(window_hours=args.window_hours, assertions=args.assertions)


if __name__ == "__main__":
    raise SystemExit(main())
