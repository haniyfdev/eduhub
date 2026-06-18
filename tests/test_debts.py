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
        from django.utils import timezone
        from apps.teachers.models import Teacher
        from apps.users.models import User
        from apps.courses.models import Course
        from apps.rooms.models import Room
        from apps.groups.models import Group, GroupStudent

        other_user = User.objects.create_user(
            phone=make_phone(), password="pass",
            first_name="X", last_name="Y",
            role="teacher", status="active", company=company2,
        )
        other_teacher = Teacher.objects.create(
            user=other_user, company=company2,
            salary_type="fixed", fixed_amount=Decimal("1000000"),
            hired_at=date.today(), status="active",
        )
        other_course = Course.objects.create(
            company=company2, name="Other Course", price=Decimal("400000"),
            duration_months=3, duration_hours=Decimal("60"),
        )
        other_course.teachers.add(other_teacher)
        other_room = Room.objects.create(company=company2, name=1, gender_type="a", status="active")
        other_group = Group.objects.create(
            company=company2, course=other_course, teacher=other_teacher,
            room=other_room, number=1, gender_type="a", status="active",
        )
        other_student = Student.objects.create(
            company=company2, first_name="X", last_name="Y",
            phone=make_phone(), status="active"
        )
        other_gs = GroupStudent.objects.create(
            group=other_group, student=other_student, joined_at=timezone.now()
        )
        other_debt = Debt.objects.create(
            company=company2, group_student=other_gs,
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
class TestDebtSearch:
    """Search by group number must not be drowned out by phone number matches."""

    def test_search_by_group_number_returns_only_that_group(
        self, boss_client, company, group, student, group_student, course, teacher, room, db
    ):
        """Searching '1' (the group number) must return only debts in group 1,
        not debts from other groups whose students happen to have '1' in their phone."""
        from django.utils import timezone
        from apps.groups.models import Group, GroupStudent

        # Debt for the existing group (number=1) already via group_student fixture.
        # Create a second group (number=2) with its own student/debt.
        group2 = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=2, gender_type="b", status="active",
        )
        student2 = Student.objects.create(
            company=company, first_name="Other", last_name="Student",
            phone=make_phone(), status="active",
        )
        gs2 = GroupStudent.objects.create(group=group2, student=student2, joined_at=timezone.now())
        debt2 = Debt.objects.create(
            company=company, group_student=gs2,
            amount=Decimal("300000"),
            due_date=date.today() + timedelta(days=30),
            status="unpaid",
        )
        # Also create a debt for the existing (group 1) student.
        debt1 = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("500000"),
            due_date=date.today() + timedelta(days=30),
            status="unpaid",
        )

        resp = boss_client.get(f"{DEBTS_URL}?search=2")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.data["results"]]
        assert str(debt2.id) in ids
        assert str(debt1.id) not in ids

    def test_search_by_student_name_works(self, boss_client, debt, student):
        """Searching by part of a student's first name must return their debt."""
        resp = boss_client.get(f"{DEBTS_URL}?search={student.first_name[:3]}")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.data["results"]]
        assert str(debt.id) in ids

    def test_short_digit_does_not_match_via_phone(
        self, boss_client, company, group, group_student, course, teacher, room, db
    ):
        """A single-digit search must NOT match every row via phone__icontains."""
        from django.utils import timezone
        from apps.groups.models import Group, GroupStudent

        # Debt for group 1.
        debt1 = Debt.objects.create(
            company=company, group_student=group_student,
            amount=Decimal("500000"),
            due_date=date.today() + timedelta(days=30),
            status="unpaid",
        )
        # Create group 9 with a student whose phone also contains '1' (almost certain).
        group9 = Group.objects.create(
            company=company, course=course, teacher=teacher, room=room,
            number=9, gender_type="a", status="active",
        )
        student9 = Student.objects.create(
            company=company, first_name="Zara", last_name="Zed",
            phone="+998901111111", status="active",
        )
        gs9 = GroupStudent.objects.create(group=group9, student=student9, joined_at=timezone.now())
        debt9 = Debt.objects.create(
            company=company, group_student=gs9,
            amount=Decimal("200000"),
            due_date=date.today() + timedelta(days=30),
            status="unpaid",
        )

        # Search '1' — should match group 1 (number=1), not group 9 (even though
        # student9's phone '+998901111111' is full of '1's).
        resp = boss_client.get(f"{DEBTS_URL}?search=1")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.data["results"]]
        assert str(debt1.id) in ids
        assert str(debt9.id) not in ids


@pytest.mark.django_db
class TestAssignMonthlyDebts:
    def test_assign_monthly_debts_task(self, company, student, group, group_student, course, db):
        from apps.debts.tasks import assign_monthly_debts
        group_student.status = 'active'
        group_student.save()
        assign_monthly_debts(str(company.id))
        assert Debt.objects.filter(group_student__student=student, company=company).exists()

    def test_assign_monthly_debts_idempotent(self, company, student, group, group_student, course, db):
        from apps.debts.tasks import assign_monthly_debts
        group_student.status = 'active'
        group_student.save()
        assign_monthly_debts(str(company.id))
        assign_monthly_debts(str(company.id))
        assert Debt.objects.filter(group_student__student=student, company=company).count() == 1
