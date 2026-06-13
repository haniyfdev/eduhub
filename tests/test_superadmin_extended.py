import pytest
from datetime import date, timedelta
from decimal import Decimal

from apps.superadmin_panel.models import SubscriptionPlan, CompanySubscriptionDebt, CompanySubscriptionPayment
from apps.users.models import User
from .conftest import make_phone

SUPERADMIN_COMPANIES_URL = "/api/superadmin/companies/"
SUPERADMIN_DEBTS_URL = "/api/superadmin/debts/"
SUPERADMIN_PAYMENTS_URL = "/api/superadmin/payments/"
SUPERADMIN_PLAN_URL = "/api/superadmin/plan/"
SUPERADMIN_DASHBOARD_URL = "/api/superadmin/dashboard/"
SUPERADMIN_BROADCAST_URL = "/api/superadmin/broadcast/"


@pytest.mark.django_db
class TestSuperadminCompanyDetail:
    def test_get_company_detail(self, superadmin_client, company, student, pending_student):
        resp = superadmin_client.get(f"{SUPERADMIN_COMPANIES_URL}{company.id}/")
        assert resp.status_code == 200
        assert resp.data["id"] == str(company.id)
        assert "total_students" in resp.data
        assert "active_students" in resp.data
        assert resp.data["active_students"] >= 1

    def test_boss_blocked_from_company_detail(self, boss_client, company):
        resp = boss_client.get(f"{SUPERADMIN_COMPANIES_URL}{company.id}/")
        assert resp.status_code == 403

    def test_company_detail_404_for_unknown_company(self, superadmin_client, db):
        resp = superadmin_client.get(f"{SUPERADMIN_COMPANIES_URL}00000000-0000-0000-0000-000000000000/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestSuperadminCreateBoss:
    def test_create_boss(self, superadmin_client, company):
        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/create-boss/", {
            "first_name": "New",
            "last_name": "Boss",
            "phone": make_phone(),
            "password": "pass1234",
        })
        assert resp.status_code == 201
        assert resp.data["role"] == "boss"
        assert User.objects.filter(id=resp.data["id"], company=company, role="boss").exists()

    def test_create_boss_missing_fields(self, superadmin_client, company):
        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/create-boss/", {
            "first_name": "New",
        })
        assert resp.status_code == 400

    def test_create_boss_duplicate_phone_rejected(self, superadmin_client, company, boss):
        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/create-boss/", {
            "first_name": "Dup",
            "last_name": "Boss",
            "phone": boss.phone,
            "password": "pass1234",
        })
        assert resp.status_code == 400

    def test_boss_blocked_from_create_boss(self, boss_client, company):
        resp = boss_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/create-boss/", {
            "first_name": "New", "last_name": "Boss",
            "phone": make_phone(), "password": "pass1234",
        })
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSuperadminCompanyArchiveUnarchive:
    def test_archive_company_cascades(self, superadmin_client, superadmin, company, boss, group_student):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )

        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/archive/")
        assert resp.status_code == 200
        assert resp.data["status"] == "archived"

        company.refresh_from_db()
        assert company.status == "archived"
        assert company.archived_at is not None

        boss.refresh_from_db()
        assert boss.is_active is False

        group_student.refresh_from_db()
        assert group_student.status == "left"
        assert group_student.left_at is not None

        debt.refresh_from_db()
        assert debt.status == "overdue"

        from apps.superadmin_panel.models import SuperadminLog
        assert SuperadminLog.objects.filter(user=superadmin, action="archive").exists()

    def test_archive_already_archived_returns_400(self, superadmin_client, company):
        company.status = "archived"
        company.save()
        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/archive/")
        assert resp.status_code == 400

    def test_unarchive_company(self, superadmin_client, superadmin, company, boss):
        company.status = "archived"
        company.save()
        User.objects.filter(company=company).update(is_active=False)

        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/unarchive/")
        assert resp.status_code == 200
        assert resp.data["status"] == "active"

        company.refresh_from_db()
        assert company.status == "active"
        assert company.archived_at is None

        boss.refresh_from_db()
        assert boss.is_active is True

    def test_unarchive_non_archived_returns_400(self, superadmin_client, company):
        resp = superadmin_client.post(f"{SUPERADMIN_COMPANIES_URL}{company.id}/unarchive/")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestSuperadminDebts:
    def test_list_debts(self, superadmin_client, company):
        CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.get(SUPERADMIN_DEBTS_URL)
        assert resp.status_code == 200
        assert len(resp.data) >= 1

    def test_filter_debts_by_status(self, superadmin_client, company):
        CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="overdue",
        )
        resp = superadmin_client.get(f"{SUPERADMIN_DEBTS_URL}?status=overdue")
        assert resp.status_code == 200
        assert all(d["company_id"] for d in resp.data)
        for d in resp.data:
            assert CompanySubscriptionDebt.objects.get(id=d["id"]).status == "overdue"

    def test_filter_debts_by_company(self, superadmin_client, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.get(f"{SUPERADMIN_DEBTS_URL}?company={company.id}")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.data]
        assert debt.id in ids

    def test_boss_blocked_from_debts(self, boss_client):
        resp = boss_client.get(SUPERADMIN_DEBTS_URL)
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSuperadminDebtPay:
    def test_pay_partial(self, superadmin_client, superadmin, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.post(f"{SUPERADMIN_DEBTS_URL}{debt.id}/pay/", {
            "amount": "200000", "payment_method": "cash",
        })
        assert resp.status_code == 200
        debt.refresh_from_db()
        assert debt.status == "partial"
        assert CompanySubscriptionPayment.objects.filter(debt=debt, amount=Decimal("200000")).exists()

    def test_pay_in_full_marks_paid(self, superadmin_client, superadmin, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.post(f"{SUPERADMIN_DEBTS_URL}{debt.id}/pay/", {
            "amount": "500000", "payment_method": "card",
        })
        assert resp.status_code == 200
        debt.refresh_from_db()
        assert debt.status == "paid"

    def test_pay_already_paid_returns_400(self, superadmin_client, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="paid",
        )
        resp = superadmin_client.post(f"{SUPERADMIN_DEBTS_URL}{debt.id}/pay/", {"amount": "1000"})
        assert resp.status_code == 400

    def test_pay_exceeding_remaining_returns_400(self, superadmin_client, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.post(f"{SUPERADMIN_DEBTS_URL}{debt.id}/pay/", {"amount": "600000"})
        assert resp.status_code == 400

    def test_pay_negative_amount_returns_400(self, superadmin_client, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.post(f"{SUPERADMIN_DEBTS_URL}{debt.id}/pay/", {"amount": "-100"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestSuperadminDebtDetail:
    def test_patch_debt_amount(self, superadmin_client, company):
        SubscriptionPlan.objects.all().delete()
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.patch(f"{SUPERADMIN_DEBTS_URL}{debt.id}/", {"amount": "600000"})
        assert resp.status_code == 200
        debt.refresh_from_db()
        assert debt.amount == Decimal("600000")

    def test_patch_amount_below_minimum_rejected(self, superadmin_client, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        resp = superadmin_client.patch(f"{SUPERADMIN_DEBTS_URL}{debt.id}/", {"amount": "5000"})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestSuperadminPayments:
    def test_list_payments(self, superadmin_client, superadmin, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        CompanySubscriptionPayment.objects.create(
            company=company, debt=debt, amount=Decimal("100000"),
            payment_method="cash", recorded_by=superadmin,
        )
        resp = superadmin_client.get(SUPERADMIN_PAYMENTS_URL)
        assert resp.status_code == 200
        assert len(resp.data) >= 1

    def test_search_payments_by_company_name(self, superadmin_client, superadmin, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("500000"),
            period_start=date.today(), period_end=date.today() + timedelta(days=30),
            status="pending",
        )
        CompanySubscriptionPayment.objects.create(
            company=company, debt=debt, amount=Decimal("100000"),
            payment_method="cash", recorded_by=superadmin,
        )
        resp = superadmin_client.get(f"{SUPERADMIN_PAYMENTS_URL}?search={company.name}")
        assert resp.status_code == 200
        assert all(p["company_name"] == company.name for p in resp.data)

    def test_boss_blocked_from_payments(self, boss_client):
        resp = boss_client.get(SUPERADMIN_PAYMENTS_URL)
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSuperadminPlan:
    def test_get_plan_when_none_exists(self, superadmin_client, db):
        SubscriptionPlan.objects.all().delete()
        resp = superadmin_client.get(SUPERADMIN_PLAN_URL)
        assert resp.status_code == 200
        assert resp.data["price"] is None

    def test_put_creates_plan(self, superadmin_client, superadmin, db):
        resp = superadmin_client.put(SUPERADMIN_PLAN_URL, {"price": "300000"})
        assert resp.status_code == 200
        assert SubscriptionPlan.objects.count() == 1
        plan = SubscriptionPlan.objects.first()
        assert plan.price == Decimal("300000")
        assert plan.updated_by == superadmin

    def test_put_updates_existing_plan(self, superadmin_client, superadmin, db):
        SubscriptionPlan.objects.all().delete()
        SubscriptionPlan.objects.create(price=Decimal("100000"))
        resp = superadmin_client.put(SUPERADMIN_PLAN_URL, {"price": "400000"})
        assert resp.status_code == 200
        assert SubscriptionPlan.objects.count() == 1
        plan = SubscriptionPlan.objects.first()
        assert plan.price == Decimal("400000")

    def test_put_invalid_price_rejected(self, superadmin_client, db):
        resp = superadmin_client.put(SUPERADMIN_PLAN_URL, {"price": "-100"})
        assert resp.status_code == 400

    def test_boss_blocked_from_plan(self, boss_client):
        resp = boss_client.get(SUPERADMIN_PLAN_URL)
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSuperadminDashboard:
    def test_dashboard_returns_stats(self, superadmin_client, company, student):
        resp = superadmin_client.get(SUPERADMIN_DASHBOARD_URL)
        assert resp.status_code == 200
        assert "stats" in resp.data
        assert "revenue_trend" in resp.data
        assert "companies_table" in resp.data
        assert resp.data["stats"]["total_active_students"] >= 1
        assert len(resp.data["revenue_trend"]) == 30

    def test_dashboard_companies_table_contains_company(self, superadmin_client, company, student):
        resp = superadmin_client.get(SUPERADMIN_DASHBOARD_URL)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.data["companies_table"]]
        assert str(company.id) in ids

    def test_dashboard_with_date_range(self, superadmin_client, company):
        date_from = date.today().replace(day=1).isoformat()
        date_to = date.today().isoformat()
        resp = superadmin_client.get(f"{SUPERADMIN_DASHBOARD_URL}?date_from={date_from}&date_to={date_to}")
        assert resp.status_code == 200
        assert "period_revenue" in resp.data["stats"]

    def test_boss_blocked_from_dashboard(self, boss_client):
        resp = boss_client.get(SUPERADMIN_DASHBOARD_URL)
        assert resp.status_code == 403


@pytest.mark.django_db
class TestSuperadminBroadcast:
    def test_broadcast_requires_message(self, superadmin_client, db):
        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": ""})
        assert resp.status_code == 400

    def test_broadcast_with_no_telegram_users_queues_zero(self, superadmin_client, student, boss, db):
        resp = superadmin_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Hello everyone"})
        assert resp.status_code == 200
        assert resp.data["queued"] == 0

    def test_boss_blocked_from_broadcast(self, boss_client):
        resp = boss_client.post(SUPERADMIN_BROADCAST_URL, {"message": "Hi"})
        assert resp.status_code == 403
