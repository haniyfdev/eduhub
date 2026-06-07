import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.salaries.models import TeacherSalary
from apps.groups.models import Group, GroupStudent
from apps.courses.models import Course
from apps.rooms.models import Room
from apps.payments.models import Payment
from apps.teachers.models import Teacher
from apps.students.models import Student
from apps.users.models import User

TEACHER_SALARIES_URL = "/api/v1/teacher-salaries/"
THIS_MONTH = date.today().replace(day=1)

# ---------------------------------------------------------------------------
# Local helpers (avoid broken conftest `course` fixture which uses teacher=)
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


def make_group(company, course, teacher, room=None):
    if room is None:
        room = make_room(company)
    n = Group.objects.filter(company=company).count() + 1
    return Group.objects.create(
        company=company,
        course=course,
        teacher=teacher,
        room=room,
        number=n,
        gender_type="a",
        status="active",
    )


def make_gs(group, company):
    student = Student.objects.create(
        company=company,
        first_name="S", last_name="S",
        phone=_phone(),
        status="active",
    )
    return GroupStudent.objects.create(group=group, student=student, joined_at=timezone.now())


def pay(company, gs, amount, paid_at=None):
    if paid_at is None:
        paid_at = timezone.now()
    return Payment.objects.create(
        company=company,
        group_student=gs,
        amount=Decimal(str(amount)),
        payment_type="cash",
        paid_at=paid_at,
    )


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherSalaryPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        resp = admin_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(TEACHER_SALARIES_URL)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 1. Fixed salary — unaffected by payments or student count
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFixedSalary:
    def test_fixed_uses_fixed_amount(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("3000000"))
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert len(salaries) == 1
        assert salaries[0].base_amount == Decimal("3000000")
        assert salaries[0].calculated_amount == Decimal("3000000")

    def test_fixed_ignores_student_count(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        course = make_course(company)
        group = make_group(company, course, t)
        for _ in range(10):
            make_gs(group, company)
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].calculated_amount == Decimal("2000000")

    def test_fixed_ignores_payments(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        course = make_course(company)
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        pay(company, gs, Decimal("9000000"))  # large payment must not affect fixed
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].calculated_amount == Decimal("2000000")

    def test_fixed_with_kpi(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        t.kpi_bonus = Decimal("500000")
        t.save()
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].calculated_amount == Decimal("2500000")


