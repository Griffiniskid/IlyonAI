from src.defi.execution.executability_oracle import classify_plan, SOFT_BLOCKERS


def test_ready_is_executable():
    assert classify_plan({"status": "ready", "blockers": []}) == (True, None)


def test_soft_balance_blocker_is_executable():
    plan = {"status": "blocked", "blockers": [{"code": "INSUFFICIENT_BALANCE"}]}
    ok, reason = classify_plan(plan)
    assert ok is True and reason is None


def test_mixed_soft_blockers_executable():
    plan = {"status": "blocked", "blockers": [{"code": "INSUFFICIENT_BALANCE"}, {"code": "SIM_STALE"}]}
    assert classify_plan(plan)[0] is True


def test_hard_adapter_failure_not_executable():
    plan = {"status": "blocked", "blockers": [{"code": "ADAPTER_BUILD_FAILED"}]}
    ok, reason = classify_plan(plan)
    assert ok is False and "ADAPTER_BUILD_FAILED" in reason


def test_hard_mixed_with_soft_not_executable():
    plan = {"status": "blocked", "blockers": [{"code": "INSUFFICIENT_BALANCE"}, {"code": "UNSUPPORTED_ADAPTER"}]}
    assert classify_plan(plan)[0] is False


def test_no_card_not_executable():
    assert classify_plan(None)[0] is False


def test_soft_set_membership():
    assert "INSUFFICIENT_BALANCE" in SOFT_BLOCKERS
    assert "ADAPTER_BUILD_FAILED" not in SOFT_BLOCKERS
