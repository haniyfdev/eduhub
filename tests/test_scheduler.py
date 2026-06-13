import pytest
from datetime import date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta

from apps.companies.models import Company
from apps.debts.models import Debt
from apps.discounts.models import Discount
from apps.superadmin_panel.models import SubscriptionPlan, CompanySubscriptionDebt
from apps.scheduler.jobs import (
    assign_monthly_student_debts,
    mark_overdue_student_debts,
    renew_subscription_debts,
    mark_overdue_subscription_debts,
)
from .conftest import make_phone


@pytest.mark.django_db
class TestAssignMonthlyStudentDebts:
    def test_creates_debt_for_active_enrollment(self, company, group, group_student, course):
        group_student.status = "active"
        group_student.save()

        assign_monthly_student_debts()

        debt = Debt.objects.get(group_student=group_student)
        assert debt.amount == Decimal(str(course.price))
        assert debt.status == "unpaid"
        assert debt.due_date == group_student.joined_at.date() + timedelta(days=30)
        assert debt.discount is None
        assert debt.discount_amount == Decimal("0")

    def test_skips_enrollment_without_course_price(self, company, group, group_student, course):
        group_student.status = "active"
        group_student.save()
        course.price = Decimal("0")
        course.save()

        assign_monthly_student_debts()

        assert not Debt.objects.filter(group_student=group_student).exists()

    def test_rolls_forward_past_due_debt(self, company, group, group_student, course):
        group_student.status = "active"
        group_student.save()

        old_due_date = date.today() - timedelta(days=5)
        debt = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("100000"), due_date=old_due_date, status="overdue",
        )

        assign_monthly_student_debts()

        debt.refresh_from_db()
        assert debt.due_date == old_due_date + timedelta(days=30)
        assert debt.status == "unpaid"
        assert debt.amount == Decimal(str(course.price))

    def test_skips_future_due_date_debt(self, company, group, group_student, course):
        group_student.status = "active"
        group_student.save()

        future_due_date = date.today() + timedelta(days=10)
        debt = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("100000"), due_date=future_due_date, status="unpaid",
        )

        assign_monthly_student_debts()

        debt.refresh_from_db()
        assert debt.due_date == future_due_date
        assert debt.amount == Decimal("100000")

    def test_applies_active_discount(self, company, group, group_student, course, discount, student):
        group_student.status = "active"
        group_student.save()

        assign_monthly_student_debts()

        debt = Debt.objects.get(group_student=group_student)
        expected_discount_amount = (Decimal(str(course.price)) * discount.percent / Decimal("100")).quantize(Decimal("1"))
        assert debt.discount_id == discount.id
        assert debt.discount_amount == expected_discount_amount
        assert debt.amount == Decimal(str(course.price)) - expected_discount_amount

    def test_inactive_enrollment_not_billed(self, company, group, group_student, course):
        # group_student stays at default status="trial" — not 'active'
        assign_monthly_student_debts()
        assert not Debt.objects.filter(group_student=group_student).exists()


@pytest.mark.django_db
class TestMarkOverdueStudentDebts:
    def test_marks_unpaid_past_due_as_overdue(self, company, group_student):
        debt = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("100000"), due_date=date.today() - timedelta(days=1), status="unpaid",
        )

        mark_overdue_student_debts()

        debt.refresh_from_db()
        assert debt.status == "overdue"

    def test_does_not_mark_future_due_date(self, company, group_student):
        debt = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("100000"), due_date=date.today() + timedelta(days=1), status="unpaid",
        )

        mark_overdue_student_debts()

        debt.refresh_from_db()
        assert debt.status == "unpaid"

    def test_does_not_mark_paid_debts(self, company, group_student):
        debt = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("100000"), due_date=date.today() - timedelta(days=1), status="paid",
        )

        mark_overdue_student_debts()

        debt.refresh_from_db()
        assert debt.status == "paid"


