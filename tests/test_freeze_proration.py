"""Tests for debt proration when a group or individual student is frozen.

Coverage:
- Group freeze with per_lesson billing prorates debt correctly
- Group freeze with per_day billing prorates debt correctly
- Group freeze with manual billing leaves debt unchanged
- Group freeze does not overwrite a confirmed debt
- Group freeze creates a new debt when none exists (per_lesson)
- Individual student freeze with per_lesson billing prorates debt
- Scheduler excludes individually-frozen students from debt generation
- Scheduler still bills active (non-frozen) students (sanity check)
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pytest
from django.utils import timezone

from apps.attendance.models import Attendance
from apps.companies.models import CompanySettings
from apps.debts.models import Debt
from apps.lessons.models import Lesson
from apps.scheduler.jobs import assign_monthly_student_debts

GROUPS_URL = "/api/v1/groups/"
STUDENTS_URL = "/api/v1/students/"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_lessons(group, teacher, n_total):
    """Create n_total finished lessons for group in the current month (all <= today)."""
    today = date.today()
    month_start = today.replace(day=1)
    lessons = []
    for i in range(n_total):
        lesson_date = month_start + timedelta(days=i)
        if lesson_date > today:
            lesson_date = today
        lessons.append(Lesson.objects.create(
            group=group,
            teacher=teacher,
            topic=f"Lesson {i + 1}",
            date=lesson_date,
            status='finished',
        ))
    return lessons


def _mark_attended(lessons, student, n_attended):
    """Mark the first n_attended lessons as 'present' for student."""
    for lesson in lessons[:n_attended]:
        Attendance.objects.create(lesson=lesson, student=student, status='present')


@pytest.fixture
def company_settings(db, company):
    settings, _ = CompanySettings.objects.get_or_create(company=company)
    return settings


# ---------------------------------------------------------------------------
# Group freeze — proration modes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGroupFreezeProratesDebt:

    def test_per_lesson_updates_debt_amount(
        self, boss_client, group, student, group_student, debt, course, teacher, company_settings,
    ):
        """per_lesson: debt.amount = price / total_lessons * attended."""
        company_settings.freeze_billing_type = 'per_lesson'
        company_settings.save()
        group_student.status = 'active'
        group_student.save()

        total = 10
        attended = 4
        lessons = _make_lessons(group, teacher, total)
        _mark_attended(lessons, student, attended)

        resp = boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")
        assert resp.status_code == 200

        debt.refresh_from_db()
        expected = (Decimal(str(course.price)) / total * attended).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert debt.amount == expected

    def test_per_day_updates_debt_amount(
        self, boss_client, group, student, group_student, debt, course, company_settings,
    ):
        """per_day: debt.amount = price / days_in_month * days_active."""
        company_settings.freeze_billing_type = 'per_day'
        company_settings.save()
        group_student.status = 'active'
        today = date.today()
        month_start = today.replace(day=1)
        group_student.joined_at = timezone.make_aware(
            timezone.datetime(month_start.year, month_start.month, month_start.day)
        )
        group_student.save()

        resp = boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")
        assert resp.status_code == 200

        debt.refresh_from_db()
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_in_group = (today - month_start).days + 1
        expected = (Decimal(str(course.price)) / days_in_month * days_in_group).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert debt.amount == expected

    def test_manual_leaves_debt_unchanged(
        self, boss_client, group, student, group_student, debt, course, company_settings,
    ):
        """manual: debt.amount must NOT be modified."""
        company_settings.freeze_billing_type = 'manual'
        company_settings.save()
        original_amount = debt.amount

        resp = boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")
        assert resp.status_code == 200

        debt.refresh_from_db()
        assert debt.amount == original_amount

    def test_does_not_overwrite_confirmed_debt(
        self, boss_client, group, student, group_student, debt, course, teacher, company_settings,
    ):
        """A debt with confirmed_at set must not be touched, even with per_lesson billing."""
        company_settings.freeze_billing_type = 'per_lesson'
        company_settings.save()
        group_student.status = 'active'
        group_student.save()

        debt.confirmed_at = timezone.now()
        debt.save(update_fields=['confirmed_at'])
        original_amount = debt.amount

        lessons = _make_lessons(group, teacher, 10)
        _mark_attended(lessons, student, 3)

        resp = boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")
        assert resp.status_code == 200

        debt.refresh_from_db()
        assert debt.amount == original_amount

    def test_creates_new_debt_when_none_exists(
        self, boss_client, group, student, group_student, course, teacher, company_settings,
    ):
        """If no Debt record exists yet, per_lesson billing creates one."""
        company_settings.freeze_billing_type = 'per_lesson'
        company_settings.save()
        group_student.status = 'active'
        group_student.save()
        # Ensure no debt pre-exists
        assert not Debt.objects.filter(group_student=group_student).exists()

        total = 8
        attended = 5
        lessons = _make_lessons(group, teacher, total)
        _mark_attended(lessons, student, attended)

        resp = boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")
        assert resp.status_code == 200

        new_debt = Debt.objects.filter(group_student=group_student).first()
        assert new_debt is not None
        expected = (Decimal(str(course.price)) / total * attended).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert new_debt.amount == expected

    def test_group_status_set_to_frozen(
        self, boss_client, group, company_settings,
    ):
        """Smoke-test: group.status is 'frozen' after the action, regardless of billing type."""
        company_settings.freeze_billing_type = 'manual'
        company_settings.save()

        boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")
        group.refresh_from_db()
        assert group.status == 'frozen'


# ---------------------------------------------------------------------------
# Individual student freeze — proration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestIndividualStudentFreezeProratesDebt:

    def test_per_lesson_prorates_single_student(
        self, boss_client, group, student, group_student, debt, course, teacher, company_settings,
    ):
        """Freezing a single student with per_lesson billing prorates their debt."""
        company_settings.freeze_billing_type = 'per_lesson'
        company_settings.save()
        group_student.status = 'active'
        group_student.save()

        total = 6
        attended = 2
        lessons = _make_lessons(group, teacher, total)
        _mark_attended(lessons, student, attended)

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 200

        debt.refresh_from_db()
        expected = (Decimal(str(course.price)) / total * attended).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert debt.amount == expected

    def test_student_status_set_to_frozen(
        self, boss_client, student, group_student, company_settings,
    ):
        """student.status is 'frozen' after the action."""
        company_settings.freeze_billing_type = 'manual'
        company_settings.save()

        boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        student.refresh_from_db()
        assert student.status == 'frozen'

    def test_manual_leaves_debt_unchanged_for_individual_freeze(
        self, boss_client, student, group_student, debt, company_settings,
    ):
        """manual billing: individual freeze leaves debt.amount unchanged."""
        company_settings.freeze_billing_type = 'manual'
        company_settings.save()
        original_amount = debt.amount

        boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        debt.refresh_from_db()
        assert debt.amount == original_amount


# ---------------------------------------------------------------------------
# Scheduler — frozen-student exclusion
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSchedulerExcludesFrozenStudents:

    def test_skips_individually_frozen_student(self, company, group, student, group_student, course):
        """Scheduler must NOT generate debt when student.status='frozen'
        even though group.status='active' and gs.status='active'."""
        group_student.status = 'active'
        group_student.save()
        student.status = 'frozen'
        student.save()

        assign_monthly_student_debts()

        assert not Debt.objects.filter(group_student=group_student).exists()

    def test_still_bills_active_students(self, company, group, group_student, course):
        """Sanity: active students are still billed by the scheduler."""
        group_student.status = 'active'
        group_student.save()

        assign_monthly_student_debts()

        assert Debt.objects.filter(group_student=group_student).exists()
