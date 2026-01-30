"""
Bot initialization and core components.

This module initializes the Telegram bot instance, dispatcher,
and main router. All handlers should be registered to the router.
"""

import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# BOT INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# Initialize bot instance with HTML parse mode for formatted messages
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

logger.info("✅ Bot instance created")


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCHER & STORAGE
# ═══════════════════════════════════════════════════════════════════════════════

# Initialize dispatcher with memory storage for FSM states
# For production, consider Redis storage for multi-instance deployments
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logger.info("✅ Dispatcher initialized with MemoryStorage")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

# Main router for all handlers
# Handlers from different modules will be registered to this router
router = Router()
dp.include_router(router)

logger.info("✅ Main router registered")


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = ['bot', 'dp', 'router', 'storage']
