import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.students.models import Student
from apps.notifications.models import SmsTemplate

WEBHOOK_URL = '/api/telegram/webhook/'
SEND_SMS_URL = '/api/v1/notifications/send-sms/'


def run(coro):
    return asyncio.run(coro)


def _fake_sync_to_async(fn, **kwargs):
    """Runs fn in the same thread — avoids spawning a thread that can't see test DB state."""
    async def wrapper(*args, **kw):
        return fn(*args, **kw)
    return wrapper


@pytest.fixture(autouse=True)
def _allow_sync_db_in_async_context(monkeypatch):
    """_fake_sync_to_async runs ORM calls directly inside the running event
    loop (on purpose, so they share the test's transaction/connection).
    Django's async-safety guard otherwise raises SynchronousOnlyOperation."""
    monkeypatch.setenv('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')


def _contact_message(phone_number: str, chat_id: int = 12345) -> AsyncMock:
    msg = AsyncMock()
    msg.contact = MagicMock()
    msg.contact.phone_number = phone_number
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    return msg


# ---------------------------------------------------------------------------
# Test 1 — /start handler
# ---------------------------------------------------------------------------

class TestStartHandler:
    def test_sends_welcome_message_with_contact_button(self):
        from apps.telegram_bot.handlers import start_handler, language_callback
        from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup

        message = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = 12345

        with (
            patch('asgiref.sync.sync_to_async', _fake_sync_to_async),
            patch('apps.users.models.User.objects') as mock_objects,
        ):
            mock_objects.filter.return_value.select_related.return_value.first.return_value = None
            run(start_handler(message))

        message.answer.assert_called_once()
        kb = message.answer.call_args.kwargs['reply_markup']
        assert isinstance(kb, InlineKeyboardMarkup)

        callback = AsyncMock()
        callback.data = "lang_uz"
        callback.from_user = None
        callback.message.chat.id = 12345

        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(language_callback(callback))

        callback.message.answer.assert_called_once()
        text = callback.message.answer.call_args.args[0]
        kb2 = callback.message.answer.call_args.kwargs['reply_markup']

        assert "Assalomu alaykum" in text
        assert "EduHub" in text
        assert isinstance(kb2, ReplyKeyboardMarkup)
        assert kb2.keyboard[0][0].text == "📱 Telefon raqamni ulash"
        assert kb2.keyboard[0][0].request_contact is True


# ---------------------------------------------------------------------------
# Boss-detection on /start — non-boss flow untouched, returning boss skips
# the language picker once a language was already chosen in a prior session
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestStartHandlerBossDetection:
    def test_non_boss_user_sees_language_picker(self, teacher_user):
        from apps.telegram_bot.handlers import start_handler
        from aiogram.types import InlineKeyboardMarkup

        teacher_user.telegram_chat_id = 700001
        teacher_user.save(update_fields=['telegram_chat_id'])

        message = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = 700001
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(start_handler(message))

        message.answer.assert_called_once()
        kb = message.answer.call_args.kwargs['reply_markup']
        assert isinstance(kb, InlineKeyboardMarkup)
        text = message.answer.call_args.args[0]
        assert "Tilni tanlang" in text

    def test_unlinked_boss_sees_language_picker(self, boss):
        from apps.telegram_bot.handlers import start_handler
        from aiogram.types import InlineKeyboardMarkup

        message = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = 700002
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(start_handler(message))

        message.answer.assert_called_once()
        kb = message.answer.call_args.kwargs['reply_markup']
        assert isinstance(kb, InlineKeyboardMarkup)
        text = message.answer.call_args.args[0]
        assert "Tilni tanlang" in text

    def test_linked_boss_without_cached_language_still_sees_picker(self, boss):
        """A linked boss whose language was never recorded (e.g. cache expired)
        must not be silently dropped into the boss menu — language choice is
        only skipped when we know a prior session already selected one."""
        from apps.telegram_bot.handlers import start_handler
        from aiogram.types import InlineKeyboardMarkup

        boss.telegram_chat_id = 700003
        boss.save(update_fields=['telegram_chat_id'])

        message = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = 700003
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(start_handler(message))

        text = message.answer.call_args.args[0]
        kb = message.answer.call_args.kwargs['reply_markup']
        assert "Tilni tanlang" in text
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_linked_boss_with_cached_language_goes_straight_to_boss_menu(self, boss):
        from apps.telegram_bot.handlers import start_handler
        from aiogram.types import InlineKeyboardMarkup
        from django.core.cache import cache

        chat_id = 700004
        boss.telegram_chat_id = chat_id
        boss.save(update_fields=['telegram_chat_id'])
        cache.set(f"bot_lang:{chat_id}", "uz", 3600)

        message = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = chat_id
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(start_handler(message))

        message.answer.assert_called_once()
        text = message.answer.call_args.args[0]
        kb = message.answer.call_args.kwargs['reply_markup']
        assert "boshqaruv menyusi" in text
        assert isinstance(kb, InlineKeyboardMarkup)
        assert kb.inline_keyboard[0][0].callback_data == "boss_reports"


