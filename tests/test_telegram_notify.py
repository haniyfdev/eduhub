import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.notifications.models import SmsTemplate

SEND_SMS_URL = '/api/v1/notifications/send-sms/'


class _SyncThread:
    """Stand-in for threading.Thread that runs the target synchronously
    on .start() — makes background-thread dispatch deterministic in tests."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        self.target(*self.args, **self.kwargs)


@pytest.mark.django_db
class TestTelegramNotify:
    # Test 1 — student with telegram_chat_id linked → counted as telegram_sent
    @patch('aiogram.Bot.send_message', new_callable=AsyncMock)
    def test_student_with_chat_id_sends_message(self, mock_send, boss_client, company, student):
        student.telegram_chat_id = 7785640931
        student.save(update_fields=['telegram_chat_id'])

        template = SmsTemplate.objects.create(
            company=company, name="Test", body="Salom {student_name}",
        )

        resp = boss_client.post(SEND_SMS_URL, {
            'template_id': str(template.id),
            'message': None,
            'recipients': [
                {'type': 'student', 'id': str(student.id), 'phone': student.phone},
            ],
        }, format='json')

        assert resp.status_code == 200
        assert resp.data['telegram_sent'] == 1
        assert resp.data['skipped'] == 0

    # Test 2 — student WITHOUT telegram_chat_id → counted as skipped
    def test_student_without_chat_id_skipped(self, boss_client, company, student):
        assert student.telegram_chat_id is None

        template = SmsTemplate.objects.create(
            company=company, name="Test2", body="Salom {student_name}",
        )

        resp = boss_client.post(SEND_SMS_URL, {
            'template_id': str(template.id),
            'message': None,
            'recipients': [
                {'type': 'student', 'id': str(student.id), 'phone': student.phone},
            ],
        }, format='json')

        assert resp.status_code == 200
        assert resp.data['telegram_sent'] == 0
        assert resp.data['skipped'] == 1

    # Test 3 — _send_telegram_background is dispatched via threading.Thread
    def test_send_runs_in_background_thread(self, boss_client, company, student):
        student.telegram_chat_id = 7785640931
        student.save(update_fields=['telegram_chat_id'])

        template = SmsTemplate.objects.create(
            company=company, name="Test3", body="Salom {student_name}",
        )

        with (
            patch('apps.notifications.views._send_telegram_background') as mock_bg,
            patch('apps.notifications.views.threading.Thread', _SyncThread),
        ):
            resp = boss_client.post(SEND_SMS_URL, {
                'template_id': str(template.id),
                'message': None,
                'recipients': [
                    {'type': 'student', 'id': str(student.id), 'phone': student.phone},
                ],
            }, format='json')

        assert resp.status_code == 200
        mock_bg.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4 — _send_telegram_background uses an explicit event loop, not asyncio.run
# ---------------------------------------------------------------------------

def test_new_event_loop_created():
    from apps.notifications.views import _send_telegram_background

    mock_loop = MagicMock()

    with (
        patch('asyncio.new_event_loop', return_value=mock_loop) as mock_new_loop,
        patch('asyncio.set_event_loop') as mock_set_loop,
        patch('asyncio.run') as mock_run,
    ):
        _send_telegram_background([(7785640931, 'hello')])

    mock_new_loop.assert_called_once()
    mock_set_loop.assert_called_once_with(mock_loop)
    mock_loop.run_until_complete.assert_called_once()
    mock_loop.close.assert_called_once()
    mock_run.assert_not_called()
