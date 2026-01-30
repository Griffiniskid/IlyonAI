"""
Telegram bot package.

This package contains all bot-related components including:
- Bot and dispatcher initialization
- Command handlers
- Callback handlers
- Message handlers
- Middleware
"""

from .bot import bot, dp, router, storage

__all__ = ['bot', 'dp', 'router', 'storage']
