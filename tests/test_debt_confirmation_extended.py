from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.attendance.models import Attendance
from apps.lessons.models import Lesson

DEBTS_URL = "/api/v1/debts/"


@pytest.mark.django_db
class TestDebtConfirmation:
    def test_patch_amount_sets_confirmed_at(self, boss_client, debt):
        assert debt.confirmed_at is None

        resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "600000"})

        assert resp.status_code == 200
        debt.refresh_from_db()
        assert debt.confirmed_at is not None
        assert debt.amount == Decimal("600000")

    def test_confirmed_at_not_null_after_patch(self, boss_client, debt):
        boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "700000"})

        debt.refresh_from_db()
        assert debt.confirmed_at is not None

    def test_cannot_change_amount_after_confirmed(self, boss_client, debt):
        first = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "600000"})
        assert first.status_code == 200
        debt.refresh_from_db()
        first_confirmed_at = debt.confirmed_at
        assert first_confirmed_at is not None

        # Once confirmed_at is set, a second amount change is rejected.
        second = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "650000"})
        assert second.status_code == 400
        assert second.data["amount"] == "Qarz miqdori allaqachon tasdiqlangan"

        debt.refresh_from_db()
        assert debt.amount == Decimal("600000")
        assert debt.confirmed_at == first_confirmed_at

    def test_confirmed_amount_shown_in_list(self, boss_client, debt):
        boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": "600000"})

        resp = boss_client.get(DEBTS_URL)
        assert resp.status_code == 200
        results = resp.data.get("results", resp.data)
        entry = next(d for d in results if d['id'] == str(debt.id))
        assert Decimal(str(entry['amount'])) == Decimal("600000")
        assert entry['confirmed_at'] is not None

    def test_unconfirmed_debt_has_null_confirmed_at(self, boss_client, debt):
        resp = boss_client.get(f"{DEBTS_URL}{debt.id}/")

        assert resp.status_code == 200
        assert resp.data['confirmed_at'] is None

    def test_kunbay_calculated_amount_saved_correctly(self, boss_client, debt, group_student):
        month_start = date.today().replace(day=1)
        left_date = month_start + timedelta(days=10)

        group_student.joined_at = timezone.make_aware(datetime.combine(month_start, time.min))
        group_student.left_at = timezone.make_aware(datetime.combine(left_date, time.min))
        group_student.archive_billing_type = 'per_day'
        group_student.save()

        resp = boss_client.get(f"{DEBTS_URL}{debt.id}/last-month-attendance/")
        assert resp.status_code == 200
        calculated_amount = resp.data['calculated_amount']
        assert calculated_amount > 0

        patch_resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": str(calculated_amount)})
        assert patch_resp.status_code == 200

        debt.refresh_from_db()
        assert debt.amount == Decimal(str(calculated_amount))
        assert debt.confirmed_at is not None

    def test_darsbay_calculated_amount_saved_correctly(
        self, boss_client, debt, group_student, group, teacher, student,
    ):
        month_start = date.today().replace(day=1)
        left_date = month_start + timedelta(days=10)
        lesson_date = month_start + timedelta(days=5)

        group_student.joined_at = timezone.make_aware(datetime.combine(month_start, time.min))
        group_student.left_at = timezone.make_aware(datetime.combine(left_date, time.min))
        group_student.archive_billing_type = 'per_lesson'
        group_student.save()

        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="Lesson 1", date=lesson_date, status="finished",
        )
        Attendance.objects.create(lesson=lesson, student=student, status="present")

        resp = boss_client.get(f"{DEBTS_URL}{debt.id}/last-month-attendance/")
        assert resp.status_code == 200
        calculated_amount = resp.data['calculated_amount']
        assert calculated_amount > 0

        patch_resp = boss_client.patch(f"{DEBTS_URL}{debt.id}/", {"amount": str(calculated_amount)})
        assert patch_resp.status_code == 200

        debt.refresh_from_db()
        assert debt.amount == Decimal(str(calculated_amount))
        assert debt.confirmed_at is not None
