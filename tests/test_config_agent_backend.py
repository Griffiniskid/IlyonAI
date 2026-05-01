"""Tests for Sentinel-Assistant Fusion configuration fields."""

import os
import pytest
from unittest.mock import patch

from src.config import Settings, settings


class TestAgentBackendConfig:
    """Test AGENT_BACKEND and related fusion configuration fields."""

    def test_agent_backend_default(self):
        """AGENT_BACKEND defaults to 'sentinel'."""
        s = Settings()
        assert s.AGENT_BACKEND == "sentinel"

    def test_agent_backend_from_env(self):
        """AGENT_BACKEND can be set via environment variable."""
        with patch.dict(os.environ, {"AGENT_BACKEND": "assistant"}, clear=False):
            s = Settings()
            assert s.AGENT_BACKEND == "assistant"

    def test_sentinel_api_target_default(self):
        """SENTINEL_API_TARGET defaults to 'http://localhost:8080'."""
        s = Settings()
        assert s.SENTINEL_API_TARGET == "http://localhost:8080"

    def test_sentinel_api_target_from_env(self):
        """SENTINEL_API_TARGET can be set via environment variable."""
        with patch.dict(os.environ, {"SENTINEL_API_TARGET": "http://sentinel:9000"}, clear=False):
            s = Settings()
            assert s.SENTINEL_API_TARGET == "http://sentinel:9000"

    def test_assistant_api_target_default(self):
        """ASSISTANT_API_TARGET defaults to 'http://localhost:8000'."""
        s = Settings()
        assert s.ASSISTANT_API_TARGET == "http://localhost:8000"

    def test_assistant_api_target_from_env(self):
        """ASSISTANT_API_TARGET can be set via environment variable."""
        with patch.dict(os.environ, {"ASSISTANT_API_TARGET": "http://assistant:9001"}, clear=False):
            s = Settings()
            assert s.ASSISTANT_API_TARGET == "http://assistant:9001"

    def test_optimizer_enabled_default(self):
        """OPTIMIZER_ENABLED defaults to False."""
        s = Settings()
        assert s.OPTIMIZER_ENABLED is False

    def test_optimizer_enabled_from_env(self):
        """OPTIMIZER_ENABLED can be set to True via environment variable."""
        with patch.dict(os.environ, {"OPTIMIZER_ENABLED": "true"}, clear=False):
            s = Settings()
            assert s.OPTIMIZER_ENABLED is True

    def test_optimizer_enabled_false_string(self):
        """OPTIMIZER_ENABLED handles 'false' string correctly."""
        with patch.dict(os.environ, {"OPTIMIZER_ENABLED": "false"}, clear=False):
            s = Settings()
            assert s.OPTIMIZER_ENABLED is False

    def test_fields_exist_on_global_settings(self):
        """All fusion fields exist on the global settings instance."""
        assert hasattr(settings, "AGENT_BACKEND")
        assert hasattr(settings, "SENTINEL_API_TARGET")
        assert hasattr(settings, "ASSISTANT_API_TARGET")
        assert hasattr(settings, "OPTIMIZER_ENABLED")

    def test_field_types(self):
        """All fusion fields have correct types."""
        s = Settings()
        assert isinstance(s.AGENT_BACKEND, str)
        assert isinstance(s.SENTINEL_API_TARGET, str)
        assert isinstance(s.ASSISTANT_API_TARGET, str)
        assert isinstance(s.OPTIMIZER_ENABLED, bool)
