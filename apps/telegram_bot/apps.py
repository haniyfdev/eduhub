import logging
import sys
from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Commands where webhook setup makes no sense (build steps, introspection, etc.)
_SKIP = frozenset({
    'migrate', 'makemigrations', 'shell', 'test',
    'collectstatic', 'dbshell', 'showmigrations', 'check',
    'create_superadmin',
})


class TelegramBotConfig(AppConfig):
    name = 'apps.telegram_bot'
    verbose_name = 'Telegram Bot'

    def ready(self) -> None:
        if len(sys.argv) > 1 and sys.argv[1] in _SKIP:
            return

        from decouple import config as dconf
        token = dconf('TELEGRAM_BOT_TOKEN', default='')
        backend_url = dconf('BACKEND_URL', default='')
        if not token or not backend_url:
            logger.warning('TELEGRAM_BOT_TOKEN or BACKEND_URL not configured — webhook skipped')
            return

        import asyncio
        try:
            asyncio.run(self._set_webhook(token, backend_url))
        except Exception as exc:
            logger.warning(f'Telegram webhook setup failed (server still starts normally): {exc}')

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