# ---------------------------------------------------------------------------
# Tests 2 & 3 — contact handler (mocked DB, no network needed)
# ---------------------------------------------------------------------------

class TestContactHandler:
    def _run_contact(self, phone: str, mock_user, chat_id: int = 12345):
        """
        Run contact_handler with:
        - sync_to_async replaced by a direct call (same-thread)
        - apps.users.models.User patched to return mock_user (or None)
        """
        from apps.telegram_bot.handlers import contact_handler

        message = _contact_message(phone, chat_id)

        def fake_filter(**kwargs):
            qs = MagicMock()
            qs.first.return_value = mock_user
            return qs

        with (
            patch('asgiref.sync.sync_to_async', _fake_sync_to_async),
            patch('apps.users.models.User.objects') as mock_objects,
            patch('apps.students.models.Student.objects') as mock_student_objects,
        ):
            mock_objects.filter.return_value.first.return_value = mock_user
            mock_student_objects.filter.return_value.first.return_value = None
            if mock_user:
                mock_user.save = MagicMock()
            run(contact_handler(message))

        return message

    # Test 2 — phone found → chat_id saved on user, success message contains first_name
    def test_phone_found_saves_chat_id_and_sends_success(self):
        mock_user = MagicMock()
        mock_user.first_name = "Alisher"

        message = self._run_contact("+998901234567", mock_user, chat_id=98765)

        assert mock_user.telegram_chat_id == 98765
        mock_user.save.assert_called_once_with(update_fields=['telegram_chat_id'])

        text = message.answer.call_args.args[0]
        assert "muvaffaqiyatli" in text

    # Test 3 — phone not in DB → error message contains the normalised phone
    def test_phone_not_found_sends_error_with_phone(self):
        message = self._run_contact("+998000000001", None)

        text = message.answer.call_args.args[0]
        assert "+998000000001" in text

    # Extra — Telegram may omit leading +; must still match DB phone
    def test_phone_without_plus_normalized_before_db_lookup(self):
        mock_user = MagicMock()
        mock_user.first_name = "Bob"

        message = self._run_contact("998907654321", mock_user, chat_id=55555)

        assert mock_user.telegram_chat_id == 55555


# ---------------------------------------------------------------------------
# Test 4 — webhook HTTP endpoint
# ---------------------------------------------------------------------------

