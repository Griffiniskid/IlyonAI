"""Tests for _assistant_bridge.parse_assistant_json and AssistantError."""
from __future__ import annotations

import pytest

from src.agent.tools._assistant_bridge import AssistantError, parse_assistant_json


class TestAssistantError:
    def test_is_runtime_error_subclass(self):
        assert issubclass(AssistantError, RuntimeError)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(AssistantError, match="boom"):
            raise AssistantError("boom")


class TestParseAssistantJsonPassThrough:
    def test_dict_passes_through(self):
        raw = {"action": "swap", "amount": 100}
        assert parse_assistant_json(raw) == raw

    def test_list_is_rejected(self):
        with pytest.raises(AssistantError, match="not a dict"):
            parse_assistant_json([1, 2, 3])

    def test_none_is_rejected(self):
        with pytest.raises(AssistantError, match="empty"):
            parse_assistant_json(None)

    def test_empty_string_is_rejected(self):
        with pytest.raises(AssistantError, match="empty"):
            parse_assistant_json("")

    def test_whitespace_string_is_rejected(self):
        with pytest.raises(AssistantError, match="empty"):
            parse_assistant_json("   \n\t  ")


class TestParseAssistantJsonString:
    def test_valid_json_string(self):
        raw = '{"action": "swap", "amount": 100}'
        assert parse_assistant_json(raw) == {"action": "swap", "amount": 100}

    def test_json_with_prose_prefix(self):
        raw = 'Here is your JSON:\n{"action": "swap", "amount": 100}'
        assert parse_assistant_json(raw) == {"action": "swap", "amount": 100}

    def test_json_with_prose_suffix(self):
        raw = '{"action": "swap", "amount": 100}\nHope that helps!'
        assert parse_assistant_json(raw) == {"action": "swap", "amount": 100}

    def test_json_with_prose_both_sides(self):
        raw = 'Sure thing!\n{"action": "swap", "amount": 100}\nDone!'
        assert parse_assistant_json(raw) == {"action": "swap", "amount": 100}

    def test_no_json_object_found(self):
        raw = "I don't have any JSON for you."
        with pytest.raises(AssistantError, match="No JSON object"):
            parse_assistant_json(raw)

    def test_json_with_error_key(self):
        raw = '{"error": "invalid parameter"}'
        with pytest.raises(AssistantError, match="error"):
            parse_assistant_json(raw)

    def test_nested_json_in_prose(self):
        raw = '```json\n{"action": "swap", "amount": 100}\n```'
        assert parse_assistant_json(raw) == {"action": "swap", "amount": 100}

    def test_multiple_json_objects_takes_first(self):
        raw = '{"a": 1} and then {"b": 2}'
        assert parse_assistant_json(raw) == {"a": 1}


class TestParseAssistantJsonEdgeCases:
    def test_integer_is_rejected(self):
        with pytest.raises(AssistantError, match="not a dict"):
            parse_assistant_json(42)

    def test_boolean_is_rejected(self):
        with pytest.raises(AssistantError, match="not a dict"):
            parse_assistant_json(True)

    def test_json_array_string_is_rejected(self):
        with pytest.raises(AssistantError, match="not a dict"):
            parse_assistant_json('[1, 2, 3]')

    def test_json_primitive_string_is_rejected(self):
        with pytest.raises(AssistantError, match="not a dict"):
            parse_assistant_json('"hello"')

    def test_malformed_json_no_object(self):
        raw = "not { valid"
        with pytest.raises(AssistantError, match="No JSON object"):
            parse_assistant_json(raw)
