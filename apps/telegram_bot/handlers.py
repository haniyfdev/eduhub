import re

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

router = Router()

_WELCOME = {
    'uz': (
        "Assalomu alaykum, {username}! 👋\n\n"
        "Sizni EduHub platformasining xabarchi botiga xush kelibsiz.\n\n"
        "Telefon raqamingizni ulash uchun quyidagi tugmani bosing 👇"
    ),
    'ru': (
        "Здравствуйте, {username}! 👋\n\n"
        "Добро пожаловать в бот платформы EduHub.\n\n"
        "Нажмите кнопку ниже, чтобы привязать номер телефона 👇"
    ),
    'en': (
        "Hello, {username}! 👋\n\n"
        "Welcome to EduHub platform bot.\n\n"
        "Press the button below to link your phone number 👇"
    ),
}

_CONTACT_BUTTON = {
    'uz': "📱 Telefon raqamni ulash",
    'ru': "📱 Привязать номер телефона",
    'en': "📱 Link phone number",
}

_SUCCESS = {
    'uz': (
        "🎉 Tabriklaymiz!\n\n"
        "✅ Telefon raqamingiz EduHub platformasiga muvaffaqiyatli ulandi.\n"
        "🤖 Endi platforma bilan bo'lgan muomalalarda botdan foydalanishingiz mumkin!"
    ),
    'ru': (
        "🎉 Поздравляем!\n\n"
        "✅ Ваш номер телефона успешно привязан к платформе EduHub.\n"
        "🤖 Теперь вы можете использовать бота для работы с платформой!"
    ),
    'en': (
        "🎉 Congratulations!\n\n"
        "✅ Your phone number has been successfully linked to the EduHub platform.\n"
        "🤖 You can now use the bot to interact with the platform!"
    ),
}

_ERROR = {
    'uz': "❌ Bu raqam ({phone}) tizimda topilmadi. Boshqa raqam bilan urinib ko'ring.",
    'ru': "❌ Номер ({phone}) не найден в системе. Попробуйте другой номер.",
    'en': "❌ Number ({phone}) not found in the system. Try another number.",
}


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    ]])
    await message.answer(
        "🌐 Tilni tanlang / Выберите язык / Choose language:",
        reply_markup=kb,
    )


@router.callback_query(F.data.in_({"lang_uz", "lang_ru", "lang_en"}))
async def language_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async
    from django.core.cache import cache

    lang = callback.data.split('_')[1]
    chat_id = callback.message.chat.id

    def _save_lang():
        cache.set(f"bot_lang:{chat_id}", lang, timeout=365 * 24 * 3600)

    await sync_to_async(_save_lang)()

    username = ''
    if callback.from_user:
        first = callback.from_user.first_name or ''
        last = callback.from_user.last_name or ''
        username = (first + (' ' + last if last else '')).strip()
    if not username:
        username = 'Foydalanuvchi'

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=_CONTACT_BUTTON[lang], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await callback.message.answer(_WELCOME[lang].format(username=username), reply_markup=kb)
    await callback.answer()


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('998'):
        return f"+{digits}"
    elif digits.startswith('0'):
        return f"+998{digits[1:]}"
    else:
        return f"+998{digits}"


def _find_and_link_account(phone: str, chat_id: int):
    """Match a normalized phone against User then Student (phone or second_phone)
    and save the Telegram chat_id onto whichever field matches.
    A match on `phone` saves telegram_chat_id (student); a match on
    `second_phone` saves telegram_chat_id_second (parent) — never mixed."""
    from apps.users.models import User
    from apps.students.models import Student

    user = User.objects.filter(phone=phone, is_active=True).first()
    if user:
        user.telegram_chat_id = chat_id
        user.save(update_fields=['telegram_chat_id'])
        return user

    student = Student.objects.filter(phone=phone).first()
    if student:
        student.telegram_chat_id = chat_id
        student.save(update_fields=['telegram_chat_id'])
        return student

    student = Student.objects.filter(second_phone=phone).first()
    if student:
        student.telegram_chat_id_second = chat_id
        student.save(update_fields=['telegram_chat_id_second'])
        return student

    return None


@router.message(F.contact)
async def contact_handler(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from django.core.cache import cache

    phone = _normalize_phone(message.contact.phone_number or '')
    chat_id = message.chat.id

    def _get_lang():
        return cache.get(f"bot_lang:{chat_id}", 'uz')

    lang = await sync_to_async(_get_lang)()
    account = await sync_to_async(_find_and_link_account)(phone, chat_id)

    if account:
        await message.answer(_SUCCESS[lang], reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer(_ERROR[lang].format(phone=phone), reply_markup=ReplyKeyboardRemove())
