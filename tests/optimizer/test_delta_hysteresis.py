from src.optimizer.delta import MoveCandidate, should_move


def test_should_move_requires_apy_sentinel_and_gas_thresholds():
    candidate = MoveCandidate(usd_value=10_000, apy_delta=2.5, sentinel_delta=3, estimated_gas_usd=20)

    assert should_move(candidate) is True


def test_should_not_move_when_safety_drops():
    candidate = MoveCandidate(usd_value=10_000, apy_delta=5.0, sentinel_delta=-1, estimated_gas_usd=20)

    assert should_move(candidate) is False
