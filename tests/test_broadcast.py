from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.students.models import Student
from .conftest import make_phone

SUPERADMIN_BROADCAST_URL = "/api/superadmin/broadcast/"


class SyncThread:
    """Stand-in for threading.Thread that runs the target synchronously."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)

    def join(self, *a, **kw):
        pass


@pytest.fixture
def mock_bot():
    bot_instance = MagicMock()
    bot_instance.send_message = AsyncMock()
    bot_instance.session.close = AsyncMock()
    with patch('aiogram.Bot', return_value=bot_instance), patch('threading.Thread', SyncThread):
        yield bot_instance


@pytest.mark.django_db
class TestSuperadminBroadcast:
    def test_broadcast_sends_to_all_students_with_chat_id(self, superadmin_client, company, mock_bot):
        Student.objects.create(
            company=company, first_name="A", last_name="One",
            phone=make_phone(), status="active", telegram_chat_id=111,
        )
        Student.objects.create(
            company=company, first_name="B", last_name="Two",
            phone=make_phone(), status="active", telegram_chat_id=222,
        )

        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Salom"})

        assert resp.status_code == 200
        assert mock_bot.send_message.call_count == 2
        sent_chat_ids = {c.kwargs['chat_id'] for c in mock_bot.send_message.call_args_list}
        assert sent_chat_ids == {111, 222}

    def test_broadcast_skips_students_without_chat_id(self, superadmin_client, company, mock_bot):
        Student.objects.create(
            company=company, first_name="A", last_name="One",
            phone=make_phone(), status="active", telegram_chat_id=111,
        )
        Student.objects.create(
            company=company, first_name="B", last_name="Two",
            phone=make_phone(), status="active",
        )

        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Salom"})

        assert resp.status_code == 200
        assert mock_bot.send_message.call_count == 1
        assert mock_bot.send_message.call_args.kwargs['chat_id'] == 111

    def test_broadcast_includes_staff_with_chat_id(self, superadmin_client, boss, mock_bot):
        boss.telegram_chat_id = 999
        boss.save()

        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Salom"})

        assert resp.status_code == 200
        sent_chat_ids = {c.kwargs['chat_id'] for c in mock_bot.send_message.call_args_list}
        assert 999 in sent_chat_ids

    def test_broadcast_returns_correct_queued_count(self, superadmin_client, company, boss, mock_bot):
        Student.objects.create(
            company=company, first_name="A", last_name="One",
            phone=make_phone(), status="active", telegram_chat_id=111,
        )
        Student.objects.create(
            company=company, first_name="B", last_name="Two",
            phone=make_phone(), status="active", telegram_chat_id=222,
        )
        boss.telegram_chat_id = 999
        boss.save()

        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Salom"})

        assert resp.status_code == 200
        assert resp.data['queued'] == 3

    def test_broadcast_blocked_for_boss(self, boss_client):
        resp = boss_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Hi"})
        assert resp.status_code == 403

    def test_broadcast_blocked_for_manager(self, manager_client):
        resp = manager_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Hi"})
        assert resp.status_code == 403

    def test_broadcast_blocked_for_unauthenticated(self, api_client, db):
        resp = api_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Hi"})
        assert resp.status_code == 401

    def test_broadcast_empty_message_rejected(self, superadmin_client, db):
        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": ""})
        assert resp.status_code == 400

    def test_broadcast_message_format_includes_header(self, superadmin_client, company, mock_bot):
        Student.objects.create(
            company=company, first_name="A", last_name="One",
            phone=make_phone(), status="active", telegram_chat_id=111,
        )

        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Tizim yangilanishi"})

        assert resp.status_code == 200
        text = mock_bot.send_message.call_args.kwargs['text']
        assert "EduHub ma'muriyati" in text
        assert "Tizim yangilanishi" in text
