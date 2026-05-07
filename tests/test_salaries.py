import pytest
from datetime import date
from decimal import Decimal

from apps.salaries.models import TeacherSalary, StaffSalary
from apps.expenses.models import Expense

TEACHER_SALARIES_URL = "/api/v1/teacher-salaries/"
STAFF_SALARIES_URL = "/api/v1/staff-salaries/"


@pytest.mark.django_db
class TestTeacherSalaryPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        # TeacherSalaryViewSet uses IsAuthenticated() for all read actions
        resp = admin_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestSalaryCalculationFixed:
    def test_fixed_salary_calculation(self, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        teacher.salary_type = "fixed"
        teacher.fixed_amount = Decimal("2000000")
        teacher.save()

        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert salary.base_amount == Decimal("2000000")
        assert salary.total_amount == salary.base_amount + (teacher.kpi_bonus or 0)

    def test_fixed_salary_with_kpi(self, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        teacher.salary_type = "fixed"
        teacher.fixed_amount = Decimal("2000000")
        teacher.kpi_bonus = Decimal("500000")
        teacher.save()

        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert salary.total_amount == Decimal("2500000")


@pytest.mark.django_db
class TestSalaryCalculationPercent:
    def test_percent_salary_based_on_enrollments(self, company, teacher, course, group, student, group_student):
        from apps.salaries.logic import calculate_teacher_salary
        teacher.salary_type = "percent"
        teacher.salary_percent = Decimal("20")
        teacher.save()

        # 1 enrolled student × course.price 500000 × 20% = 100000
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert salary.base_amount == Decimal("100000")

    def test_percent_ignores_actual_payments(self, company, teacher, course, group, student, group_student):
        from apps.salaries.logic import calculate_teacher_salary
        # No payment made, but salary still calculated from enrollment (Rule 9)
        teacher.salary_type = "percent"
        teacher.salary_percent = Decimal("10")
        teacher.save()
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert salary.base_amount > 0


@pytest.mark.django_db
class TestSalaryCalculationPerStudent:
    def test_per_student_salary(self, company, teacher, course, group, student, group_student):
        from apps.salaries.logic import calculate_teacher_salary
        teacher.salary_type = "per_student"
        teacher.per_student_amt = Decimal("100000")
        teacher.save()

        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert salary.base_amount == Decimal("100000")  # 1 student × 100000

    def test_per_student_ignores_payments(self, company, teacher, course, group, student, group_student):
        from apps.salaries.logic import calculate_teacher_salary
        teacher.salary_type = "per_student"
        teacher.per_student_amt = Decimal("50000")
        teacher.save()
        # Salary based on enrolled students, not payments (Rule 9)
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert salary.base_amount == Decimal("50000")


@pytest.mark.django_db
class TestSalaryExpenseMirror:
    def test_teacher_salary_creates_expense(self, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        initial_count = Expense.objects.filter(company=company, category="teacher_salary").count()
        calculate_teacher_salary(teacher, date.today().replace(day=1))
        assert Expense.objects.filter(company=company, category="teacher_salary").count() == initial_count + 1

    def test_teacher_salary_expense_amount_matches(self, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        expense = Expense.objects.get(reference_id=salary.id)
        assert expense.amount == salary.total_amount

    def test_expense_source_is_auto(self, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        expense = Expense.objects.get(reference_id=salary.id)
        assert expense.source == "auto"

    def test_staff_salary_creates_expense(self, boss_client, company, boss):
        # StaffSalaryCreateSerializer uses `user` FK field directly
        resp = boss_client.post(STAFF_SALARIES_URL, {
            "user": str(boss.id),
            "month": str(date.today().replace(day=1)),
            "amount": "1000000.00",
        })
        assert resp.status_code == 201
        assert Expense.objects.filter(company=company, category="staff_salary").exists()

    def test_update_teacher_salary_does_not_create_duplicate_expense(self, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        before = Expense.objects.filter(reference_id=salary.id).count()
        # Updating salary — signal guard `if not created: return` prevents duplicate
        salary.note = "updated"
        salary.save()
        after = Expense.objects.filter(reference_id=salary.id).count()
        assert after == before


@pytest.mark.django_db
class TestTeacherSalaryMarkPaid:
    def test_mark_paid(self, boss_client, company, teacher):
        from apps.salaries.logic import calculate_teacher_salary
        salary = calculate_teacher_salary(teacher, date.today().replace(day=1))
        resp = boss_client.post(f"{TEACHER_SALARIES_URL}{salary.id}/mark-paid/")
        assert resp.status_code == 200
        salary.refresh_from_db()
        assert salary.paid_at is not None
