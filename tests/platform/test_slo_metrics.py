import json

from scripts.perf.run_slo_probe import parse_threshold_assertion, probe_slo_metrics, run


def test_probe_slo_metrics_exposes_expected_metrics():
    metrics = probe_slo_metrics(window_hours=24)

    assert "first_meaningful_p95_ms" in metrics
    assert "deep_analysis_p95_ms" in metrics
    assert "critical_alert_delivery_p95_ms" in metrics
    assert "route_transition_p95_ms" in metrics


def test_threshold_assertion_parser_supports_less_than_contract():
    parsed = parse_threshold_assertion("first_meaningful_p95_ms<5000")

    assert parsed.metric == "first_meaningful_p95_ms"
    assert parsed.op == "<"
    assert parsed.target == 5000.0


def test_run_emits_json_report_with_contract_shape(capsys):
    exit_code = run(window_hours=24, assertions=["route_transition_p95_ms<1500"])
    assert exit_code == 0

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["window_hours"] == 24
    assert isinstance(report["metrics"], dict)
    assert report["pass"] is True
    assert isinstance(report["assertions"], list)
    assert report["assertions"][0]["assertion"] == "route_transition_p95_ms<1500"


def test_run_handles_malformed_assertion_without_traceback(capsys):
    exit_code = run(window_hours=24, assertions=["badassert"])
    assert exit_code == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["pass"] is False
    assert report["assertions"] == []
    assert len(report["failures"]) == 1
    assert report["failures"][0]["assertion"] == "badassert"
    assert "missing comparator" in report["failures"][0]["detail"]


def test_run_reports_unknown_metric_as_failed_assertion(capsys):
    exit_code = run(window_hours=24, assertions=["unknown_metric_p95_ms<10"])
    assert exit_code == 1

    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert report["pass"] is False
    assert report["assertions"][0]["passed"] is False
    assert report["assertions"][0]["detail"] == "missing metric: unknown_metric_p95_ms"
    assert report["failures"] == [
        {
            "assertion": "unknown_metric_p95_ms<10",
            "detail": "missing metric: unknown_metric_p95_ms",
        }
    ]
