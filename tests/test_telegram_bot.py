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
