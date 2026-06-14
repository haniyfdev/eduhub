from unittest.mock import patch

import pytest
from django.core.cache import cache

from apps.users.models import User
from .conftest import make_phone
from .test_otp import fake_redis  # noqa: F401  (reuse FakeRedis fixture)

FORGOT_PASSWORD_URL = "/api/auth/forgot-password/"
VERIFY_OTP_URL = "/api/auth/verify-otp/"
RESET_PASSWORD_URL = "/api/auth/reset-password/"


@pytest.fixture
def telegram_user(db, company):
    return User.objects.create_user(
        phone=make_phone(), password="OldPass123",
        first_name="Tele", last_name="User",
        role="admin", status="active", company=company,
        telegram_chat_id=555111,
    )


def _request_otp(api_client, phone):
    with patch('utils.telegram.send_otp_to_telegram', return_value=True) as mock_send:
        resp = api_client.post(FORGOT_PASSWORD_URL, {'phone': phone})
    code = mock_send.call_args[0][1]
    return resp, code


@pytest.mark.django_db
class TestOtpForgotPasswordFlow:
    def test_request_otp_sends_telegram_message(self, api_client, telegram_user, fake_redis):
        with patch('utils.telegram.send_otp_to_telegram', return_value=True) as mock_send:
            resp = api_client.post(FORGOT_PASSWORD_URL, {'phone': telegram_user.phone})

        assert resp.status_code == 200
        assert resp.data['success'] is True
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == telegram_user.phone

    def test_request_otp_stores_in_redis_with_ttl(self, api_client, telegram_user, fake_redis):
        resp, code = _request_otp(api_client, telegram_user.phone)

        assert resp.status_code == 200
        assert cache.get(f"otp:{telegram_user.phone}") == code

    def test_verify_otp_correct_returns_success(self, api_client, telegram_user, fake_redis):
        resp, code = _request_otp(api_client, telegram_user.phone)

        resp2 = api_client.post(VERIFY_OTP_URL, {'phone': telegram_user.phone, 'code': code})

        assert resp2.status_code == 200
        assert 'reset_token' in resp2.data

    def test_verify_otp_wrong_code_returns_error(self, api_client, telegram_user, fake_redis):
        _request_otp(api_client, telegram_user.phone)

        resp = api_client.post(VERIFY_OTP_URL, {'phone': telegram_user.phone, 'code': '000000'})

        assert resp.status_code == 400
        assert resp.data['error'] == 'invalid_otp'

    def test_verify_otp_expired_returns_error(self, api_client, telegram_user, fake_redis):
        # No OTP was ever generated for this phone -> cache miss -> 'expired'
        resp = api_client.post(VERIFY_OTP_URL, {'phone': telegram_user.phone, 'code': '123456'})

        assert resp.status_code == 400
        assert resp.data['error'] == 'otp_expired'

    def test_reset_password_with_valid_otp_token(self, api_client, telegram_user, fake_redis):
        resp, code = _request_otp(api_client, telegram_user.phone)
        resp2 = api_client.post(VERIFY_OTP_URL, {'phone': telegram_user.phone, 'code': code})
        reset_token = resp2.data['reset_token']

        resp3 = api_client.post(RESET_PASSWORD_URL, {
            'reset_token': reset_token, 'new_password': 'NewPass123',
        })

        assert resp3.status_code == 200
        assert resp3.data['success'] is True

        telegram_user.refresh_from_db()
        assert telegram_user.check_password('NewPass123')

    def test_reset_password_with_invalid_token_rejected(self, api_client, db, fake_redis):
        resp = api_client.post(RESET_PASSWORD_URL, {
            'reset_token': 'not-a-real-token', 'new_password': 'NewPass123',
        })

        assert resp.status_code == 400
        assert resp.data['error'] == 'invalid_token'

    def test_otp_cleared_from_redis_after_success(self, api_client, telegram_user, fake_redis):
        resp, code = _request_otp(api_client, telegram_user.phone)

        api_client.post(VERIFY_OTP_URL, {'phone': telegram_user.phone, 'code': code})

        assert cache.get(f"otp:{telegram_user.phone}") is None

    def test_unknown_phone_returns_404(self, api_client, db, fake_redis):
        # ForgotPasswordView intentionally returns 200 (anti phone-enumeration)
        # for an unknown phone rather than 404 -- see final report.
        resp = api_client.post(FORGOT_PASSWORD_URL, {'phone': make_phone()})

        assert resp.status_code == 200
        assert resp.data == {'success': True, 'expires_in': 100}
