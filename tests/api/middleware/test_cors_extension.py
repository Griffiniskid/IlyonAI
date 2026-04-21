import pytest
from unittest.mock import MagicMock
from src.api.middleware.cors import get_cors_origin, _is_allowed_extension_origin
from src.config import settings


def test_extension_origin_allowed_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_CHROME_EXT", True)
    monkeypatch.setattr(settings, "ALLOWED_EXTENSION_IDS", "abc123,def456")
    req = MagicMock()
    req.path = "/api/v1/agent"
    req.headers = {"Origin": "chrome-extension://abc123"}
    assert get_cors_origin(req) == "chrome-extension://abc123"


def test_extension_origin_rejected_when_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_CHROME_EXT", False)
    req = MagicMock()
    req.path = "/api/v1/agent"
    req.headers = {"Origin": "chrome-extension://abc123"}
    result = get_cors_origin(req)
    assert not result.startswith("chrome-extension")


def test_moz_extension_origin(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_CHROME_EXT", True)
    monkeypatch.setattr(settings, "ALLOWED_EXTENSION_IDS", "xyz789")
    assert _is_allowed_extension_origin("moz-extension://xyz789") is True
    assert _is_allowed_extension_origin("moz-extension://unknown") is False


def test_unknown_extension_scheme_rejected(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_CHROME_EXT", True)
    monkeypatch.setattr(settings, "ALLOWED_EXTENSION_IDS", "abc")
    assert _is_allowed_extension_origin("https://evil.com") is False
