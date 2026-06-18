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
from apps.groups.models import Group
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
        assert Debt.objects.filter(group_student=group_student).count() == 1

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


# ---------------------------------------------------------------------------
# freeze_billing_type end-to-end — settings → modal endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestFreezeBillingTypeEndToEnd:

    def test_billing_type_per_lesson_read_from_settings(
        self, boss_client, group, student, group_student, debt, course, teacher, company_settings,
    ):
        """CompanySettings.freeze_billing_type='per_lesson' must be returned by
        last-month-attendance for a frozen student, not fall back to 'manual'."""
        company_settings.freeze_billing_type = 'per_lesson'
        company_settings.save()
        group_student.status = 'active'
        group_student.save()

        lessons = _make_lessons(group, teacher, 5)
        _mark_attended(lessons, student, 2)

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 200

        resp = boss_client.get(f"/api/v1/debts/{debt.id}/last-month-attendance/")
        assert resp.status_code == 200
        assert resp.data['billing_type'] == 'per_lesson'

    def test_billing_type_per_day_read_from_settings(
        self, boss_client, group, student, group_student, debt, course, company_settings,
    ):
        """freeze_billing_type='per_day' is correctly returned for a frozen student."""
        company_settings.freeze_billing_type = 'per_day'
        company_settings.save()

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 200

        resp = boss_client.get(f"/api/v1/debts/{debt.id}/last-month-attendance/")
        assert resp.status_code == 200
        assert resp.data['billing_type'] == 'per_day'


# ---------------------------------------------------------------------------
# Unfreeze — full-price debt creation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUnfreezeCreatesFullPriceDebt:

    def test_unfreeze_creates_second_full_price_debt(
        self, boss_client, group, student, group_student, debt, course, company_settings,
    ):
        """After freeze → unfreeze, there must be 2 Debt records: the original
        (possibly prorated) debt and a new full-price reactivation debt."""
        company_settings.freeze_billing_type = 'manual'
        company_settings.save()

        boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/unfreeze/")
        assert resp.status_code == 200

        all_debts = Debt.objects.filter(group_student=group_student)
        assert all_debts.count() == 2

        full_price_debts = all_debts.filter(amount=course.price)
        assert full_price_debts.count() >= 1

    def test_prorated_debt_unchanged_after_unfreeze(
        self, boss_client, group, student, group_student, debt, course, teacher, company_settings,
    ):
        """The prorated freeze debt must remain intact after unfreeze; only a new
        separate full-price debt is added."""
        company_settings.freeze_billing_type = 'per_lesson'
        company_settings.save()
        group_student.status = 'active'
        group_student.save()

        total = 8
        attended = 3
        lessons = _make_lessons(group, teacher, total)
        _mark_attended(lessons, student, attended)

        boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        debt.refresh_from_db()
        prorated_amount = debt.amount
        expected_prorated = (Decimal(str(course.price)) / total * attended).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert prorated_amount == expected_prorated

        boss_client.post(f"{STUDENTS_URL}{student.id}/unfreeze/")

        debt.refresh_from_db()
        assert debt.amount == prorated_amount

        new_debt = Debt.objects.filter(group_student=group_student).exclude(id=debt.id).first()
        assert new_debt is not None
        assert new_debt.amount == Decimal(str(course.price))

    def test_group_unfreeze_creates_full_price_debt_per_student(
        self, boss_client, group, student, group_student, debt, course, company_settings,
    ):
        """Group-level unfreeze must also create a new full-price debt for every
        student that was in the frozen group."""
        company_settings.freeze_billing_type = 'manual'
        company_settings.save()

        boss_client.post(f"{GROUPS_URL}{group.id}/freeze/")

        resp = boss_client.post(f"{GROUPS_URL}{group.id}/unfreeze/")
        assert resp.status_code == 200

        all_debts = Debt.objects.filter(group_student=group_student)
        assert all_debts.count() == 2
        assert all_debts.filter(amount=course.price).count() >= 1


