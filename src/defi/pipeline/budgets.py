from dataclasses import dataclass

from src.config import Settings, settings


@dataclass(slots=True, frozen=True)
class ProviderBudget:
    timeout_seconds: int
    concurrency_limit: int


def get_provider_budget(provider: str, config: Settings = settings) -> ProviderBudget:
    return ProviderBudget(
        timeout_seconds=config.defi_provider_timeout_seconds,
        concurrency_limit=config.defi_provider_concurrency_limit,
    )