class TestWebhookEndpoint:
    def test_returns_200_for_valid_telegram_update(self, client):
        update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 123, "is_bot": False, "first_name": "Test"},
                "text": "/start",
            },
        }
        resp = client.post(
            WEBHOOK_URL,
            data=json.dumps(update),
            content_type='application/json',
        )
        assert resp.status_code == 200

    def test_returns_400_for_invalid_json(self, client):
        resp = client.post(
            WEBHOOK_URL,
            data="not json",
            content_type='application/json',
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests 1-2 — _find_and_link_account falls back to Student (phone / second_phone)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFindAndLinkAccount:
    # Test 1 — student found by primary phone → chat_id saved
    def test_student_found_by_primary_phone_saves_chat_id(self, company):
        from apps.telegram_bot.handlers import _find_and_link_account

        student = Student.objects.create(
            company=company, first_name="Aziz", last_name="Karimov",
            phone="+998901112233", status="active",
        )

        result = _find_and_link_account("+998901112233", 11111)

        student.refresh_from_db()
        assert result.id == student.id
        assert student.telegram_chat_id == 11111

    # Test 2 — student found by second_phone → chat_id saved
    def test_student_found_by_second_phone_saves_chat_id(self, company):
        from apps.telegram_bot.handlers import _find_and_link_account

        student = Student.objects.create(
            company=company, first_name="Vali", last_name="Tosh",
            phone="+998901112299", second_phone="+998950269345", status="active",
        )

        result = _find_and_link_account("+998950269345", 22222)

        student.refresh_from_db()
        assert result.id == student.id
        assert student.telegram_chat_id_second == 22222


# ---------------------------------------------------------------------------
# Test 3 — contact handler: phone not found in User or Student → error message
# ---------------------------------------------------------------------------

class TestContactHandlerNotFound:
    def test_phone_not_found_anywhere_sends_error(self):
        from apps.telegram_bot.handlers import contact_handler

        message = _contact_message("+998999999999", chat_id=33333)

        with (
            patch('asgiref.sync.sync_to_async', _fake_sync_to_async),
            patch('apps.users.models.User.objects') as mock_user_objects,
            patch('apps.students.models.Student.objects') as mock_student_objects,
        ):
            mock_user_objects.filter.return_value.first.return_value = None
            mock_student_objects.filter.return_value.first.return_value = None
            run(contact_handler(message))

        text = message.answer.call_args.args[0]
        assert "+998999999999" in text


# ---------------------------------------------------------------------------
# Tests 4-5 — /api/v1/notifications/send-sms/
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSendSmsEndpoint:
    # Test 4 — valid template + valid student → 200
    def test_send_sms_returns_200_with_valid_template_and_student(self, boss_client, company, student):
        template = SmsTemplate.objects.create(
            company=company, name="Test", body="Hello {student_name}",
        )

        resp = boss_client.post(SEND_SMS_URL, {
            'template_id': str(template.id),
            'message': None,
            'recipients': [
                {'type': 'student', 'id': str(student.id), 'phone': student.phone, 'amount': '', 'due_date': ''},
            ],
        }, format='json')

        assert resp.status_code == 200

    # Test 5 — malformed recipient id → 400, not 500
    def test_send_sms_returns_400_with_invalid_student_id(self, boss_client, company):
        template = SmsTemplate.objects.create(
            company=company, name="Test2", body="Hello {student_name}",
        )

        resp = boss_client.post(SEND_SMS_URL, {
            'template_id': str(template.id),
            'message': None,
            'recipients': [
                {'type': 'student', 'id': 'not-a-valid-uuid', 'phone': '+998901234567', 'amount': '', 'due_date': ''},
            ],
        }, format='json')

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Full onboarding: language picker -> contact share -> link -> boss menu
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestBossFullOnboardingFlow:
    def test_new_boss_goes_through_language_then_contact_then_boss_menu(self, boss):
        from apps.telegram_bot.handlers import start_handler, language_callback, contact_handler
        from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

        chat_id = 800001
        phone = "+998901230001"
        boss.phone = phone
        boss.save(update_fields=['phone'])

        message = AsyncMock()
        message.chat = MagicMock()
        message.chat.id = chat_id
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(start_handler(message))
        kb1 = message.answer.call_args.kwargs['reply_markup']
        assert isinstance(kb1, InlineKeyboardMarkup)

        callback = AsyncMock()
        callback.data = "lang_uz"
        callback.from_user = None
        callback.message.chat.id = chat_id
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(language_callback(callback))
        kb2 = callback.message.answer.call_args.kwargs['reply_markup']
        assert isinstance(kb2, ReplyKeyboardMarkup)

        contact_message = _contact_message(phone, chat_id=chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(contact_handler(contact_message))

        boss.refresh_from_db()
        assert boss.telegram_chat_id == chat_id

        calls = contact_message.answer.call_args_list
        assert len(calls) == 2
        assert "muvaffaqiyatli" in calls[0].args[0]
        boss_menu_kb = calls[1].kwargs['reply_markup']
        assert isinstance(boss_menu_kb, InlineKeyboardMarkup)
        assert boss_menu_kb.inline_keyboard[0][0].callback_data == "boss_reports"


# ---------------------------------------------------------------------------
# Hisobotlar entry point + branch picker
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestBossReportsMenu:
    def _callback(self, chat_id, data=None):
        cb = AsyncMock()
        cb.message.chat.id = chat_id
        cb.data = data
        return cb

    def test_single_branch_boss_skips_branch_picker(self, boss):
        from apps.telegram_bot.handlers import boss_reports_callback
        from aiogram.types import InlineKeyboardMarkup

        chat_id = 800101
        boss.telegram_chat_id = chat_id
        boss.save(update_fields=['telegram_chat_id'])

        callback = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(boss_reports_callback(callback))

        callback.message.answer.assert_called_once()
        text = callback.message.answer.call_args.args[0]
        kb = callback.message.answer.call_args.kwargs['reply_markup']
        assert "Hisobotlar" in text
        callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert callback_datas == ["rep_payments", "rep_debts", "rep_groups", "rep_lessons", "rep_salaries"]

    def test_multi_branch_boss_sees_picker_then_selection_persists(self, boss, company):
        from apps.companies.models import Company
        from apps.telegram_bot.handlers import boss_reports_callback, branch_select_callback, report_debts_callback
        from aiogram.types import InlineKeyboardMarkup
        from django.core.cache import cache

        branch = Company.objects.create(name="Branch B", branch_of=company, status='active')

        chat_id = 800102
        boss.telegram_chat_id = chat_id
        boss.save(update_fields=['telegram_chat_id'])

        cb1 = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(boss_reports_callback(cb1))
        kb1 = cb1.message.answer.call_args.kwargs['reply_markup']
        assert isinstance(kb1, InlineKeyboardMarkup)
        names = [btn.text for row in kb1.inline_keyboard for btn in row]
        assert company.name in names
        assert branch.name in names

        cb2 = self._callback(chat_id, data=f"branch:{branch.id}")
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(branch_select_callback(cb2))
        kb2 = cb2.message.answer.call_args.kwargs['reply_markup']
        callback_datas = [btn.callback_data for row in kb2.inline_keyboard for btn in row]
        assert "rep_debts" in callback_datas
        assert cache.get(f"bot_branch:{chat_id}") == str(branch.id)

        # Subsequent sub-menu tap must use the persisted branch — no picker shown again
        cb3 = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(report_debts_callback(cb3))
        text3 = cb3.message.answer.call_args.args[0]
        assert "Qarzdorlar" in text3

    def test_non_boss_chat_id_is_denied(self):
        from apps.telegram_bot.handlers import boss_reports_callback

        callback = self._callback(999999)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(boss_reports_callback(callback))

        callback.answer.assert_called_once()
        assert callback.answer.call_args.kwargs.get('show_alert') is True


# ---------------------------------------------------------------------------
# The 5 Hisobotlar sub-sections — correctly scoped + correctly formatted data
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBossReportSections:
    def test_today_payments_scoped_and_formatted(self, company, company2, group_student):
        from apps.payments.models import Payment
        from apps.telegram_bot.handlers import _get_today_payments, _format_payments
        import datetime

        today = datetime.date.today()
        Payment.objects.create(
            company=company, group_student=group_student,
            amount=150000, payment_type='cash', paid_at=datetime.datetime.now(),
        )
        # A payment in a different company must never leak into this report
        Payment.objects.create(
            company=company2, group_student=group_student,
            amount=999999, payment_type='cash', paid_at=datetime.datetime.now(),
        )

        rows = _get_today_payments(company, today)
        assert len(rows) == 1
        assert rows[0]['amount'] == 150000.0
        assert rows[0]['name'] == "Student One"

        text = _format_payments(rows, today)
        assert "150 000 so'm" in text
        assert "Student One" in text

    def test_debtors_scoped_and_formatted(self, company, company2, debt, group_student):
        from apps.debts.models import Debt
        from apps.telegram_bot.handlers import _get_debtors, _format_debts

        Debt.objects.create(
            company=company2, group_student=group_student,
            amount=777777, due_date=debt.due_date, status='unpaid',
        )
        # A paid debt must not appear in the debtors list
        Debt.objects.create(
            company=company, group_student=group_student,
            amount=111111, due_date=debt.due_date, status='paid',
        )

        rows = _get_debtors(company)
        assert len(rows) == 1
        assert rows[0]['amount'] == 500000.0
        assert rows[0]['name'] == "Student One"

        text = _format_debts(rows)
        assert "500 000 so'm" in text
        assert "Qarzdorlar" in text

    def test_groups_summary_scoped_and_formatted(self, company, group, group_student):
        from apps.telegram_bot.handlers import _get_groups_summary, _format_groups

        rows = _get_groups_summary(company)
        assert len(rows) == 1
        assert rows[0]['name'] == "1A"
        assert rows[0]['course'] == "Python Course"
        assert rows[0]['teacher'] == "Teacher User"
        assert rows[0]['count'] == 1  # group_student fixture defaults to status='trial'

        text = _format_groups(rows)
        assert "1A" in text
        assert "Python Course" in text
        assert "1 talaba" in text

    def test_today_lessons_includes_pending_groups_with_no_lesson_row_and_correct_local_time(
        self, company, course, teacher, room
    ):
        """Mirrors GroupViewSet.today: every active group scheduled for today
        must show up — finished/ongoing (has a Lesson row) AND pending (no
        Lesson row yet, just scheduled). A group scheduled on a different
        weekday must never appear. started_at must be converted from the
        stored UTC value to local time (Asia/Tashkent, UTC+5), not shown raw."""
        from apps.groups.models import Group
        from apps.lessons.models import Lesson
        from apps.telegram_bot.handlers import _get_today_lessons, _format_lessons, _DAY_MAP
        from django.utils import timezone as dj_timezone
        import datetime

        today = datetime.date.today()
        variant = _DAY_MAP[today.weekday()][0]
        other_variant = _DAY_MAP[(today.weekday() + 1) % 7][0]

        group_finished = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=10, gender_type='a', status='active', schedule=f"{variant} 10:00-11:30",
        )
        group_ongoing = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=11, gender_type='a', status='active', schedule=f"{variant} 10:00-11:30",
        )
        group_pending = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=12, gender_type='a', status='active', schedule=f"{variant} 10:00-11:30",
        )
        # Scheduled on a different weekday — must never appear in today's report
        Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=13, gender_type='a', status='active', schedule=f"{other_variant} 09:00-10:00",
        )

        # Stored as 06:20 UTC — the web dashboard shows this same value as
        # 11:20 local (Asia/Tashkent, UTC+5); the bot must match it exactly.
        started_at_utc = dj_timezone.make_aware(
            datetime.datetime(today.year, today.month, today.day, 6, 20), datetime.timezone.utc
        )
        Lesson.objects.create(
            group=group_finished, teacher=teacher, topic="T1", date=today,
            status='finished', started_at=started_at_utc,
        )
        Lesson.objects.create(
            group=group_ongoing, teacher=teacher, topic="T2", date=today,
            status='ongoing', started_at=started_at_utc,
        )
        # group_pending intentionally has no Lesson row at all

        rows = _get_today_lessons(company, today)
        by_group = {r['group']: r for r in rows}

        assert "13A" not in by_group
        assert by_group["10A"]['status'] == 'finished'
        assert by_group["10A"]['started_at'] == "11:20"
        assert by_group["11A"]['status'] == 'ongoing'
        assert by_group["12A"]['status'] == 'pending'
        assert by_group["12A"]['started_at'] is None

        text = _format_lessons(rows, today)
        assert "Tugallangan" in text
        assert "Jarayonda" in text
        assert "Boshlanmagan" in text
        assert "11:20" in text
        assert "06:20" not in text

    def test_salaries_scoped_and_formatted(self, company, teacher):
        from apps.telegram_bot.handlers import _get_boss_salaries, _format_salaries
        import datetime

        month = datetime.date.today().replace(day=1)
        rows = _get_boss_salaries(company, month)

        assert len(rows) == 1
        assert rows[0]['name'] == "Teacher User"
        assert rows[0]['total'] == 2000000.0  # fixed_amount, no debt lookup

        text = _format_salaries(rows, "Iyun 2026")
        assert "Teacher User" in text
        assert "2 000 000 so'm" in text

    def test_payment_name_with_html_special_chars_is_escaped(self, company, group_student):
        """Telegram's HTML parse_mode treats &, < and > as special. A raw
        student name containing them would either break the message or get
        silently mangled — they must come through escaped."""
        from apps.payments.models import Payment
        from apps.telegram_bot.handlers import _get_today_payments, _format_payments
        import datetime

        group_student.student.first_name = "Tom & Jerry"
        group_student.student.last_name = "<King>"
        group_student.student.save(update_fields=['first_name', 'last_name'])

        today = datetime.date.today()
        Payment.objects.create(
            company=company, group_student=group_student,
            amount=100000, payment_type='cash', paid_at=datetime.datetime.now(),
        )

        rows = _get_today_payments(company, today)
        text = _format_payments(rows, today)

        assert "<King>" not in text
        assert "Tom & Jerry" not in text
        assert "&amp;" in text
        assert "&lt;King&gt;" in text


