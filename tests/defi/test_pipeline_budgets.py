import pytest
from pydantic import ValidationError

from src.config import Settings
from src.defi.pipeline.budgets import ProviderBudget, get_provider_budget


def test_provider_budget_uses_runtime_settings_defaults():
    config = Settings(
        defi_provider_timeout_seconds=11,
        defi_provider_concurrency_limit=3,
    )

    budget = get_provider_budget("openrouter", config)

    assert budget == ProviderBudget(timeout_seconds=11, concurrency_limit=3)


def test_defi_budget_settings_reject_nonsensical_values():
    with pytest.raises(ValidationError):
        Settings(defi_provider_concurrency_limit=0)