# ---------------------------------------------------------------------------
# 2. Percent salary — actual payments × percent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPercentSalary:
    def test_percent_partial_payments(self, company):
        """12 full-paying + 8 half-paying students → actual payments × percent."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        for _ in range(12):
            gs = make_gs(group, company)
            pay(company, gs, Decimal("500000"))

        for _ in range(8):
            gs = make_gs(group, company)
            pay(company, gs, Decimal("250000"))

        salaries = calculate_teacher_salary(t, THIS_MONTH)
        total_payments = 12 * Decimal("500000") + 8 * Decimal("250000")  # 8_000_000
        expected = (total_payments * Decimal("20") / 100).quantize(Decimal("1"))
        assert salaries[0].calculated_amount == expected

    def test_percent_no_payment_gives_zero(self, company):
        """Enrolled students but no payments → salary = 0."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        for _ in range(10):
            make_gs(group, company)  # no payment
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("0")

    def test_percent_single_payment(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        pay(company, gs, Decimal("500000"))
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("100000")  # 500000 × 20%


# ---------------------------------------------------------------------------
# 3. Per-student salary — coefficient = tarif / course_price
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPerStudentSalary:
    def test_per_student_coefficient(self, company):
        """tarif=100000, course_price=500000 → coeff=0.2 → 500000 × 0.2 = 100000."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        pay(company, gs, Decimal("500000"))
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("100000")

    def test_per_student_partial_payment(self, company):
        """1 full + 1 partial (3/12 of price): total=625000, coeff=0.2, salary=125000."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)

        gs1 = make_gs(group, company)
        pay(company, gs1, Decimal("500000"))

        gs2 = make_gs(group, company)
        pay(company, gs2, Decimal("125000"))  # 3/12 × 500000

        salaries = calculate_teacher_salary(t, THIS_MONTH)
        coeff = Decimal("100000") / Decimal("500000")
        expected = (Decimal("625000") * coeff).quantize(Decimal("1"))
        assert salaries[0].base_amount == expected

    def test_per_student_no_payment_gives_zero(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        for _ in range(5):
            make_gs(group, company)  # no payments
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("0")

    def test_per_student_zero_course_price_gives_zero(self, company):
        """course_price=0 → no division, salary=0 (no ZeroDivisionError)."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("0"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        pay(company, gs, Decimal("500000"))
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("0")


# ---------------------------------------------------------------------------
# 4. Multiple groups — one salary record per group, KPI added only once
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMultipleGroups:
    def test_percent_three_groups_separate_records(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))

        group_totals = [Decimal("1000000"), Decimal("2000000"), Decimal("3000000")]
        for total_pmt in group_totals:
            course = make_course(company, price=Decimal("500000"))
            group = make_group(company, course, t)
            gs = make_gs(group, company)
            pay(company, gs, total_pmt)

        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert len(salaries) == 3

        total_salary = sum(s.calculated_amount for s in salaries)
        expected = sum(p * Decimal("20") / 100 for p in group_totals).quantize(Decimal("1"))
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
            pay(company, gs, Decimal("1000000"))

        salaries = calculate_teacher_salary(t, THIS_MONTH)
        kpi_counts = sum(1 for s in salaries if s.kpi_amount == Decimal("200000"))
        assert kpi_counts == 1


# ---------------------------------------------------------------------------
# 5. Zero payments → salary = 0 (no crash)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestZeroPayments:
    def test_percent_zero_payments(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        make_group(company, course, t)
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert len(salaries) == 1
        assert salaries[0].base_amount == Decimal("0")
        assert salaries[0].calculated_amount == Decimal("0")

    def test_per_student_zero_payments(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="per_student", per_student_amt=Decimal("100000"))
        course = make_course(company, price=Decimal("500000"))
        make_group(company, course, t)
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("0")


# ---------------------------------------------------------------------------
# 6. Billing period — payments outside window excluded
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBillingPeriod:
    def test_payment_before_month_excluded(self, company):
        """No prev salary → window starts THIS_MONTH. Last-month payment excluded."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)

        last_month_end = THIS_MONTH - timedelta(days=1)
        old_paid_at = timezone.make_aware(
            datetime.combine(last_month_end, datetime.min.time())
        )
        pay(company, gs, Decimal("500000"), paid_at=old_paid_at)

        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("0")

    def test_payment_today_included(self, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)
        pay(company, gs, Decimal("500000"))
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("100000")  # 500000 × 20%

    def test_window_starts_from_prev_salary_created_at(self, company):
        """When a prev salary exists, window starts from its created_at date."""
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="percent", percent=Decimal("20"))
        course = make_course(company, price=Decimal("500000"))
        group = make_group(company, course, t)
        gs = make_gs(group, company)

        prev_month = THIS_MONTH - relativedelta(months=1)
        prev_salary = TeacherSalary.objects.create(
            teacher=t, company=company, group=group, month=prev_month,
            base_amount=Decimal("0"), kpi_amount=Decimal("0"),
            total_amount=Decimal("0"), calculated_amount=Decimal("0"),
            carry_over=Decimal("0"), status="paid",
        )
        window_start = prev_salary.created_at.date()

        # payment before window — excluded
        before_dt = timezone.make_aware(
            datetime.combine(window_start - timedelta(days=1), datetime.min.time())
        )
        pay(company, gs, Decimal("1000000"), paid_at=before_dt)

        # payment on window_start — included
        within_dt = timezone.make_aware(
            datetime.combine(window_start, datetime.min.time())
        )
        pay(company, gs, Decimal("500000"), paid_at=within_dt)

        salaries = calculate_teacher_salary(t, THIS_MONTH)
        assert salaries[0].base_amount == Decimal("100000")  # only 500000 × 20%


# ---------------------------------------------------------------------------
# 7. Mark-paid
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMarkPaid:
    def test_mark_paid(self, boss_client, company):
        from apps.salaries.logic import calculate_teacher_salary
        t = make_teacher(company, salary_type="fixed", fixed_amount=Decimal("2000000"))
        salaries = calculate_teacher_salary(t, THIS_MONTH)
        salary = salaries[0]
        resp = boss_client.post(f"{TEACHER_SALARIES_URL}{salary.id}/mark-paid/")
        assert resp.status_code == 200
        salary.refresh_from_db()
        assert salary.paid_at is not None
