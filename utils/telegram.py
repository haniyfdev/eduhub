import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def send_otp_to_telegram(phone: str, code: str) -> bool:
    from apps.users.models import User

    user = (
        User.objects
        .filter(phone=phone, is_active=True)
        .exclude(telegram_chat_id=None)
        .first()
    )
    if not user or not user.telegram_chat_id:
        return False

    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        return False

    text = (
        f"🔐 EduHub tasdiqlash kodi: {code}\n"
        f"⏱ Amal qilish vaqti: 100 soniya"
    )
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": user.telegram_chat_id, "text": text},
            timeout=10,
        )
        return resp.ok
    except Exception as e:
        logger.error(f"Telegram OTP send error: {e}")
        return False