# ---------------------------------------------------------------------------
# Group transfer — proration on leaving old group
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTransferStudentProratesDebt:

    @pytest.fixture
    def group2(self, db, company, course, teacher, room):
        return Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=2, gender_type="a", status="active",
        )

    def test_per_lesson_prorates_old_group_debt(
        self, boss_client, group, group2, student, group_student, debt, course, teacher, company_settings,
    ):
        """per_lesson: transferring out of a group updates the debt to reflect
        only the lessons attended, not the full course price."""
        company_settings.archive_billing_type = 'per_lesson'
        company_settings.save()

        total = 10
        attended = 3
        lessons = _make_lessons(group, teacher, total)
        _mark_attended(lessons, student, attended)

        resp = boss_client.post(
            f"{GROUPS_URL}{group.id}/transfer-student/",
            {'student_id': str(student.id), 'new_group_id': str(group2.id)},
        )
        assert resp.status_code == 200

        debt.refresh_from_db()
        expected = (Decimal(str(course.price)) / total * attended).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert debt.amount == expected

    def test_per_day_prorates_old_group_debt(
        self, boss_client, group, group2, student, group_student, debt, course, company_settings,
    ):
        """per_day: transferring out prorates debt by days active in the month."""
        company_settings.archive_billing_type = 'per_day'
        company_settings.save()
        today = date.today()
        month_start = today.replace(day=1)
        group_student.joined_at = timezone.make_aware(
            timezone.datetime(month_start.year, month_start.month, month_start.day)
        )
        group_student.save()

        resp = boss_client.post(
            f"{GROUPS_URL}{group.id}/transfer-student/",
            {'student_id': str(student.id), 'new_group_id': str(group2.id)},
        )
        assert resp.status_code == 200

        debt.refresh_from_db()
        import calendar
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_active = (today - month_start).days + 1
        expected = (Decimal(str(course.price)) / days_in_month * days_active).quantize(
            Decimal('1E+3'), rounding=ROUND_HALF_UP
        )
        assert debt.amount == expected

    def test_manual_leaves_old_group_debt_unchanged(
        self, boss_client, group, group2, student, group_student, debt, company_settings,
    ):
        """manual: transfer must not change the existing debt amount."""
        company_settings.archive_billing_type = 'manual'
        company_settings.save()
        original_amount = debt.amount

        resp = boss_client.post(
            f"{GROUPS_URL}{group.id}/transfer-student/",
            {'student_id': str(student.id), 'new_group_id': str(group2.id)},
        )
        assert resp.status_code == 200

        debt.refresh_from_db()
        assert debt.amount == original_amount

    def test_old_gs_closed_as_left(
        self, boss_client, group, group2, student, group_student, company_settings,
    ):
        """Old GroupStudent must have status='left' and left_at set after transfer."""
        company_settings.archive_billing_type = 'manual'
        company_settings.save()

        boss_client.post(
            f"{GROUPS_URL}{group.id}/transfer-student/",
            {'student_id': str(student.id), 'new_group_id': str(group2.id)},
        )

        group_student.refresh_from_db()
        assert group_student.status == 'left'
        assert group_student.left_at is not None

    def test_new_enrollment_is_trial_with_no_debt(
        self, boss_client, group, group2, student, group_student, debt, company_settings,
    ):
        """New GroupStudent in the target group must be trial, and no debt is
        created for it (the monthly scheduler handles trial→active billing)."""
        company_settings.archive_billing_type = 'manual'
        company_settings.save()

        boss_client.post(
            f"{GROUPS_URL}{group.id}/transfer-student/",
            {'student_id': str(student.id), 'new_group_id': str(group2.id)},
        )

        from apps.groups.models import GroupStudent as GS
        new_gs = GS.objects.filter(group=group2, student=student, left_at__isnull=True).first()
        assert new_gs is not None
        assert new_gs.status == 'trial'
        assert not Debt.objects.filter(group_student=new_gs).exists()

    def test_transfer_sets_archive_billing_type_on_old_gs(
        self, boss_client, group, group2, student, group_student, company_settings,
    ):
        """archive_billing_type is stored on the old GroupStudent so the debt
        modal can display the correct billing method."""
        company_settings.archive_billing_type = 'per_lesson'
        company_settings.save()

        boss_client.post(
            f"{GROUPS_URL}{group.id}/transfer-student/",
            {'student_id': str(student.id), 'new_group_id': str(group2.id)},
        )

        group_student.refresh_from_db()
        assert group_student.archive_billing_type == 'per_lesson'
