"""Shared helpers for parsing wallet-assistant builder JSON responses."""
from __future__ import annotations

import json
import re
from typing import Any


class AssistantError(RuntimeError):
    """Raised when an assistant response cannot be parsed or contains an error."""


_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)


def parse_assistant_json(raw: Any) -> dict:
    """Parse a wallet-assistant builder JSON response.

    Accepts a dict (pass-through), str (JSON parse), or any other type.
    Strips prose prefixes/suffixes and extracts the first JSON object found.

    Raises:
        AssistantError: If the response is empty, no JSON object is found,
            the parsed JSON has an "error" key, or the result is not a dict.
    """
    if raw is None:
        raise AssistantError("Response is empty")

    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            raise AssistantError("Response is empty")

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            match = _JSON_OBJECT_RE.search(stripped)
            if not match:
                raise AssistantError("No JSON object found in response")
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                raise AssistantError("No JSON object found in response")
    else:
        # Non-dict, non-str types are parsed as JSON if possible
        try:
            parsed = json.loads(json.dumps(raw))
        except (TypeError, ValueError):
            raise AssistantError("Response is not a valid JSON dict")

    if not isinstance(parsed, dict):
        raise AssistantError("Parsed JSON is not a dict")

    if "error" in parsed:
        raise AssistantError(f"Assistant returned error: {parsed['error']}")

    return parsed
