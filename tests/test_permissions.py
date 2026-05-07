"""
Cross-cutting permission tests: multi-tenant isolation and role access control.
"""
import pytest
from decimal import Decimal
from datetime import date

from apps.students.models import Student
from apps.groups.models import Group
from apps.teachers.models import Teacher
from apps.users.models import User
from .conftest import make_phone, auth_client

STUDENTS_URL = "/api/v1/students/"
TEACHERS_URL = "/api/v1/teachers/"
GROUPS_URL = "/api/v1/groups/"
PAYMENTS_URL = "/api/v1/payments/"
EXPENSES_URL = "/api/v1/expenses/"
TEACHER_SALARIES_URL = "/api/v1/teacher-salaries/"
STAFF_SALARIES_URL = "/api/v1/staff-salaries/"
AUDIT_LOGS_URL = "/api/v1/audit-logs/"
DEBTS_URL = "/api/v1/debts/"
DISCOUNTS_URL = "/api/v1/discounts/"


@pytest.mark.django_db
class TestMultiTenantIsolation:
    """Company A users must never see company B data."""

    def test_boss_a_cannot_see_company_b_student(self, boss_client, company2, db):
        student_b = Student.objects.create(
            company=company2, first_name="B", last_name="Student",
            phone=make_phone(), status="active"
        )
        resp = boss_client.get(f"{STUDENTS_URL}{student_b.id}/")
        assert resp.status_code in (403, 404)

    def test_boss_a_list_excludes_company_b_students(self, boss_client, company2, db):
        student_b = Student.objects.create(
            company=company2, first_name="B", last_name="Student",
            phone=make_phone(), status="active"
        )
        resp = boss_client.get(STUDENTS_URL)
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(student_b.id) not in ids

    def test_boss_a_cannot_see_company_b_teacher(self, boss_client, company2, db):
        user_b = User.objects.create_user(
            phone=make_phone(), password="pass",
            first_name="X", last_name="Y", role="teacher",
            status="active", company=company2,
        )
        teacher_b = Teacher.objects.create(
            user=user_b, company=company2, salary_type="fixed",
            fixed_amount=Decimal("1000000"), hired_at=date.today(),
        )
        resp = boss_client.get(f"{TEACHERS_URL}{teacher_b.id}/")
        assert resp.status_code in (403, 404)

    def test_superadmin_sees_all_companies(self, superadmin_client):
        from apps.companies.models import Company
        Company.objects.create(name="SA Test Co")
        resp = superadmin_client.get("/api/superadmin/companies/")
        assert resp.status_code == 200
        assert len(resp.data) >= 1


@pytest.mark.django_db
class TestRoleMatrix:
    """Actual view permissions reflect real behavior: most use IsAuthenticated."""

    def test_admin_can_list_expenses(self, admin_client):
        # ExpenseViewSet: list=IsAuthenticated, create=IsBossOrManager
        resp = admin_client.get(EXPENSES_URL)
        assert resp.status_code == 200

    def test_admin_blocked_from_create_expense(self, admin_client):
        resp = admin_client.post(EXPENSES_URL, {
            "category": "rent", "amount": "100000",
            "description": "Test", "expense_date": str(date.today()),
        })
        assert resp.status_code == 403

    def test_admin_can_read_teacher_salaries(self, admin_client):
        resp = admin_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_admin_can_read_students(self, admin_client):
        resp = admin_client.get(STUDENTS_URL)
        assert resp.status_code == 200

    def test_admin_can_read_debts(self, admin_client):
        resp = admin_client.get(DEBTS_URL)
        assert resp.status_code == 200

    def test_admin_can_read_payments(self, admin_client):
        resp = admin_client.get(PAYMENTS_URL)
        assert resp.status_code == 200

    def test_admin_blocked_from_audit(self, admin_client):
        # AuditLogViewSet uses IsSuperAdminOrBossOrManager
        resp = admin_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 403

    def test_audit_accessible_by_boss(self, boss_client):
        resp = boss_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 200

    def test_audit_accessible_by_manager(self, manager_client):
        resp = manager_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 200

    def test_audit_accessible_by_superadmin(self, superadmin_client):
        resp = superadmin_client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 200

    def test_teacher_can_read_payments(self, teacher_client):
        # PaymentViewSet uses IsAuthenticated
        resp = teacher_client.get(PAYMENTS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked_from_all(self, api_client):
        for url in [STUDENTS_URL, TEACHERS_URL, GROUPS_URL, PAYMENTS_URL, EXPENSES_URL]:
            resp = api_client.get(url)
            assert resp.status_code == 401, f"{url} should block unauthenticated"

    def test_rule4_boss_means_boss_and_manager(self, manager_client, boss_client):
        # Both boss AND manager should access discounts (IsBossOrManager)
        for client in [boss_client, manager_client]:
            resp = client.get(DISCOUNTS_URL)
            assert resp.status_code == 200


@pytest.mark.django_db
class TestCustomPermissionActiveCheck:
    """Custom permissions (IsBossOrManager, etc.) check status == 'active'."""

    def test_archived_boss_blocked_by_custom_permission(self, db, company):
        """Endpoints using IsBossOrManager check _active() which requires status='active'."""
        archived_boss = User.objects.create_user(
            phone=make_phone(), password="pass",
            first_name="Archived", last_name="Boss",
            role="boss", status="archived", company=company,
        )
        client = auth_client(archived_boss)
        # Expenses create uses IsBossOrManager which checks _active()
        resp = client.post(EXPENSES_URL, {
            "category": "rent", "amount": "100000",
            "description": "Test", "expense_date": str(date.today()),
        })
        assert resp.status_code == 403

    def test_archived_boss_blocked_from_audit(self, db, company):
        """AuditLogViewSet uses IsSuperAdminOrBossOrManager — archived boss blocked."""
        archived_boss = User.objects.create_user(
            phone=make_phone(), password="pass",
            first_name="Archived", last_name="Boss",
            role="boss", status="archived", company=company,
        )
        client = auth_client(archived_boss)
        resp = client.get(AUDIT_LOGS_URL)
        assert resp.status_code == 403
