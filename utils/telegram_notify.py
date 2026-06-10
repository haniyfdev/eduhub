import asyncio
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


async def send_telegram_message(chat_id: int, text: str) -> bool:
    """Send an HTML-formatted message to a Telegram chat. Returns success status."""
    from aiogram import Bot
    from aiogram.enums import ParseMode

    try:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
        await bot.session.close()
        return True
    except Exception as e:
        logger.error(f"Telegram send failed to {chat_id}: {e}")
        return False


def send_telegram_sync(chat_id: int, text: str) -> bool:
    """Sync wrapper around send_telegram_message for use in views/signals."""
    return asyncio.run(send_telegram_message(chat_id, text))