@pytest.mark.django_db
class TestRenewSubscriptionDebts:
    def _make_company(self):
        # Clear any leftover SubscriptionPlan so the Company post_save signal
        # doesn't create a stray initial CompanySubscriptionDebt.
        SubscriptionPlan.objects.all().delete()
        return Company.objects.create(name="Renewal Co", phone=make_phone())

    def test_creates_next_period_when_paid_and_ended(self, db):
        company = self._make_company()
        plan = SubscriptionPlan.objects.create(price=Decimal("100000"))
        period_end = date.today() - timedelta(days=1)
        CompanySubscriptionDebt.objects.create(
            company=company, amount=plan.price,
            period_start=period_end - timedelta(days=30),
            period_end=period_end, status="paid",
        )

        renew_subscription_debts()

        new_debt = CompanySubscriptionDebt.objects.get(company=company, period_start=period_end)
        assert new_debt.period_end == period_end + timedelta(days=30)
        assert new_debt.status == "pending"
        assert new_debt.amount == plan.price

    def test_skips_when_no_plan_exists(self, db):
        company = self._make_company()
        period_end = date.today() - timedelta(days=1)
        CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=period_end - timedelta(days=30),
            period_end=period_end, status="paid",
        )

        renew_subscription_debts()

        assert CompanySubscriptionDebt.objects.filter(company=company).count() == 1

    def test_skips_if_next_period_already_exists(self, db):
        company = self._make_company()
        plan = SubscriptionPlan.objects.create(price=Decimal("100000"))
        period_end = date.today() - timedelta(days=1)
        CompanySubscriptionDebt.objects.create(
            company=company, amount=plan.price,
            period_start=period_end - timedelta(days=30),
            period_end=period_end, status="paid",
        )
        CompanySubscriptionDebt.objects.create(
            company=company, amount=plan.price,
            period_start=period_end,
            period_end=period_end + timedelta(days=30), status="pending",
        )

        renew_subscription_debts()

        assert CompanySubscriptionDebt.objects.filter(company=company).count() == 2

    def test_does_not_renew_unpaid_debt(self, db):
        company = self._make_company()
        plan = SubscriptionPlan.objects.create(price=Decimal("100000"))
        CompanySubscriptionDebt.objects.create(
            company=company, amount=plan.price,
            period_start=date.today() - timedelta(days=31),
            period_end=date.today() - timedelta(days=1), status="pending",
        )

        renew_subscription_debts()

        assert CompanySubscriptionDebt.objects.filter(company=company).count() == 1

    def test_does_not_renew_before_period_end(self, db):
        company = self._make_company()
        plan = SubscriptionPlan.objects.create(price=Decimal("100000"))
        CompanySubscriptionDebt.objects.create(
            company=company, amount=plan.price,
            period_start=date.today(),
            period_end=date.today() + timedelta(days=30), status="paid",
        )

        renew_subscription_debts()

        assert CompanySubscriptionDebt.objects.filter(company=company).count() == 1


@pytest.mark.django_db
class TestMarkOverdueSubscriptionDebts:
    def test_marks_pending_past_due_as_overdue(self, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today() - timedelta(days=31),
            period_end=date.today() - timedelta(days=1), status="pending",
        )

        mark_overdue_subscription_debts()

        debt.refresh_from_db()
        assert debt.status == "overdue"

    def test_marks_partial_past_due_as_overdue(self, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today() - timedelta(days=31),
            period_end=date.today() - timedelta(days=1), status="partial",
        )

        mark_overdue_subscription_debts()

        debt.refresh_from_db()
        assert debt.status == "overdue"

    def test_does_not_mark_future_period(self, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today(),
            period_end=date.today() + timedelta(days=30), status="pending",
        )

        mark_overdue_subscription_debts()

        debt.refresh_from_db()
        assert debt.status == "pending"

    def test_does_not_mark_paid_debts(self, company):
        debt = CompanySubscriptionDebt.objects.create(
            company=company, amount=Decimal("100000"),
            period_start=date.today() - timedelta(days=31),
            period_end=date.today() - timedelta(days=1), status="paid",
        )

        mark_overdue_subscription_debts()

        debt.refresh_from_db()
        assert debt.status == "paid"
