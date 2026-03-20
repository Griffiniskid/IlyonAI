from scripts.perf.run_slo_probe import run


def test_slo_thresholds_pass_for_current_probe_defaults():
    exit_code = run(
        window_hours=24,
        assertions=[
            "first_meaningful_p95_ms<5000",
            "deep_analysis_p95_ms<30000",
            "critical_alert_delivery_p95_ms<5000",
            "route_transition_p95_ms<1500",
        ],
    )
    assert exit_code == 0


def test_slo_thresholds_fail_when_assertion_is_too_strict():
    exit_code = run(window_hours=24, assertions=["first_meaningful_p95_ms<100"])
    assert exit_code == 1
