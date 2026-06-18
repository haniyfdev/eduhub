import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.salaries.models import TeacherSalary
from apps.groups.models import Group, GroupStudent
from apps.courses.models import Course
from apps.rooms.models import Room
from apps.debts.models import Debt
from apps.teachers.models import Teacher
from apps.students.models import Student
from apps.users.models import User

TEACHER_SALARIES_URL = "/api/v1/teacher-salaries/"
THIS_MONTH = date.today().replace(day=1)
PREV_MONTH = (THIS_MONTH - relativedelta(months=1)).replace(day=1)

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _phone():
    return f"+998{uuid.uuid4().int % 10**9:09d}"


def make_room(company):
    n = Room.objects.filter(company=company).count() + 1
    return Room.objects.create(company=company, name=n, status="active")


def make_course(company, price=Decimal("500000")):
    return Course.objects.create(
        company=company,
        name="Test Course",
        price=price,
        duration_months=3,
        duration_hours=Decimal("60.0"),
        status="active",
    )


def make_teacher(company, salary_type="percent", percent=None, per_student_amt=None, fixed_amount=None):
    user = User.objects.create_user(
        phone=_phone(), password="pass1234",
        first_name="T", last_name="T",
        role="teacher", status="active", company=company,
    )
    return Teacher.objects.create(
        user=user,
        company=company,
        salary_type=salary_type,
        salary_percent=percent,
        per_student_amt=per_student_amt,
        fixed_amount=fixed_amount,
        hired_at=date.today(),
        status="active",
    )


def make_group(company, course, teacher):
    room = make_room(company)
    n = Group.objects.filter(company=company).count() + 1
    return Group.objects.create(
        company=company, course=course, teacher=teacher, room=room,
        number=n, gender_type="a", status="active",
    )


def make_gs(group, company):
    """Creates a trial GroupStudent — no auto-debt signal fires."""
    student = Student.objects.create(
        company=company, first_name="S", last_name="S",
        phone=_phone(), status="active",
    )
    # status defaults to 'trial' → create_debt_on_enrollment signal skips it
    return GroupStudent.objects.create(group=group, student=student, joined_at=timezone.now())


def make_debt(company, gs, amount, month=None, billing_month=None):
    """Create a debt whose due_date falls in the given billing month."""
    if month is None:
        month = THIS_MONTH
    due = date(month.year, month.month, 15)
    return Debt.objects.create(
        company=company,
        group_student=gs,
        amount=Decimal(str(amount)),
        due_date=due,
        billing_month=billing_month,
        status="unpaid",
    )


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherSalaryPermissions:
    def test_boss_can_list(self, boss_client):
        assert boss_client.get(TEACHER_SALARIES_URL).status_code == 200

    def test_manager_can_list(self, manager_client):
        assert manager_client.get(TEACHER_SALARIES_URL).status_code == 200

    def test_admin_can_list(self, admin_client):
        assert admin_client.get(TEACHER_SALARIES_URL).status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        assert api_client.get(TEACHER_SALARIES_URL).status_code == 401


# ---------------------------------------------------------------------------
# 1. Fixed salary — debt records do not affect result
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFixedSalary:
    def test_fixed_uses_fixed_amount(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("3000000"))
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert len(s) == 1
        assert s[0].base_amount == Decimal("3000000")
        assert s[0].calculated_amount == Decimal("3000000")

    def test_fixed_ignores_debts(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        course = make_course(company)
        group = make_group(company, course, t)
        for _ in range(10):
            gs = make_gs(group, company)
            make_debt(company, gs, Decimal("500000"))
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].calculated_amount == Decimal("2000000")

    def test_fixed_with_kpi(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        t.kpi_bonus = Decimal("500000")
        t.save()
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].calculated_amount == Decimal("2500000")


