"""
AI Sentinel - Main entry point for the Telegram bot.

This module initializes and runs the bot with all its components.
Supports both polling (development) and webhook (production) modes.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import settings


# ═══════════════════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

def setup_logging() -> logging.Logger:
    """
    Configure advanced structured logging with dual output.

    Logging outputs:
    - Console: Human-readable colored logs with context
    - Text file: Standard logs with function names and line numbers
    - JSON file: Structured logs for parsing and analysis

    Features:
    - Automatic sensitive data redaction
    - Request tracing with trace IDs
    - Exit code tracking
    - AI metadata logging (tokens, costs, latency)
    """
    from src.logging.structured import JSONFormatter, HumanReadableFormatter
    from src.logging.filters import SensitiveDataFilter
    from src.logging.handlers import StructuredFileHandler

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    handlers = []

    # ═══════════════════════════════════════════════════════════════════════════
    # CONSOLE HANDLER - Human-readable with colors and context
    # ═══════════════════════════════════════════════════════════════════════════
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(HumanReadableFormatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    ))
    handlers.append(console_handler)

    # ═══════════════════════════════════════════════════════════════════════════
    # TEXT FILE HANDLER - Traditional logs with function names and line numbers
    # ═══════════════════════════════════════════════════════════════════════════
    if settings.log_file:
        text_handler = StructuredFileHandler(
            settings.log_file,
            maxBytes=getattr(settings, 'log_max_bytes', 10 * 1024 * 1024),
            backupCount=getattr(settings, 'log_backup_count', 5)
        )
        text_handler.setLevel(log_level)
        text_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        handlers.append(text_handler)

    # ═══════════════════════════════════════════════════════════════════════════
    # JSON FILE HANDLER - Structured logs for parsing and analysis
    # ═══════════════════════════════════════════════════════════════════════════
    json_handler = StructuredFileHandler(
        log_dir / "ai_sentinel.json",
        maxBytes=getattr(settings, 'log_max_bytes', 10 * 1024 * 1024),
        backupCount=getattr(settings, 'log_backup_count', 5)
    )
    json_handler.setLevel(log_level)
    json_handler.setFormatter(JSONFormatter())
    handlers.append(json_handler)

    # ═══════════════════════════════════════════════════════════════════════════
    # APPLY SENSITIVE DATA FILTER - Redact API keys, tokens, passwords
    # ═══════════════════════════════════════════════════════════════════════════
    redact_enabled = getattr(settings, 'log_redact_sensitive', True)
    sensitive_filter = SensitiveDataFilter(redact_enabled=redact_enabled)
    for handler in handlers:
        handler.addFilter(sensitive_filter)

    # ═══════════════════════════════════════════════════════════════════════════
    # CONFIGURE ROOT LOGGER
    # ═══════════════════════════════════════════════════════════════════════════
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True  # Override any existing configuration
    )

    # Set specific log levels for noisy libraries
    logging.getLogger('aiogram').setLevel(logging.INFO)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

    logger = logging.getLogger('AI_Sentinel')
    logger.info(f"✅ Advanced logging initialized (level: {settings.log_level})")

    if settings.log_file:
        logger.info(f"📝 Text log file: {settings.log_file}")

    logger.info(f"📊 JSON log file: {log_dir / 'ai_sentinel.json'}")
    logger.info(f"🔒 Sensitive data redaction: {'enabled' if redact_enabled else 'disabled'}")

    return logger


# ═══════════════════════════════════════════════════════════════════════════
# BOT INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

async def create_bot() -> tuple[Bot, Dispatcher]:
    """
    Create and configure the bot and dispatcher.

    Returns:
        Tuple of (Bot, Dispatcher) instances
    """
    # Create bot instance with HTML parsing
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        )
    )

    # Create dispatcher with memory storage
    dp = Dispatcher(storage=MemoryStorage())

    # Register access control middleware (check whitelist first)
    from src.bot.middleware.access_control import AccessControlMiddleware
    dp.message.middleware(AccessControlMiddleware())
    dp.callback_query.middleware(AccessControlMiddleware())

    # Register rate limiting middleware
    from src.bot.middleware.rate_limit import RateLimitMiddleware
    dp.message.middleware(RateLimitMiddleware())

    # Register all handlers
    from src.bot.handlers import start, analyze, commands, callbacks, export
    dp.include_router(start.router)
    dp.include_router(analyze.router)
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(export.router)

    return bot, dp


# ═══════════════════════════════════════════════════════════════════════════
# STARTUP & SHUTDOWN
# ═══════════════════════════════════════════════════════════════════════════

async def on_startup(bot: Bot, logger: logging.Logger):
    """Called when the bot starts"""
    bot_info = await bot.get_me()
    logger.info("═" * 70)
    logger.info("🛡️  AI SENTINEL BOT - Starting Up")
    logger.info("═" * 70)
    logger.info(f"Bot Username: @{bot_info.username}")
    logger.info(f"Bot ID: {bot_info.id}")

    # Determine mode
    mode = "Webhook" if settings.webhook_url else "Polling"
    logger.info(f"Mode: {mode}")
    logger.info("═" * 70)

    # Initialize database
    logger.info("💾 Initializing storage...")
    try:
        from src.storage.database import init_database
        db = await init_database()
        if db._initialized:
            logger.info("  ✅ Database connected")
        else:
            logger.warning("  ⚠️  Database not configured - using in-memory storage")
    except Exception as e:
        logger.warning(f"  ⚠️  Database initialization failed: {e}")

    # Initialize cache
    try:
        from src.storage.cache import init_cache
        cache = await init_cache()
        stats = await cache.get_stats()
        if stats.get("redis_connected"):
            logger.info("  ✅ Redis cache connected")
        else:
            logger.info("  ✅ In-memory cache active")
    except Exception as e:
        logger.warning(f"  ⚠️  Cache initialization failed: {e}")

    # Initialize AI clients
    logger.info("🤖 Initializing AI providers...")

    from src.ai.openai_client import OpenAIClient
    from src.monetization.affiliates import get_manager

    # AI Provider (required)
    if settings.openrouter_api_key:
        logger.info(f"  ✅ OpenRouter: {settings.ai_model}")
    elif settings.openai_api_key:
        logger.info(f"  ✅ OpenAI: {settings.openai_model}")
    else:
        logger.error("  ❌ No AI API key configured! Set OPENROUTER_API_KEY or OPENAI_API_KEY")

    # Initialize affiliate manager
    affiliate_manager = get_manager()
    logger.info(f"💰 Affiliate: Trojan Bot ({settings.trojan_ref_code[:8]}...)" if settings.trojan_ref_code else "💰 Affiliate: Trojan Bot (no ref code)")

    logger.info("═" * 70)
    logger.info("✅ All services initialized - Bot is ready!")
    logger.info("═" * 70)


async def on_shutdown(bot: Bot, logger: logging.Logger):
    """Called when the bot shuts down"""
    logger.info("═" * 70)
    logger.info("🛡️  AI SENTINEL BOT - Shutting Down")
    logger.info("═" * 70)

    # Close database connection
    try:
        from src.storage.database import get_database
        db = await get_database()
        await db.close()
    except Exception:
        pass

    # Close cache connection
    try:
        from src.storage.cache import get_cache
        cache = get_cache()
        await cache.close()
    except Exception:
        pass

    await bot.session.close()
    logger.info("✅ Cleanup complete")


# ═══════════════════════════════════════════════════════════════════════════
# BLINKS API SERVER
# ═══════════════════════════════════════════════════════════════════════════

async def start_blinks_api(logger: logging.Logger):
    """
    Start the Blinks API server for Solana Actions.

    Used in development mode (polling) to run API alongside bot.
    In webhook mode, Blinks routes are integrated into the webhook server.

    Args:
        logger: Logger instance

    Returns:
        AppRunner instance or None if disabled
    """
    if not settings.blinks_enabled:
        logger.info("🔗 Blinks API disabled")
        return None

    from aiohttp import web
    from src.api.app import create_api_app

    app = create_api_app()
    runner = web.AppRunner(app)
    await runner.setup()

    port = settings.actions_api_port
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"🔗 Blinks API started on port {port}")
    logger.info(f"   Actions manifest: http://localhost:{port}/.well-known/actions.json")
    logger.info(f"   Health check: http://localhost:{port}/health")

    return runner


# ═══════════════════════════════════════════════════════════════════════════
# WEBHOOK MODE
# ═══════════════════════════════════════════════════════════════════════════

async def run_webhook(bot: Bot, dp: Dispatcher, logger: logging.Logger):
    """
    Run bot in webhook mode for production deployment.

    Uses aiohttp to run a web server that receives Telegram updates.
    Also integrates Blinks API routes when enabled.
    """
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    # Webhook configuration
    webhook_path = f"/webhook/{settings.webhook_secret or 'default'}"
    webhook_url = f"{settings.webhook_url}{webhook_path}"

    # Create aiohttp app with Blinks middleware if enabled
    if settings.blinks_enabled:
        from src.api.middleware.cors import cors_middleware
        from src.api.middleware.rate_limit import rate_limit_middleware
        app = web.Application(middlewares=[cors_middleware, rate_limit_middleware])
    else:
        app = web.Application()

    # Health check endpoint
    async def health_check(request):
        return web.json_response({
            "status": "healthy",
            "bot": "AI Sentinel",
            "blinks_enabled": settings.blinks_enabled,
        })

    app.router.add_get("/health", health_check)

    # Setup Blinks API routes if enabled
    if settings.blinks_enabled:
        from src.api.app import setup_api_routes
        setup_api_routes(app)
        logger.info("🔗 Blinks API routes integrated into webhook server")

    # Setup webhook handler
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=webhook_path)
    setup_application(app, dp, bot=bot)

    # Set webhook
    await bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types()
    )
    logger.info(f"Webhook set: {webhook_url}")

    # Run server
    runner = web.AppRunner(app)
    await runner.setup()

    port = settings.webhook_port
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"Webhook server started on port {port}")

    # Keep running until stopped
    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """Main function to run the bot"""
    # Setup logging
    logger = setup_logging()

    blinks_runner = None

    try:
        # Create bot and dispatcher
        logger.info("Initializing bot...")
        bot, dp = await create_bot()

        # Run startup tasks
        await on_startup(bot, logger)

        # Choose mode based on configuration
        if settings.webhook_url:
            # Production: Webhook mode (Blinks API integrated into webhook server)
            logger.info("Starting in WEBHOOK mode...")
            try:
                await run_webhook(bot, dp, logger)
            finally:
                await on_shutdown(bot, logger)
        else:
            # Development: Polling mode + separate Blinks API server
            logger.info("Starting in POLLING mode...")

            # Start Blinks API server in development mode
            blinks_runner = await start_blinks_api(logger)

            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            finally:
                # Cleanup Blinks API
                if blinks_runner:
                    await blinks_runner.cleanup()
                    logger.info("🔗 Blinks API stopped")
                await on_shutdown(bot, logger)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        # Cleanup Blinks API on error
        if blinks_runner:
            try:
                await blinks_runner.cleanup()
            except Exception:
                pass
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
