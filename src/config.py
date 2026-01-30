"""
Centralized configuration management using Pydantic Settings.
All environment variables and application settings are defined here.

NOTE: AI Sentinel is exclusively designed for Solana blockchain analysis.
All configurations are Solana-specific - no multi-chain support.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional, Dict, Any, ClassVar




class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    AI Sentinel is a Solana-exclusive token analysis platform.
    All blockchain settings are for Solana mainnet only.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # TELEGRAM CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    bot_token: str = Field(..., env="BOT_TOKEN", description="Telegram Bot API token")

    # Access control - whitelist of allowed Telegram IDs (comma-separated)
    # Field name matches env var: ALLOWED_USERS
    allowed_users: str = Field(default="")

    def get_allowed_user_ids(self) -> list[int]:
        """Parse comma-separated Telegram IDs from env var"""
        if not self.allowed_users or not self.allowed_users.strip():
            return []
        # Remove quotes if present and split by comma
        raw = self.allowed_users.strip().strip('"').strip("'")
        return [int(id.strip()) for id in raw.split(",") if id.strip()]

    # ═══════════════════════════════════════════════════════════════════════════
    # AI PROVIDERS CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    # OpenRouter (currently used)
    openrouter_api_key: Optional[str] = Field(None, env="OPENROUTER_API_KEY")
    ai_model: str = Field("openai/gpt-4o-mini", env="AI_MODEL", description="Default AI model")

    # OpenAI (direct)
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    openai_mini_model: str = Field("gpt-4o-mini", env="OPENAI_MINI_MODEL")

    # ═══════════════════════════════════════════════════════════════════════════
    # SOLANA BLOCKCHAIN CONFIGURATION (SOLANA ONLY - NO MULTI-CHAIN SUPPORT)
    # ═══════════════════════════════════════════════════════════════════════════

    solana_rpc_url: str = Field(
        "https://api.mainnet-beta.solana.com",
        env="SOLANA_RPC_URL",
        description="Solana RPC endpoint (use Helius for production)"
    )
    helius_api_key: Optional[str] = Field(None, env="HELIUS_API_KEY")

    # ═══════════════════════════════════════════════════════════════════════════
    # HONEYPOT DETECTION CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    honeypot_simulation_amount_sol: float = Field(
        0.1,
        env="HONEYPOT_SIMULATION_SOL",
        description="SOL equivalent to simulate selling for honeypot detection"
    )
    honeypot_high_tax_threshold: float = Field(
        20.0,
        env="HONEYPOT_HIGH_TAX_THRESHOLD",
        description="Percentage above which sell tax is considered high"
    )
    honeypot_extreme_tax_threshold: float = Field(
        50.0,
        env="HONEYPOT_EXTREME_TAX_THRESHOLD",
        description="Percentage above which sell tax is considered extreme"
    )
    jupiter_api_timeout: int = Field(
        15,
        env="JUPITER_API_TIMEOUT",
        description="Timeout for Jupiter API requests in seconds"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # DATABASE & CACHING
    # ═══════════════════════════════════════════════════════════════════════════

    database_url: Optional[str] = Field(None, env="DATABASE_URL")
    redis_url: Optional[str] = Field(None, env="REDIS_URL")

    cache_ttl_seconds: int = Field(120, env="CACHE_TTL", description="Cache TTL in seconds")
    analysis_timeout_seconds: int = Field(30, env="ANALYSIS_TIMEOUT")

    # ═══════════════════════════════════════════════════════════════════════════
    # AFFILIATE CONFIGURATION - TROJAN BOT ONLY
    # ═══════════════════════════════════════════════════════════════════════════
    # Trojan Bot: 25-35% lifetime commission
    # Link: https://t.me/solana_trojanbot
    # ═══════════════════════════════════════════════════════════════════════════

    trojan_ref_code: str = Field("", env="TROJAN_REF", description="Trojan Bot referral code")

    # ═══════════════════════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════════════════════

    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(None, env="LOG_FILE", description="Log file path for production")

    # Advanced logging configuration
    log_max_bytes: int = Field(10 * 1024 * 1024, env="LOG_MAX_BYTES", description="Max log file size before rotation (10MB)")
    log_backup_count: int = Field(5, env="LOG_BACKUP_COUNT", description="Number of backup log files to keep")
    log_ai_full_responses: bool = Field(True, env="LOG_AI_FULL_RESPONSES", description="Log full AI responses")
    log_redact_sensitive: bool = Field(True, env="LOG_REDACT_SENSITIVE", description="Redact sensitive data (API keys, tokens)")

    # ═══════════════════════════════════════════════════════════════════════════
    # WEBHOOK CONFIGURATION (PRODUCTION)
    # ═══════════════════════════════════════════════════════════════════════════

    webhook_url: Optional[str] = Field(None, env="WEBHOOK_URL", description="Webhook URL for production")
    webhook_secret: Optional[str] = Field(None, env="WEBHOOK_SECRET", description="Webhook secret token")
    webhook_port: int = Field(8443, env="WEBHOOK_PORT", description="Webhook server port")

    # ═══════════════════════════════════════════════════════════════════════════
    # SOLANA ACTIONS / BLINKS CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    actions_base_url: str = Field(
        "https://api.aisentinel.io",
        env="ACTIONS_BASE_URL",
        description="Base URL for Solana Actions API (must be HTTPS in production)"
    )
    actions_api_port: int = Field(8080, env="ACTIONS_API_PORT", description="Port for Blinks API server")
    blinks_enabled: bool = Field(True, env="BLINKS_ENABLED", description="Enable/disable Blinks feature")
    blinks_rate_limit_per_minute: int = Field(30, env="BLINKS_RATE_LIMIT_PER_MINUTE")
    blinks_rate_limit_per_hour: int = Field(200, env="BLINKS_RATE_LIMIT_PER_HOUR")
    blink_ttl_hours: int = Field(168, env="BLINK_TTL_HOURS", description="Blink expiration time (0 = never)")

    # ═══════════════════════════════════════════════════════════════════════════
    # WEB API CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    web_api_port: int = Field(8080, env="WEB_API_PORT", description="Port for Web API server")
    web_api_host: str = Field("0.0.0.0", env="WEB_API_HOST", description="Host for Web API server")

    # CORS settings for web frontend
    cors_origins: str = Field(
        "http://localhost:3000,http://localhost:3001,https://aisentinel.io,https://www.aisentinel.io",
        env="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins"
    )

    def get_cors_origins(self) -> list[str]:
        """Parse comma-separated CORS origins"""
        if not self.cors_origins:
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Web API rate limiting
    web_api_rate_limit_per_minute: int = Field(60, env="WEB_API_RATE_LIMIT_PER_MINUTE")
    web_api_rate_limit_per_hour: int = Field(500, env="WEB_API_RATE_LIMIT_PER_HOUR")

    # Session settings
    session_secret: str = Field(
        "change-me-in-production-use-random-string",
        env="SESSION_SECRET",
        description="Secret key for session encryption"
    )
    session_ttl_hours: int = Field(24, env="SESSION_TTL_HOURS", description="Session TTL in hours")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env file

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPUTED PROPERTIES & HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════════════
    # TROJAN BOT AFFILIATE HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    TROJAN_BOT_URL: ClassVar[str] = "https://t.me/solana_trojanbot"
    TROJAN_LINK_TEMPLATE: ClassVar[str] = "https://t.me/solana_trojanbot?start=r-{ref}-{token}"

    def get_trojan_link(self, token_address: str) -> str:
        """
        Generate Trojan Bot affiliate link with token address.

        Args:
            token_address: Solana token address

        Returns:
            Formatted Trojan affiliate link
        """
        if self.trojan_ref_code:
            return self.TROJAN_LINK_TEMPLATE.format(
                ref=self.trojan_ref_code,
                token=token_address
            )
        # Fallback to basic link without ref
        return f"{self.TROJAN_BOT_URL}?start={token_address}"

    def get_trojan_ref_link(self) -> str:
        """
        Get Trojan Bot referral link without token.

        Returns:
            Trojan affiliate base link
        """
        if self.trojan_ref_code:
            return f"{self.TROJAN_BOT_URL}?start=r-{self.trojan_ref_code}"
        return self.TROJAN_BOT_URL

    def get_primary_affiliate_link(self, token_address: str) -> str:
        """
        Get primary affiliate link (Trojan Bot).

        Args:
            token_address: Solana token address

        Returns:
            Trojan affiliate link
        """
        return self.get_trojan_link(token_address)


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL SETTINGS INSTANCE
# ═══════════════════════════════════════════════════════════════════════════

settings = Settings()