# ---------------------------------------------------------------------------
# 2. Percent — full debt sum (paid + unpaid students both counted)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPercentSalaryDebts:
    def test_percent_full_debt_sum_regardless_of_payment_status(self, company):
        """20 students owe debt; 10 paid, 10 didn't.
        Teacher salary = full debt sum × percent (status doesn't matter)."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        for _ in range(10):
            gs = make_gs(group, company)
            d = make_debt(company, gs, Decimal("500000"))
            d.status = "paid"
            d.save(update_fields=["status"])

        for _ in range(10):
            gs = make_gs(group, company)
            make_debt(company, gs, Decimal("500000"))

        s = calculate_teacher_salary(t, THIS_MONTH)
        total_debt = 20 * Decimal("500000")
        expected = (total_debt * Decimal("20") / 100).quantize(Decimal("1"))
        assert s[0].base_amount == expected

    def test_percent_partial_debt_mid_month_join(self, company):
        """Some students joined mid-month and owe a partial debt amount.
        Salary reflects the actual debt amount, not full course price."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        # 10 full-month students
        for _ in range(10):
            gs = make_gs(group, company)
            make_debt(company, gs, Decimal("500000"))

        # 5 mid-month joiners — prorated debt (half price)
        for _ in range(5):
            gs = make_gs(group, company)
            make_debt(company, gs, Decimal("250000"))

        s = calculate_teacher_salary(t, THIS_MONTH)
        total_debt = 10 * Decimal("500000") + 5 * Decimal("250000")  # 6_250_000
        expected = (total_debt * Decimal("20") / 100).quantize(Decimal("1"))
        assert s[0].base_amount == expected

    def test_percent_no_debts_gives_zero(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        for _ in range(5):
            make_gs(group, company)  # no debt
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("0")


# ---------------------------------------------------------------------------
# 3. Per-student — coefficient = tarif / course_price, applied to debt sum
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPerStudentSalaryDebts:
    def test_per_student_coefficient_full_debt(self, company):
        """tarif=100000, course_price=500000 → coeff=0.2.
        One full debt of 500000 → salary = 100000."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        make_debt(company, gs, Decimal("500000"))
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("100000")

    def test_per_student_partial_debt(self, company):
        """1 full debt + 1 partial debt (half price).
        total_debt=750000, coeff=0.2, salary=150000."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        gs1 = make_gs(group, company)
        make_debt(company, gs1, Decimal("500000"))

        gs2 = make_gs(group, company)
        make_debt(company, gs2, Decimal("250000"))

        s = calculate_teacher_salary(t, THIS_MONTH)
        coeff = Decimal("100000") / Decimal("500000")
        expected = (Decimal("750000") * coeff).quantize(Decimal("1"))
        assert s[0].base_amount == expected

    def test_per_student_zero_course_price_gives_zero(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("0"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        make_debt(company, gs, Decimal("500000"))
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("0")


# ---------------------------------------------------------------------------
# 4. Multiple groups — each group's debt calculated separately, then summed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMultipleGroups:
    def test_percent_three_groups_separate_records(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))

        group_debts = [Decimal("1000000"), Decimal("2000000"), Decimal("3000000")]
        for debt_total in group_debts:
            course = make_course(company, price=Decimal("500000"))
            group = make_group(company, course, t)
            gs = make_gs(group, company)
            make_debt(company, gs, debt_total)

        s = calculate_teacher_salary(t, THIS_MONTH)
        assert len(s) == 3

        total_salary = sum(x.calculated_amount for x in s)
        expected = sum(d * Decimal("20") / 100 for d in group_debts).quantize(Decimal("1"))
        assert total_salary == expected

    def test_kpi_added_only_to_first_group(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        t.kpi_bonus = Decimal("200000")
        t.save()

        for _ in range(2):
            course = make_course(company, price=Decimal("500000"))
            group = make_group(company, course, t)
            gs = make_gs(group, company)
            make_debt(company, gs, Decimal("1000000"))

        s = calculate_teacher_salary(t, THIS_MONTH)
        kpi_counts = sum(1 for x in s if x.kpi_amount == Decimal("200000"))
        assert kpi_counts == 1


# ---------------------------------------------------------------------------
# 5. Edge — zero debt in group → salary = 0
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestZeroDebt:
    def test_percent_zero_debt(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        make_group(company, course, t)
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert len(s) == 1
        assert s[0].base_amount == Decimal("0")
        assert s[0].calculated_amount == Decimal("0")

    def test_per_student_zero_debt(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        make_group(company, course, t)
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("0")


# ---------------------------------------------------------------------------
# 6. Edge — previous-month debt must NOT be included
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDebtMonthFilter:
    def test_prev_month_debt_excluded(self, company):
        """Debt with due_date in the previous month must not count."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        make_debt(company, gs, Decimal("500000"), month=PREV_MONTH)  # wrong month
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("0")

    def test_current_month_debt_included(self, company):
        """Debt with due_date in the current billing month is included."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        make_debt(company, gs, Decimal("500000"), month=THIS_MONTH)
        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("100000")  # 500000 × 20%

    def test_only_current_month_debt_counted_when_both_exist(self, company):
        """Two students: one has a debt this month, another has debt last month only.
        Only the current-month debt counts."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        gs1 = make_gs(group, company)
        make_debt(company, gs1, Decimal("500000"), month=THIS_MONTH)

        gs2 = make_gs(group, company)
        make_debt(company, gs2, Decimal("500000"), month=PREV_MONTH)

        s = calculate_teacher_salary(t, THIS_MONTH)
        assert s[0].base_amount == Decimal("100000")  # only gs1's debt × 20%


# ---------------------------------------------------------------------------
# 7. Edge — archived student's debt still counts
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestArchivedStudentDebt:
    def test_archived_student_debt_counted(self, company):
        """Student archived mid-month (left_at set) — their debt was already created
        and still counts toward teacher salary for that month."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        # Active student with debt
        gs_active = make_gs(group, company)
        make_debt(company, gs_active, Decimal("500000"))

        # Archived student (left mid-month) — debt still exists
        gs_left = make_gs(group, company)
        gs_left.left_at = timezone.now()
        gs_left.status = "left"
        gs_left.save(update_fields=["left_at", "status"])
        make_debt(company, gs_left, Decimal("500000"))

        s = calculate_teacher_salary(t, THIS_MONTH)
        total_debt = Decimal("1000000")
        expected = (total_debt * Decimal("20") / 100).quantize(Decimal("1"))
        assert s[0].base_amount == expected


# ---------------------------------------------------------------------------
# Mark-paid
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMarkPaid:
    def test_mark_paid(self, boss_client, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        s = calculate_teacher_salary(t, THIS_MONTH)
        salary = s[0]
        resp = boss_client.post(f"{TEACHER_SALARIES_URL}{salary.id}/mark-paid/")
        assert resp.status_code == 200
        salary.refresh_from_db()
        assert salary.paid_at is not None


# ---------------------------------------------------------------------------
# Billing-month rollover regression
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBillingMonthRollover:
    """Debts rolled by the scheduler get a billing_month set to the original
    billing cycle (before rolling).  Salary for that earlier month must still
    be non-zero even though due_date has moved to the next month."""

    def test_rolled_debt_counted_in_original_billing_month(self, company):
        """Debt created for June, rolled to July (due_date in July, billing_month=June).
        calculate_teacher_salary for June must find it; July must not."""
        from apps.salaries.logic import calculate_teacher_salary

        billing_june = date(THIS_MONTH.year, THIS_MONTH.month, 1)
        next_month = (billing_june + relativedelta(months=1)).replace(day=1)

        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)

        # Debt was billed for THIS_MONTH but due_date rolled into next month.
        # billing_month records the original billing cycle.
        due_in_next_month = date(next_month.year, next_month.month, 15)
        Debt.objects.create(
            company=company,
            group_student=gs,
            amount=Decimal("500000"),
            due_date=due_in_next_month,
            billing_month=billing_june,
            status="unpaid",
        )

        salaries_this = calculate_teacher_salary(t, billing_june)
        salaries_next = calculate_teacher_salary(t, next_month)

        assert salaries_this, "Expected a salary record for billing_june"
        assert salaries_this[0].base_amount == Decimal("100000"), (
            f"Expected 500000 × 20% = 100000, got {salaries_this[0].base_amount}"
        )

        # Next month has no debts billed to it, so it should produce zero/no record.
        if salaries_next:
            assert salaries_next[0].base_amount == Decimal("0"), (
                f"Next month should have no contribution, got {salaries_next[0].base_amount}"
            )
