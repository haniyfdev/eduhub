import pytest
from django.core import signing

from apps.users.models import User
from apps.companies.models import Company
from .conftest import make_phone

LOGIN_URL = "/api/auth/login/"
SELECT_COMPANY_URL = "/api/auth/select-company/"


@pytest.mark.django_db
class TestSingleCompanyLogin:
    def test_single_company_login_returns_tokens_directly(self, boss):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post(LOGIN_URL, {"phone": boss.phone, "password": "pass1234"})
        assert resp.status_code == 200
        assert "access" in resp.data
        assert "refresh" in resp.data
        assert "requires_company_selection" not in resp.data
        assert resp.data["user"]["company_id"] == str(boss.company_id)

    def test_user_payload_includes_accessible_companies(self, boss, company):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post(LOGIN_URL, {"phone": boss.phone, "password": "pass1234"})
        assert resp.status_code == 200
        accessible = resp.data["user"]["accessible_companies"]
        ids = [c["id"] for c in accessible]
        assert str(company.id) in ids

    def test_accessible_companies_includes_branches(self, boss, company, db):
        from rest_framework.test import APIClient
        branch = Company.objects.create(name="Branch", phone=make_phone(), branch_of=company, status="active")

        client = APIClient()
        resp = client.post(LOGIN_URL, {"phone": boss.phone, "password": "pass1234"})
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.data["user"]["accessible_companies"]]
        assert str(company.id) in ids
        assert str(branch.id) in ids


@pytest.mark.django_db
class TestMultiCompanyLogin:
    def _create_shared_phone_users(self, company, company2):
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

    def test_multiple_companies_requires_selection(self, company, company2, db):
        phone, user1, user2 = self._create_shared_phone_users(company, company2)

        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})

        assert resp.status_code == 200
        assert resp.data["requires_company_selection"] is True
        assert "temp_token" in resp.data
        company_ids = [c["id"] for c in resp.data["companies"]]
        assert str(company.id) in company_ids
        assert str(company2.id) in company_ids

    def test_select_company_returns_tokens(self, company, company2, db):
        phone, user1, user2 = self._create_shared_phone_users(company, company2)

        from rest_framework.test import APIClient
        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        temp_token = login_resp.data["temp_token"]

        resp = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(company2.id),
        })
        assert resp.status_code == 200
        assert "access" in resp.data
        assert "refresh" in resp.data
        assert resp.data["user"]["company_id"] == str(company2.id)
        assert resp.data["user"]["id"] == str(user2.id)

    def test_select_company_invalid_temp_token(self, db):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post(SELECT_COMPANY_URL, {
            "temp_token": "not-a-valid-token",
            "company_id": "00000000-0000-0000-0000-000000000000",
        })
        assert resp.status_code == 400

    def test_select_company_missing_fields(self, db):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post(SELECT_COMPANY_URL, {})
        assert resp.status_code == 400

    def test_select_company_wrong_company_id(self, company, company2, db):
        phone, user1, user2 = self._create_shared_phone_users(company, company2)

        from rest_framework.test import APIClient
        client = APIClient()
        login_resp = client.post(LOGIN_URL, {"phone": phone, "password": "pass1234"})
        temp_token = login_resp.data["temp_token"]

        other_company = Company.objects.create(name="Unrelated", phone=make_phone())
        resp = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(other_company.id),
        })
        assert resp.status_code == 400

    def test_select_company_archived_user_blocked(self, company, db):
        archived_user = User.objects.create_user(
            phone=make_phone(), password="pass1234",
            first_name="Archived", last_name="User",
            role="boss", status="archived", company=company,
        )
        temp_token = signing.dumps(
            {"phone": archived_user.phone, "user_ids": [str(archived_user.id)]},
            salt="company-select",
        )

        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.post(SELECT_COMPANY_URL, {
            "temp_token": temp_token,
            "company_id": str(company.id),
        })
        assert resp.status_code == 403


@pytest.mark.django_db
class TestMultiCompanyPhoneUniqueness:
    def test_same_phone_different_companies_allowed(self, company, company2, db):
        phone = make_phone()
        User.objects.create_user(
            phone=phone, password="pass1234",
            first_name="A", last_name="A",
            role="boss", status="active", company=company,
        )
        # Same phone in a different company is allowed
        User.objects.create_user(
            phone=phone, password="pass1234",
            first_name="B", last_name="B",
            role="boss", status="active", company=company2,
        )
        assert User.objects.filter(phone=phone).count() == 2

    def test_same_phone_same_company_rejected(self, company, db):
        from django.db import IntegrityError, transaction
        phone = make_phone()
        User.objects.create_user(
            phone=phone, password="pass1234",
            first_name="A", last_name="A",
            role="boss", status="active", company=company,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    phone=phone, password="pass1234",
                    first_name="B", last_name="B",
                    role="manager", status="active", company=company,
                )
