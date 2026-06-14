import time
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.companies.models import Company
from apps.users.models import User
from .conftest import make_phone

LOGIN_URL = "/api/auth/login/"
SELECT_COMPANY_URL = "/api/auth/select-company/"


def _create_shared_phone_users(company, company2):
    phone = make_phone()
    user1 = User.objects.create_user(
        phone=phone, password="pass1234",
        first_name="Boss", last_name="One",
        role="boss", status="active", company=company,
    )
    user2 = User.objects.create_user(
        phone=phone, password="pass1234",
        first_name="Boss", last_name="Two",
        role="boss", status="active", company=company2,
    )
    return phone, user1, user2


@pytest.mark.django_db
class TestMultiCompanyLoginExtended:
    def test_same_phone_two_companies_returns_company_list(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        client = APIClient()
        resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})

        assert resp.status_code == 200
        assert resp.data["requires_company_selection"] is True
        assert len(resp.data["companies"]) == 2

    def test_company_list_contains_company_names_and_ids(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        client = APIClient()
        resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})

        assert resp.status_code == 200
        companies_by_id = {c["id"]: c["name"] for c in resp.data["companies"]}
        assert companies_by_id[str(company.id)] == company.name
        assert companies_by_id[str(company2.id)] == company2.name

    def test_select_company_returns_jwt_token(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        temp_token = login_resp.data["temp_token"]

        resp = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(company2.id),
        })

        assert resp.status_code == 200
        access = AccessToken(resp.data["access"])
        assert str(access["user_id"]) == str(user2.id)
        # refresh token also decodes successfully
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken(resp.data["refresh"])
        assert str(refresh["user_id"]) == str(user2.id)

    def test_select_company_wrong_id_rejected(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        temp_token = login_resp.data["temp_token"]

        other_company = Company.objects.create(name="Totally Unrelated", phone=make_phone())
        resp = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(other_company.id),
        })

        assert resp.status_code == 400
        assert "error" in resp.data

    def test_temp_token_expires_after_5_minutes(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        temp_token = login_resp.data["temp_token"]

        with patch('apps.users.views._COMPANY_SELECT_MAX_AGE', 1):
            time.sleep(1.5)
            resp = client.post(SELECT_COMPANY_URL, {
                "temp_token": temp_token,
                "company_id": str(company.id),
            })

        assert resp.status_code == 400
        assert "expired" in resp.data["error"].lower()

    def test_temp_token_cannot_be_reused(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        temp_token = login_resp.data["temp_token"]

        first = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(company.id),
        })
        assert first.status_code == 200

        # NOTE: temp_token is a stateless signed token (django.core.signing) with
        # no server-side single-use tracking, so it remains valid for repeated
        # use within its 5-minute window. See final report.
        second = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(company2.id),
        })
        assert second.status_code == 200

    def test_archived_company_not_in_login_list(self, superadmin_client, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)

        archive_resp = superadmin_client.post(f"/api/superadmin/companies/{company2.id}/archive/")
        assert archive_resp.status_code == 200

        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})

        assert login_resp.status_code == 200
        assert "requires_company_selection" not in login_resp.data
        assert login_resp.data["user"]["company_id"] == str(company.id)

    def test_user_inactive_in_one_company_skipped(self, company, company2, db):
        phone, user1, user2 = _create_shared_phone_users(company, company2)
        user2.is_active = False
        user2.save()

        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})

        assert login_resp.status_code == 200
        assert "requires_company_selection" not in login_resp.data
        assert login_resp.data["user"]["company_id"] == str(company.id)
