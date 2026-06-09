import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

WEBHOOK_URL = '/api/telegram/webhook/'


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
        from apps.telegram_bot.handlers import start_handler
        from aiogram.types import ReplyKeyboardMarkup

        message = AsyncMock()
        run(start_handler(message))

        message.answer.assert_called_once()
        text = message.answer.call_args.args[0]
        kb = message.answer.call_args.kwargs['reply_markup']

        assert "Assalomu alaykum" in text
        assert "EduHub" in text
        assert isinstance(kb, ReplyKeyboardMarkup)
        assert kb.keyboard[0][0].text == "📱 Telefon raqamni ulash"
        assert kb.keyboard[0][0].request_contact is True


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
        ):
            mock_objects.filter.return_value.first.return_value = mock_user
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
        assert "Alisher" in text
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
