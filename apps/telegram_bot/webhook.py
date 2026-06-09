import asyncio
import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):

    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return HttpResponse('Bad Request', status=400)

        try:
            asyncio.run(self._process(data))
        except Exception as e:
            logger.error(f"Webhook processing error: {e}")

        return HttpResponse('OK')

    @staticmethod
    async def _process(data: dict) -> None:
        from aiogram import Bot
        from aiogram.types import Update
        from .bot import dp

        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            return

        bot = Bot(token=token)
        try:
            update = Update.model_validate(data)
            await dp.feed_update(bot, update)
        finally:
            await bot.session.close()
