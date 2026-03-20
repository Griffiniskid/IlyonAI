def test_event_contract_contains_trace_and_freshness_fields():
    from src.platform.contracts import EventEnvelope

    event = EventEnvelope(
        event_id="evt-1",
        event_type="analysis.progress",
        trace_id="tr-1",
        occurred_at="2026-03-19T00:00:00Z",
        payload={"stage": "scan"},
        freshness={"age_seconds": 0},
    )
    assert event.trace_id == "tr-1"
    assert event.payload["stage"] == "scan"
    assert event.freshness["age_seconds"] == 0


def test_event_contract_rejects_invalid_occurred_at_timestamp():
    from src.platform.contracts import EventEnvelope

    try:
        EventEnvelope(
            event_id="evt-1",
            event_type="analysis.progress",
            trace_id="tr-1",
            occurred_at="not-a-timestamp",
            payload={"stage": "scan"},
            freshness={"age_seconds": 0},
        )
        raise AssertionError("Expected ValueError for invalid occurred_at")
    except ValueError as exc:
        assert "occurred_at" in str(exc)
