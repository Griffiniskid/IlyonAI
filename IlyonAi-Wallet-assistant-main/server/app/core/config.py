from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Map of provider name → API key, e.g. '{"openai": "sk-...", "anthropic": "sk-ant-..."}'
    api_keys: dict[str, str] = Field(default_factory=dict)

    # Map of chain_id (str) → RPC URL, e.g. '{"1": "https://mainnet.infura.io/...", "137": "..."}'
    rpc_urls: dict[str, str] = Field(default_factory=dict)

    enso_api_key: str = ""
    platform_fee_wallet_evm: str = ""
    debridge_referral_code: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # pydantic-settings parses dict fields from JSON env var values
        extra="ignore",
    )


settings = Settings()