# ---------------------------------------------------------------------------
# Navigation: the report sub-menu must reappear under every report message
# so the boss can jump straight to another section
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestBossReportNavigation:
    def _callback(self, chat_id):
        cb = AsyncMock()
        cb.message.chat.id = chat_id
        return cb

    def _setup_single_branch_boss(self, boss, chat_id):
        boss.telegram_chat_id = chat_id
        boss.save(update_fields=['telegram_chat_id'])

    def _assert_reports_kb_attached(self, callback):
        from aiogram.types import InlineKeyboardMarkup

        kb = callback.message.answer.call_args.kwargs.get('reply_markup')
        assert isinstance(kb, InlineKeyboardMarkup)
        callback_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert callback_datas == ["rep_payments", "rep_debts", "rep_groups", "rep_lessons", "rep_salaries"]

    def test_payments_report_reattaches_navigation_menu(self, boss):
        from apps.telegram_bot.handlers import report_payments_callback

        chat_id = 820001
        self._setup_single_branch_boss(boss, chat_id)
        callback = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(report_payments_callback(callback))
        self._assert_reports_kb_attached(callback)

    def test_debts_report_reattaches_navigation_menu(self, boss):
        from apps.telegram_bot.handlers import report_debts_callback

        chat_id = 820002
        self._setup_single_branch_boss(boss, chat_id)
        callback = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(report_debts_callback(callback))
        self._assert_reports_kb_attached(callback)

    def test_groups_report_reattaches_navigation_menu(self, boss):
        from apps.telegram_bot.handlers import report_groups_callback

        chat_id = 820003
        self._setup_single_branch_boss(boss, chat_id)
        callback = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(report_groups_callback(callback))
        self._assert_reports_kb_attached(callback)

    def test_lessons_report_reattaches_navigation_menu(self, boss):
        from apps.telegram_bot.handlers import report_lessons_callback

        chat_id = 820004
        self._setup_single_branch_boss(boss, chat_id)
        callback = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(report_lessons_callback(callback))
        self._assert_reports_kb_attached(callback)

    def test_salaries_report_reattaches_navigation_menu(self, boss):
        from apps.telegram_bot.handlers import report_salaries_callback

        chat_id = 820005
        self._setup_single_branch_boss(boss, chat_id)
        callback = self._callback(chat_id)
        with patch('asgiref.sync.sync_to_async', _fake_sync_to_async):
            run(report_salaries_callback(callback))
        # report_salaries_callback sends an interim "hisoblanmoqda" message
        # first — the nav menu must be on the FINAL message, not that one.
        self._assert_reports_kb_attached(callback)
