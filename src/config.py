"""
Centralized configuration management using Pydantic Settings.
All environment variables and application settings are defined here.

Ilyon AI is a multi-chain DeFi intelligence platform supporting
Ethereum, Solana, Base, Arbitrum, BSC, Polygon, Optimism, and Avalanche.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Optional, Dict, Any, ClassVar




class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Ilyon AI is a multi-chain DeFi intelligence platform.
    Supports EVM chains (Ethereum, Base, Arbitrum, BSC, Polygon, Optimism, Avalanche)
    and Solana.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # AI PROVIDERS CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    # Grok (xAI) - For Twitter/Narrative Analysis
    grok_api_key: Optional[str] = Field(None, env="GROK_API_KEY")
    grok_model: str = Field("grok-4.1-fast", env="GROK_MODEL", description="Grok model for narrative analysis")

    # OpenRouter (required for all non-Grok AI analysis)
    openrouter_api_key: Optional[str] = Field(None, env="OPENROUTER_API_KEY")
    ai_model: str = Field("nvidia/nemotron-3-super-120b-a12b:free", env="AI_MODEL", description="Default OpenRouter model for all non-Grok AI analysis")

    # Legacy OpenAI direct config (deprecated, kept for env compatibility only)
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    openai_model: str = Field("nvidia/nemotron-3-super-120b-a12b:free", env="OPENAI_MODEL")
    openai_mini_model: str = Field("nvidia/nemotron-3-super-120b-a12b:free", env="OPENAI_MINI_MODEL")

    # ═══════════════════════════════════════════════════════════════════════════
    # BLOCKCHAIN CONFIGURATION - MULTI-CHAIN
    # ═══════════════════════════════════════════════════════════════════════════

    # Solana
    solana_rpc_url: str = Field(
        "https://api.mainnet-beta.solana.com",
        env="SOLANA_RPC_URL",
        description="Solana RPC endpoint (use Helius for production)"
    )
    helius_api_key: Optional[str] = Field(None, env="HELIUS_API_KEY")

    # EVM Chains
    ethereum_rpc_url: str = Field(
        "https://eth.llamarpc.com",
        env="ETHEREUM_RPC_URL",
        description="Ethereum mainnet RPC endpoint"
    )
    base_rpc_url: str = Field(
        "https://mainnet.base.org",
        env="BASE_RPC_URL",
        description="Base mainnet RPC endpoint"
    )
    arbitrum_rpc_url: str = Field(
        "https://arb1.arbitrum.io/rpc",
        env="ARBITRUM_RPC_URL",
        description="Arbitrum One RPC endpoint"
    )
    bsc_rpc_url: str = Field(
        "https://bsc-dataseed.binance.org",
        env="BSC_RPC_URL",
        description="BNB Smart Chain RPC endpoint"
    )
    polygon_rpc_url: str = Field(
        "https://polygon-rpc.com",
        env="POLYGON_RPC_URL",
        description="Polygon mainnet RPC endpoint"
    )
    optimism_rpc_url: str = Field(
        "https://mainnet.optimism.io",
        env="OPTIMISM_RPC_URL",
        description="Optimism mainnet RPC endpoint"
    )
    avalanche_rpc_url: str = Field(
        "https://api.avax.network/ext/bc/C/rpc",
        env="AVALANCHE_RPC_URL",
        description="Avalanche C-Chain RPC endpoint"
    )

    # Block Explorer API Keys (Etherscan family)
    etherscan_api_key: Optional[str] = Field(None, env="ETHERSCAN_API_KEY")
    bscscan_api_key: Optional[str] = Field(None, env="BSCSCAN_API_KEY")
    arbiscan_api_key: Optional[str] = Field(None, env="ARBISCAN_API_KEY")
    polygonscan_api_key: Optional[str] = Field(None, env="POLYGONSCAN_API_KEY")
    basescan_api_key: Optional[str] = Field(None, env="BASESCAN_API_KEY")
    optimism_etherscan_api_key: Optional[str] = Field(None, env="OPTIMISM_ETHERSCAN_API_KEY")
    snowtrace_api_key: Optional[str] = Field(None, env="SNOWTRACE_API_KEY")

    # GoPlus Security API (multi-chain token security)
    goplus_api_key: Optional[str] = Field(None, env="GOPLUS_API_KEY")

    # Portfolio / Wallet Indexer
    moralis_api_key: Optional[str] = Field(None, env="MORALIS_API_KEY", description="Moralis API key for EVM portfolio tracking")
    portfolio_required_chains: list[str] = Field(
        default_factory=lambda: [
            "solana",
            "ethereum",
            "base",
            "arbitrum",
            "bsc",
            "polygon",
            "optimism",
            "avalanche",
        ],
        description="Required chain matrix for portfolio parity responses",
    )

    # Default chain for analysis
    default_chain: str = Field("solana", env="DEFAULT_CHAIN", description="Default blockchain for analysis")

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
    jupiter_api_key: Optional[str] = Field(
        None,
        env="JUPITER_API_KEY",
        description="Jupiter API key (required as of Jan 31, 2026 - get from portal.jup.ag)"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # DATABASE & CACHING
    # ═══════════════════════════════════════════════════════════════════════════

    database_url: Optional[str] = Field(None, env="DATABASE_URL")
    redis_url: Optional[str] = Field(None, env="REDIS_URL")

    cache_ttl_seconds: int = Field(120, env="CACHE_TTL", description="Cache TTL in seconds")
    analysis_timeout_seconds: int = Field(30, env="ANALYSIS_TIMEOUT")
    defi_scan_limit: int = Field(48, ge=1, env="DEFI_SCAN_LIMIT")
    defi_top_band_limit: int = Field(12, ge=1, env="DEFI_TOP_BAND_LIMIT")
    defi_provider_timeout_seconds: int = Field(8, ge=1, env="DEFI_PROVIDER_TIMEOUT_SECONDS")
    defi_provider_concurrency_limit: int = Field(4, ge=1, env="DEFI_PROVIDER_CONCURRENCY_LIMIT")
    defi_analysis_ttl_seconds: int = Field(300, ge=1, env="DEFI_ANALYSIS_TTL_SECONDS")
    defi_score_model_version: str = Field("defi-v2", env="DEFI_SCORE_MODEL_VERSION")
    alert_dedupe_window_seconds: int = Field(300, env="ALERT_DEDUPE_WINDOW_SECONDS")

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

    # ═══════════════════════════════════════════════════════════════════════════
    # SOLANA ACTIONS / BLINKS CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    actions_base_url: str = Field(
        "https://api.ilyonai.io",
        env="ACTIONS_BASE_URL",
        description="Base URL for Solana Actions API (must be HTTPS in production)"
    )
    actions_api_port: int = Field(8080, env="ACTIONS_API_PORT", description="Port for Blinks API server")
    blinks_enabled: bool = Field(True, env="BLINKS_ENABLED", description="Enable/disable Blinks feature")
    blinks_rate_limit_per_minute: int = Field(30, env="BLINKS_RATE_LIMIT_PER_MINUTE")
    blinks_rate_limit_per_hour: int = Field(200, env="BLINKS_RATE_LIMIT_PER_HOUR")
    blink_ttl_hours: int = Field(168, env="BLINK_TTL_HOURS", description="Blink expiration time (0 = never)")

    # Web App URL (for redirects)
    webapp_url: str = Field(
        "http://localhost:3000",
        env="WEBAPP_URL",
        description="Public URL of the web application"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # WEB API CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    web_api_port: int = Field(8080, env="WEB_API_PORT", description="Port for Web API server")
    web_api_host: str = Field("0.0.0.0", env="WEB_API_HOST", description="Host for Web API server")

    # CORS settings for web frontend
    cors_origins: str = Field(
        "http://localhost:3000,http://localhost:3001,https://ilyonai.com,https://www.ilyonai.com,https://staging.ilyonai.com",
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
    scope_burst_limit_per_minute: int = Field(6, env="SCOPE_BURST_LIMIT_PER_MINUTE")

    # Webhook/replay security settings
    webhook_signing_secret: str = Field("", env="WEBHOOK_SIGNING_SECRET")
    replay_guard_ttl_seconds: int = Field(60, env="REPLAY_GUARD_TTL_SECONDS")
    replay_guard_max_skew_seconds: int = Field(30, env="REPLAY_GUARD_MAX_SKEW_SECONDS")

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
