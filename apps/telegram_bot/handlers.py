import datetime
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

_UZ_MONTHS = [
    '', 'Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
    'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr',
]

_LESSON_STATUS_LABELS = {
    'finished': 'Tugallangan',
    'ongoing':  'Jarayonda',
    'pending':  "Boshlanmagan",
}

_BRANCH_CACHE_TTL = 365 * 24 * 3600


def _fmt_money(value) -> str:
    return f"{int(value):,}".replace(',', ' ')


# ── Boss menu ──────────────────────────────────────────────────────────────

def _boss_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📊 Hisobotlar", callback_data="boss_reports"),
    ]])


def _reports_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 To'lovlar", callback_data="rep_payments")],
        [InlineKeyboardButton(text="⚠️ Qarzdorlar", callback_data="rep_debts")],
        [InlineKeyboardButton(text="👥 Guruhlar", callback_data="rep_groups")],
        [InlineKeyboardButton(text="📚 Bugungi darslar", callback_data="rep_lessons")],
        [InlineKeyboardButton(text="💵 Maoshlar", callback_data="rep_salaries")],
    ])


def _branch_picker_kb(companies) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c.name, callback_data=f"branch:{c.id}")] for c in companies
    ])


def _get_boss_user(chat_id: int):
    """Return the linked User with role='boss' for this chat_id, or None."""
    from apps.users.models import User
    return (
        User.objects
        .filter(telegram_chat_id=chat_id, role='boss', is_active=True)
        .select_related('company')
        .first()
    )


def _get_accessible_companies(boss):
    """The boss's own company plus its active branches (mirrors _build_user_payload)."""
    from apps.companies.models import Company
    companies = [boss.company]
    branches = Company.objects.filter(branch_of_id=boss.company_id, status='active').order_by('name')
    companies.extend(branches)
    return companies


def _resolve_branch(boss, chat_id):
    """Returns (company, companies). company is None when the boss has multiple
    branches and none is cached yet for this chat — caller must show the picker."""
    from django.core.cache import cache

    companies = _get_accessible_companies(boss)
    if len(companies) <= 1:
        return (companies[0] if companies else None), companies

    cached_id = cache.get(f"bot_branch:{chat_id}")
    if cached_id:
        match = next((c for c in companies if str(c.id) == cached_id), None)
        if match:
            return match, companies
    return None, companies


async def _resolve_company_for_callback(callback: CallbackQuery, boss, chat_id: int):
    """Resolves the selected branch company for a boss callback. If ambiguous,
    sends the branch picker and returns None."""
    from asgiref.sync import sync_to_async

    company, companies = await sync_to_async(_resolve_branch)(boss, chat_id)
    if company is None:
        await callback.message.answer("Filialni tanlang:", reply_markup=_branch_picker_kb(companies))
        return None
    return company


async def _require_boss_and_company(callback: CallbackQuery):
    """Resolves (boss, company) for a boss-only callback. Sends a denial alert
    or the branch picker as needed; in those cases company is None."""
    from asgiref.sync import sync_to_async

    chat_id = callback.message.chat.id
    boss = await sync_to_async(_get_boss_user)(chat_id)
    if not boss or not boss.company:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return None, None

    await callback.answer()
    company = await _resolve_company_for_callback(callback, boss, chat_id)
    return boss, company


# ── Data fetchers ────────────────────────────────────────────────────────────

def _get_boss_salaries(company, month):
    """Generate salaries for current month and return per-teacher totals.

    Mirrors _run_generate (calculate step) then get_queryset (read step)
    from TeacherSalaryViewSet — no duplicate logic, same functions called.
    """
    from django.db.models import Q
    from apps.salaries.logic import calculate_teacher_salary
    from apps.salaries.models import TeacherSalary
    from apps.teachers.models import Teacher

    for teacher in Teacher.objects.filter(company=company, status='active'):
        calculate_teacher_salary(teacher, month)

    salaries = (
        TeacherSalary.objects
        .filter(company=company, month__year=month.year, month__month=month.month)
        .filter(
            Q(teacher__status='active') |
            Q(teacher__status='archived', archive_billing_type__isnull=False)
        )
        .filter(Q(calculated_amount__gt=0) | Q(paid_amount__gt=0))
        .select_related('teacher__user')
        .distinct()
    )

    teacher_totals: dict[str, dict] = {}
    for s in salaries:
        tid = str(s.teacher_id)
        if tid not in teacher_totals:
            teacher_totals[tid] = {
                'name':  s.teacher.user.get_full_name(),
                'total': 0.0,
            }
        teacher_totals[tid]['total'] += float(s.calculated_amount)

    return sorted(teacher_totals.values(), key=lambda r: r['name'])


