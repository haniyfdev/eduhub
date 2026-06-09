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
        "Assalomu alaykum! 👋\n\n"
        "Sizni EduHub platformasining xabarchi botiga xush kelibsiz.\n\n"
        "Telefon raqamingizni ulash uchun quyidagi tugmani bosing 👇",
        reply_markup=kb,
    )


def _normalize_phone(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith('+'):
        raw = '+' + raw
    return raw


@router.message(F.contact)
async def contact_handler(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from apps.users.models import User

    phone = _normalize_phone(message.contact.phone_number or '')
    chat_id = message.chat.id

    def _link():
        user = User.objects.filter(phone=phone, is_active=True).first()
        if user:
            user.telegram_chat_id = chat_id
            user.save(update_fields=['telegram_chat_id'])
        return user

    user = await sync_to_async(_link)()

    if user:
        first_name = (message.from_user.first_name or '').strip() if message.from_user else ''
        await message.answer(
            f"👋 Assalomu alaykum, {first_name}!\n\n"
            "✅ Telefon raqamingiz Eduhub platformasiga muvaffaqiyatli ulandi.\n"
            "🤖 Endi platforma bilan bo'lgan muomalalarda botdan foydalanishingiz mumkin.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer(
            f"❌ Bu raqam ({phone}) tizimda topilmadi. "
            "Boshqa raqam bilan urinib ko'ring.",
            reply_markup=ReplyKeyboardRemove(),
        )
