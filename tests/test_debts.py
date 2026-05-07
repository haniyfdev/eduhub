import pytest
from datetime import date, timedelta
from decimal import Decimal

from apps.debts.models import Debt
from apps.students.models import Student
from .conftest import make_phone

DEBTS_URL = "/api/v1/debts/"


@pytest.mark.django_db
class TestDebtPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(DEBTS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(DEBTS_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        resp = admin_client.get(DEBTS_URL)
        assert resp.status_code == 200

    def test_teacher_can_list(self, teacher_client):
        # DebtViewSet uses IsAuthenticated() for all actions
        resp = teacher_client.get(DEBTS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(DEBTS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestDebtOperations:
    def test_list_debts(self, boss_client, debt):
        resp = boss_client.get(DEBTS_URL)
        assert resp.status_code == 200
        assert len(resp.data.get("results", resp.data)) >= 1

    def test_retrieve_debt(self, boss_client, debt):
        resp = boss_client.get(f"{DEBTS_URL}{debt.id}/")
        assert resp.status_code == 200
        assert resp.data["id"] == str(debt.id)

    def test_cross_company_debt_blocked(self, boss_client, company2, db):
        other_student = Student.objects.create(
            company=company2, first_name="X", last_name="Y",
            phone=make_phone(), status="active"
        )
        other_debt = Debt.objects.create(
            company=company2, student=other_student,
            amount=Decimal("100000"),
            due_date=date.today() + timedelta(days=30),
            status="unpaid",
        )
        resp = boss_client.get(f"{DEBTS_URL}{other_debt.id}/")
        assert resp.status_code in (403, 404)

    def test_filter_by_status(self, boss_client, debt):
        resp = boss_client.get(f"{DEBTS_URL}?status=unpaid")
        assert resp.status_code == 200

    def test_send_sms_no_template_returns_404(self, boss_client, debt):
        # No SmsTemplate with type='debt' created — view returns 404
        resp = boss_client.post(f"{DEBTS_URL}{debt.id}/send-sms/")
        assert resp.status_code == 404

    def test_send_sms_with_template(self, boss_client, debt, company):
        from apps.notifications.models import SmsTemplate
        SmsTemplate.objects.create(
            company=company, name="Debt SMS", type="debt",
            body="Dear {student_name}, you owe {amount}."
        )
        resp = boss_client.post(f"{DEBTS_URL}{debt.id}/send-sms/")
        # Student has phone — should queue SMS
        assert resp.status_code == 200


@pytest.mark.django_db
class TestAssignMonthlyDebts:
    def test_assign_monthly_debts_task(self, company, student, group, group_student, course, db):
        from apps.debts.tasks import assign_monthly_debts
        assign_monthly_debts(str(company.id))
        assert Debt.objects.filter(student=student, company=company).exists()

    def test_assign_monthly_debts_idempotent(self, company, student, group, group_student, course, db):
        from apps.debts.tasks import assign_monthly_debts
        assign_monthly_debts(str(company.id))
        assign_monthly_debts(str(company.id))
        assert Debt.objects.filter(student=student, company=company).count() == 1