def _get_today_payments(company, today):
    from apps.payments.models import Payment

    qs = (
        Payment.objects
        .filter(company=company, paid_at__date=today)
        .select_related('group_student__student')
        .order_by('paid_at')
    )
    return [
        {
            'name':   f"{p.group_student.student.first_name} {p.group_student.student.last_name}",
            'amount': float(p.amount),
            'time':   p.paid_at.strftime('%H:%M'),
        }
        for p in qs
    ]


def _get_debtors(company):
    from apps.debts.models import Debt

    qs = (
        Debt.objects
        .filter(company=company, status__in=['unpaid', 'partial', 'overdue'])
        .select_related('group_student__student')
        .order_by('due_date')
    )
    return [
        {
            'name':     f"{d.group_student.student.first_name} {d.group_student.student.last_name}",
            'amount':   float(d.amount),
            'due_date': d.due_date.strftime('%d.%m.%Y'),
        }
        for d in qs
    ]


def _get_groups_summary(company):
    from apps.groups.models import Group

    qs = (
        Group.objects
        .filter(company=company, status='active')
        .select_related('course', 'teacher__user')
        .order_by('number')
    )
    rows = []
    for g in qs:
        count = g.memberships.filter(left_at__isnull=True, status__in=['active', 'trial']).count()
        rows.append({
            'name':    f"{g.number}{(g.gender_type or '').upper()}",
            'course':  g.course.name if g.course else '—',
            'teacher': g.teacher.user.get_full_name() if g.teacher and g.teacher.user else '—',
            'count':   count,
        })
    return rows


def _get_today_lessons(company, today):
    from apps.lessons.models import Lesson

    qs = (
        Lesson.objects
        .filter(group__company=company, date=today)
        .select_related('group', 'teacher__user')
        .order_by('group__number')
    )
    return [
        {
            'group':      f"{l.group.number}{(l.group.gender_type or '').upper()}",
            'teacher':    l.teacher.user.get_full_name() if l.teacher and l.teacher.user else '—',
            'status':     l.status,
            'started_at': l.started_at.strftime('%H:%M') if l.started_at else None,
        }
        for l in qs
    ]


# ── Formatters ───────────────────────────────────────────────────────────────

def _format_salaries(rows, month_label):
    if not rows:
        return f"💵 <b>Maoshlar — {month_label}</b>\n\nBu oy uchun hisoblangan maosh yo'q."
    lines = [f"💵 <b>Maoshlar — {month_label}</b>\n"]
    for r in rows:
        lines.append(f"• {r['name']} — {_fmt_money(r['total'])} so'm")
    total = sum(r['total'] for r in rows)
    lines.append(f"\n<b>Jami: {_fmt_money(total)} so'm</b>")
    return "\n".join(lines)


def _format_payments(rows, today):
    label = today.strftime('%d.%m.%Y')
    if not rows:
        return f"💰 <b>Bugungi to'lovlar — {label}</b>\n\nBugun hali to'lov bo'lmadi."
    lines = [f"💰 <b>Bugungi to'lovlar — {label}</b>\n"]
    for r in rows:
        lines.append(f"• {r['name']} — {_fmt_money(r['amount'])} so'm ({r['time']})")
    total = sum(r['amount'] for r in rows)
    lines.append(f"\n<b>Jami: {_fmt_money(total)} so'm</b>")
    lines.append(
        "\nUzoqroq davr (hafta, 10-20 kun) uchun veb-saytdagi boshqaruv panelini "
        "tekshiring — bot faqat bugungi ma'lumotni ko'rsatadi."
    )
    return "\n".join(lines)


def _format_debts(rows):
    if not rows:
        return "⚠️ <b>Qarzdorlar</b>\n\nHozircha qarzdorlik yo'q."
    lines = [f"⚠️ <b>Qarzdorlar</b> ({len(rows)})\n"]
    for r in rows:
        lines.append(f"• {r['name']} — {_fmt_money(r['amount'])} so'm (muddati: {r['due_date']})")
    total = sum(r['amount'] for r in rows)
    lines.append(f"\n<b>Jami qarz: {_fmt_money(total)} so'm</b>")
    return "\n".join(lines)


def _format_groups(rows):
    if not rows:
        return "👥 <b>Guruhlar</b>\n\nFaol guruhlar topilmadi."
    lines = [f"👥 <b>Guruhlar</b> ({len(rows)})\n"]
    for r in rows:
        lines.append(f"• {r['name']} — {r['course']} — {r['teacher']} — {r['count']} talaba")
    return "\n".join(lines)


