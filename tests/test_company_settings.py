"""
Tests for CompanySettings and business logic variants:
  - billing_type (monthly / per_lesson / upfront) in assign_monthly_debts
  - absent_policy (ignore / deduct / penalty) in attendance
  - teacher_contract_break_policy (full / prorate / none) in salary calculation
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.companies.models import CompanySettings
from apps.groups.models import GroupStudent
from apps.debts.models import Debt
from apps.debts.tasks import assign_monthly_debts
from apps.attendance.models import Attendance
from apps.lessons.models import Lesson
from apps.salaries.logic import calculate_teacher_salary
from apps.teachers.models import Teacher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def settings(db, company):
    return CompanySettings.objects.create(company=company)


@pytest.fixture
def lesson(db, group, teacher):
    return Lesson.objects.create(
        group=group,
        teacher=teacher,
        topic='Test Lesson',
        date=date.today(),
    )


# ---------------------------------------------------------------------------
# CompanySettings API
# ---------------------------------------------------------------------------

class TestCompanySettingsAPI:
    def test_get_my_settings_creates_if_missing(self, db, boss_client):
        res = boss_client.get('/api/v1/company-settings/my/')
        assert res.status_code == 200
        assert res.data['billing_type'] == 'monthly'
        assert res.data['absent_policy'] == 'ignore'
        assert res.data['teacher_contract_break_policy'] == 'full'

    def test_patch_my_settings(self, db, boss_client, settings):
        res = boss_client.patch('/api/v1/company-settings/my/', {
            'billing_type': 'per_lesson',
            'absent_policy': 'deduct',
            'teacher_contract_break_policy': 'per_day',
        })
        assert res.status_code == 200
        assert res.data['billing_type'] == 'per_lesson'
        assert res.data['absent_policy'] == 'deduct'
        assert res.data['teacher_contract_break_policy'] == 'per_day'

    def test_manager_can_patch(self, db, manager_client, settings):
        res = manager_client.patch('/api/v1/company-settings/my/', {'billing_type': 'upfront'})
        assert res.status_code == 200
        assert res.data['billing_type'] == 'upfront'

    def test_admin_cannot_access(self, db, admin_client):
        res = admin_client.get('/api/v1/company-settings/my/')
        assert res.status_code == 403

    def test_teacher_cannot_access(self, db, teacher_client):
        res = teacher_client.get('/api/v1/company-settings/my/')
        assert res.status_code == 403

    def test_superadmin_gets_400_for_my(self, db, superadmin_client):
        res = superadmin_client.get('/api/v1/company-settings/my/')
        assert res.status_code == 200
        assert res.data == {
            'billing_type': 'monthly',
            'absent_policy': 'ignore',
            'teacher_contract_break_policy': 'full',
        }


# ---------------------------------------------------------------------------
# billing_type variants in assign_monthly_debts
# ---------------------------------------------------------------------------

class TestBillingTypeVariants:
    def test_monthly_billing_charges_full_price(self, db, company, group_student, settings, course):
        settings.billing_type = 'monthly'
        settings.save()

        group_student.status = 'active'
        group_student.save()

        assign_monthly_debts(str(company.id))

        debt = Debt.objects.get(group_student__student=group_student.student, company=company)
        assert debt.amount == course.price

    def test_per_lesson_billing_charges_by_attendance(self, db, company, group_student, settings, course, lesson):
        settings.billing_type = 'per_lesson'
        settings.save()

        group_student.status = 'active'
        group_student.save()

        # Record 10 attended lessons
        for i in range(10):
            day = date.today() - timedelta(days=i)
            l = Lesson.objects.create(
                group=group_student.group,
                teacher=group_student.group.teacher,
                topic=f'Lesson {i}',
                date=day,
            )
            Attendance.objects.create(
                lesson=l, student=group_student.student, status='present'
            )

        assign_monthly_debts(str(company.id))

        debt = Debt.objects.get(group_student__student=group_student.student, company=company)
        expected = (course.price / Decimal('20')) * 10
        assert debt.amount == expected

    def test_upfront_billing_charges_full_course_on_new_enrollment(
        self, db, company, group_student, settings, course
    ):
        settings.billing_type = 'upfront'
        settings.save()

        group_student.status = 'active'
        group_student.save()

        # enrolled within last 30 days (fixture joins today)
        assign_monthly_debts(str(company.id))

        debt = Debt.objects.get(group_student__student=group_student.student, company=company)
        assert debt.amount == course.price * course.duration_months

    def test_upfront_billing_skips_existing_enrollment(
        self, db, company, group, student, settings, course
    ):
        settings.billing_type = 'upfront'
        settings.save()

        # Enroll student 60 days ago — outside billing window
        old_gs = GroupStudent.objects.create(
            group=group,
            student=student,
            joined_at=timezone.now() - timedelta(days=60),
        )

        assign_monthly_debts(str(company.id))

        # Should NOT create any debt since enrollment is outside the 30-day window
        assert not Debt.objects.filter(group_student__student=student, company=company).exists()


# ---------------------------------------------------------------------------
# absent_policy variants
# ---------------------------------------------------------------------------

class TestAbsentPolicyVariants:
    def test_ignore_policy_no_debt_change(self, db, company, group_student, debt, lesson, settings):
        settings.absent_policy = 'ignore'
        settings.save()

        original_amount = debt.amount
        Attendance.objects.create(
            lesson=lesson, student=group_student.student, status='absent'
        )

        debt.refresh_from_db()
        assert debt.amount == original_amount

    def test_deduct_policy_reduces_debt_on_absence(self, db, company, group_student, debt, lesson, settings, course):
        settings.absent_policy = 'deduct'
        settings.save()

        original_amount = debt.amount
        Attendance.objects.create(
            lesson=lesson, student=group_student.student, status='absent'
        )

        debt.refresh_from_db()
        lesson_price = course.price / Decimal('20')
        assert debt.amount == original_amount - lesson_price

    def test_penalty_policy_increases_debt_on_absence(self, db, company, group_student, debt, lesson, settings, course):
        settings.absent_policy = 'penalty'
        settings.save()

        original_amount = debt.amount
        Attendance.objects.create(
            lesson=lesson, student=group_student.student, status='absent'
        )

        debt.refresh_from_db()
        lesson_price = course.price / Decimal('20')
        penalty = lesson_price * Decimal('0.05')
        assert debt.amount == original_amount + penalty

    def test_present_status_never_triggers_policy(self, db, company, group_student, debt, lesson, settings):
        settings.absent_policy = 'deduct'
        settings.save()

        original_amount = debt.amount
        Attendance.objects.create(
            lesson=lesson, student=group_student.student, status='present'
        )

        debt.refresh_from_db()
        assert debt.amount == original_amount


# ---------------------------------------------------------------------------
# teacher_contract_break_policy variants
# ---------------------------------------------------------------------------

class TestTeacherContractBreakPolicy:
    def _make_archived_teacher(self, company, teacher_user, month):
        """Create a teacher who was archived mid-month."""
        archived_dt = timezone.make_aware(
            timezone.datetime(month.year, month.month, 15, 12, 0, 0)
        )
        t = Teacher.objects.create(
            user=teacher_user,
            company=company,
            salary_type='fixed',
            fixed_amount=Decimal('2000000'),
            hired_at=date(month.year, month.month, 1),
            status='archived',
            archived_at=archived_dt,
        )
        return t

    def test_full_policy_pays_complete_salary(self, db, company, teacher_user, settings):
        settings.teacher_contract_break_policy = 'full'
        settings.save()

        month = date.today().replace(day=1)
        teacher = self._make_archived_teacher(company, teacher_user, month)
        salary = calculate_teacher_salary(teacher, month)[0]

        assert salary.total_amount == Decimal('2000000')

    def test_prorate_policy_pays_partial_salary(self, db, company, teacher_user, settings):
        settings.teacher_contract_break_policy = 'prorate'
        settings.save()

        month = date.today().replace(day=1)
        teacher = self._make_archived_teacher(company, teacher_user, month)
        salary = calculate_teacher_salary(teacher, month)[0]

        # days worked = 15 - 1 = 14 days (from month start to archived_at day)
        days_worked = (teacher.archived_at.date() - month).days
        expected = Decimal('2000000') * (Decimal(days_worked) / Decimal('30'))
        assert salary.total_amount == expected

    def test_none_policy_pays_zero_salary(self, db, company, teacher_user, settings):
        settings.teacher_contract_break_policy = 'none'
        settings.save()

        month = date.today().replace(day=1)
        teacher = self._make_archived_teacher(company, teacher_user, month)
        salary = calculate_teacher_salary(teacher, month)[0]

        assert salary.total_amount == Decimal('0')
        assert salary.base_amount == Decimal('0')

    def test_active_teacher_always_gets_full_salary(self, db, company, teacher, settings):
        settings.teacher_contract_break_policy = 'none'
        settings.save()

        month = date.today().replace(day=1)
        salary = calculate_teacher_salary(teacher, month)[0]

        # Active teacher should always be paid regardless of policy
        assert salary.total_amount == Decimal('2000000')
