"""
Access control middleware for AI Sentinel bot.

Restricts bot access to whitelisted Telegram IDs during testing phase.
"""

import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from src.config import settings

logger = logging.getLogger(__name__)


class AccessControlMiddleware(BaseMiddleware):
    """
    Whitelist-based access control middleware.

    Restricts bot usage to Telegram IDs specified in ALLOWED_USERS env var.
    If ALLOWED_USERS is empty, all users are allowed (public access).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Check if user is whitelisted before processing.

        Args:
            handler: Next handler in chain
            event: Telegram event (Message or CallbackQuery)
            data: Handler data

        Returns:
            Handler result or None if access denied
        """
        # Get whitelist of allowed user IDs
        allowed_ids = settings.get_allowed_user_ids()

        # If no whitelist configured, allow all users (public access)
        if not allowed_ids:
            return await handler(event, data)

        # Get user from event
        user = getattr(event, 'from_user', None)
        if not user:
            return await handler(event, data)

        # Check if user is in whitelist
        if user.id not in allowed_ids:
            logger.info(f"Access denied for user {user.id} (@{user.username})")

            # Send access denied message
            if isinstance(event, (Message, CallbackQuery)):
                await event.answer(
                    "Access Denied\n\n"
                    "This bot is currently in private testing mode.\n"
                    "Contact the administrator for access."
                )
            return None

        # User is whitelisted, proceed
        return await handler(event, data)