def _format_lessons(rows, today):
    label = today.strftime('%d.%m.%Y')
    if not rows:
        return f"📚 <b>Bugungi darslar — {label}</b>\n\nBugunga darslar topilmadi."
    by_status: dict[str, list] = {'finished': [], 'ongoing': [], 'pending': []}
    for r in rows:
        by_status.setdefault(r['status'], []).append(r)
    lines = [f"📚 <b>Bugungi darslar — {label}</b>"]
    for status_key in ('finished', 'ongoing', 'pending'):
        group_rows = by_status.get(status_key, [])
        if not group_rows:
            continue
        lines.append(f"\n<b>{_LESSON_STATUS_LABELS[status_key]}</b>")
        for r in group_rows:
            time_part = f" ({r['started_at']})" if r['started_at'] else ""
            lines.append(f"• {r['group']} — {r['teacher']}{time_part}")
    return "\n".join(lines)


# ── /start ─────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from django.core.cache import cache

    chat_id = message.chat.id
    boss = await sync_to_async(_get_boss_user)(chat_id)

    if boss:
        lang_cached = await sync_to_async(cache.get)(f"bot_lang:{chat_id}")
        if lang_cached:
            name = boss.get_full_name() or "Xo'jayin"
            await message.answer(
                f"👋 Salom, {name}!\n\nEduHub boshqaruv menyusi:",
                reply_markup=_boss_menu_kb(),
            )
            return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    ]])
    await message.answer(
        "🌐 Tilni tanlang / Выберите язык / Choose language:",
        reply_markup=kb,
    )


# ── Language selection ──────────────────────────────────────────────────────

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


# ── Phone linking ───────────────────────────────────────────────────────────

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
        from apps.users.models import User as UserModel
        if isinstance(account, UserModel) and account.role == 'boss':
            name = account.get_full_name() or "Xo'jayin"
            await message.answer(
                f"👋 {name}, EduHub boshqaruv menyusi:",
                reply_markup=_boss_menu_kb(),
            )
    else:
        await message.answer(_ERROR[lang].format(phone=phone), reply_markup=ReplyKeyboardRemove())


# ── Boss: Hisobotlar menu tree ──────────────────────────────────────────────

@router.callback_query(F.data == "boss_reports")
async def boss_reports_callback(callback: CallbackQuery) -> None:
    boss, company = await _require_boss_and_company(callback)
    if company is None:
        return
    await callback.message.answer("📊 Hisobotlar:", reply_markup=_reports_menu_kb())


@router.callback_query(F.data.startswith("branch:"))
async def branch_select_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async
    from django.core.cache import cache

    chat_id = callback.message.chat.id
    company_id = callback.data.split(":", 1)[1]

    boss = await sync_to_async(_get_boss_user)(chat_id)
    if not boss or not boss.company:
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return

    def _validate_and_store():
        companies = _get_accessible_companies(boss)
        if not any(str(c.id) == company_id for c in companies):
            return False
        cache.set(f"bot_branch:{chat_id}", company_id, timeout=_BRANCH_CACHE_TTL)
        return True

    valid = await sync_to_async(_validate_and_store)()
    if not valid:
        await callback.answer("Noto'g'ri filial.", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer("📊 Hisobotlar:", reply_markup=_reports_menu_kb())


@router.callback_query(F.data == "rep_payments")
async def report_payments_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async

    boss, company = await _require_boss_and_company(callback)
    if company is None:
        return

    today = datetime.date.today()
    rows = await sync_to_async(_get_today_payments)(company, today)
    await callback.message.answer(_format_payments(rows, today), parse_mode="HTML")


@router.callback_query(F.data == "rep_debts")
async def report_debts_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async

    boss, company = await _require_boss_and_company(callback)
    if company is None:
        return

    rows = await sync_to_async(_get_debtors)(company)
    await callback.message.answer(_format_debts(rows), parse_mode="HTML")


@router.callback_query(F.data == "rep_groups")
async def report_groups_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async

    boss, company = await _require_boss_and_company(callback)
    if company is None:
        return

    rows = await sync_to_async(_get_groups_summary)(company)
    await callback.message.answer(_format_groups(rows), parse_mode="HTML")


@router.callback_query(F.data == "rep_lessons")
async def report_lessons_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async

    boss, company = await _require_boss_and_company(callback)
    if company is None:
        return

    today = datetime.date.today()
    rows = await sync_to_async(_get_today_lessons)(company, today)
    await callback.message.answer(_format_lessons(rows, today), parse_mode="HTML")


@router.callback_query(F.data == "rep_salaries")
async def report_salaries_callback(callback: CallbackQuery) -> None:
    from asgiref.sync import sync_to_async

    boss, company = await _require_boss_and_company(callback)
    if company is None:
        return

    await callback.message.answer("⏳ Maoshlar hisoblanmoqda...")
    month = datetime.date.today().replace(day=1)
    month_label = f"{_UZ_MONTHS[month.month]} {month.year}"
    rows = await sync_to_async(_get_boss_salaries)(company, month)
    await callback.message.answer(_format_salaries(rows, month_label), parse_mode="HTML")
