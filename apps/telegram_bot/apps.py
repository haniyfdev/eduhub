import logging
import sys
from django.apps import AppConfig

logger = logging.getLogger(__name__)

_SKIP = frozenset({
    'migrate', 'makemigrations', 'shell', 'test',
    'collectstatic', 'dbshell', 'showmigrations', 'check',
})


class TelegramBotConfig(AppConfig):
    name = 'apps.telegram_bot'
    verbose_name = 'Telegram Bot'

    def ready(self) -> None:
        # Skip during management commands that don't need the bot
        if len(sys.argv) > 1 and sys.argv[1] in _SKIP:
            return

        from .bot import dp
        from .handlers import router
        dp.include_router(router)

        from decouple import config as dconf
        token = dconf('TELEGRAM_BOT_TOKEN', default='')
        backend_url = dconf('BACKEND_URL', default='')
        if not token or not backend_url:
            logger.warning('TELEGRAM_BOT_TOKEN or BACKEND_URL not set — webhook not configured')
            return

        import asyncio
        try:
            asyncio.run(self._set_webhook(token, backend_url))
        except Exception as e:
            logger.warning(f'Telegram webhook setup failed: {e}')

    @staticmethod
    async def _set_webhook(token: str, backend_url: str) -> None:
        from aiogram import Bot
        bot = Bot(token=token)
        try:
            url = f"{backend_url.rstrip('/')}/api/telegram/webhook/"
            await bot.set_webhook(url)
            logger.info(f'Telegram webhook set to {url}')
        finally:
            await bot.session.close()
