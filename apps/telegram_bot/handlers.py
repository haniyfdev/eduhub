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

_NOT_FOUND = {
    'uz': "❌ Bu raqam ({phone}) tizimda topilmadi.",
    'ru': "❌ Номер ({phone}) не найден в системе.",
    'en': "❌ Number ({phone}) was not found in the system.",
}

_STUDENT_SUCCESS = {
    'uz': (
        "🎉 Tabriklaymiz, {first_name}!\n\n"
        "✅ Telefon raqamingiz EduHub platformasiga muvaffaqiyatli ulandi.\n"
        "📚 Endi o'quv markazingizdan xabarlar shu yerga keladi!"
    ),
    'ru': (
        "🎉 Поздравляем, {first_name}!\n\n"
        "✅ Ваш номер успешно привязан к платформе EduHub.\n"
        "📚 Теперь сообщения от вашего учебного центра будут приходить сюда!"
    ),
    'en': (
        "🎉 Congratulations, {first_name}!\n\n"
        "✅ Your number has been successfully linked to EduHub.\n"
        "📚 Messages from your education center will now arrive here!"
    ),
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


def _normalize_phone(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith('+'):
        raw = '+' + raw
    return raw


@router.message(F.contact)
async def contact_handler(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from django.core.cache import cache
    from apps.users.models import User
    from apps.students.models import Student

    phone = _normalize_phone(message.contact.phone_number or '')
    chat_id = message.chat.id

    def _get_lang():
        return cache.get(f"bot_lang:{chat_id}", 'uz')

    def _link_user():
        user = User.objects.filter(phone=phone, is_active=True).first()
        if user:
            user.telegram_chat_id = chat_id
            user.save(update_fields=['telegram_chat_id'])
        return user

    def _link_student():
        student = Student.objects.filter(phone=phone).exclude(status='archived').first()
        if student:
            student.telegram_chat_id = chat_id
            student.save(update_fields=['telegram_chat_id'])
        return student

    lang = await sync_to_async(_get_lang)()
    user = await sync_to_async(_link_user)()

    if user:
        await message.answer(_SUCCESS[lang], reply_markup=ReplyKeyboardRemove())
        return

    student = await sync_to_async(_link_student)()
    if student:
        await message.answer(
            _STUDENT_SUCCESS[lang].format(first_name=student.first_name),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer(_NOT_FOUND[lang].format(phone=phone), reply_markup=ReplyKeyboardRemove())
