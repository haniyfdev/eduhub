import pytest
from django.urls import reverse

from apps.users.models import User
from .conftest import make_phone


LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/token/refresh/"
LOGOUT_URL = "/api/auth/logout/"


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, boss):
        resp = api_client.post(LOGIN_URL, {"phone": boss.phone, "password": "pass1234"})
        assert resp.status_code == 200
        assert "access" in resp.data
        assert "refresh" in resp.data

    def test_login_wrong_password(self, api_client, boss):
        resp = api_client.post(LOGIN_URL, {"phone": boss.phone, "password": "wrong"})
        assert resp.status_code in (400, 401)

    def test_login_nonexistent_user(self, api_client):
        resp = api_client.post(LOGIN_URL, {"phone": "+998000000000", "password": "pass1234"})
        assert resp.status_code in (400, 401)

    def test_login_missing_fields(self, api_client):
        resp = api_client.post(LOGIN_URL, {"phone": ""})
        assert resp.status_code == 400

    def test_login_archived_user(self, api_client, db):
        phone = make_phone()
        User.objects.create_user(
            phone=phone, password="pass1234",
            first_name="A", last_name="B",
            role="boss", status="archived",
        )
        resp = api_client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        assert resp.status_code in (400, 401)


@pytest.mark.django_db
class TestTokenRefresh:
    def test_refresh_success(self, api_client, boss):
        tokens = api_client.post(LOGIN_URL, {"phone": boss.phone, "password": "pass1234"}).data
        resp = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
        assert resp.status_code == 200
        assert "access" in resp.data

    def test_refresh_invalid_token(self, api_client):
        resp = api_client.post(REFRESH_URL, {"refresh": "notavalidtoken"})
        assert resp.status_code == 401


@pytest.mark.django_db
class TestLogout:
    def test_logout_blacklists_token(self, api_client, boss):
        tokens = api_client.post(LOGIN_URL, {"phone": boss.phone, "password": "pass1234"}).data
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]})
        assert resp.status_code == 204

        # Refreshing with the blacklisted token should now fail
        resp2 = api_client.post(REFRESH_URL, {"refresh": tokens["refresh"]})
        assert resp2.status_code == 401

    def test_logout_unauthenticated(self, api_client):
        resp = api_client.post(LOGOUT_URL, {"refresh": "sometoken"})
        assert resp.status_code == 401
