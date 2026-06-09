from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni ulash", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Assalomu alaykum! 👋 EduHub botiga xush kelibsiz.\n\n"
        "Telefon raqamingizni ulash uchun quyidagi tugmani bosing 👇",
        reply_markup=kb,
    )


@router.message(F.contact)
async def contact_handler(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from apps.users.models import User

    phone_raw = (message.contact.phone_number or '').strip()
    phone = phone_raw if phone_raw.startswith('+') else '+' + phone_raw
    chat_id = message.chat.id

    def _link() -> int:
        return User.objects.filter(phone=phone, is_active=True).update(telegram_chat_id=chat_id)

    updated = await sync_to_async(_link)()

    if updated:
        await message.answer(
            "✅ Telefon raqamingiz tasdiqlandi! "
            "Endi parolni tiklash uchun saytdan foydalanishingiz mumkin.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer(
            "❌ Bu raqam tizimda topilmadi.",
            reply_markup=ReplyKeyboardRemove(),
        )
