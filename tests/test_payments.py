import pytest
import uuid
from datetime import date
from decimal import Decimal

from apps.payments.models import Payment
from apps.debts.models import Debt
from apps.discounts.models import Discount

PAYMENTS_URL = "/api/v1/payments/"


def payment_payload(group_student, payment_type="cash", amount="500000.00"):
    return {
        "group_student_id": str(group_student.id),
        "requested_amount": amount,
        "payment_type": payment_type,
    }


@pytest.mark.django_db
class TestPaymentPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(PAYMENTS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(PAYMENTS_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        resp = admin_client.get(PAYMENTS_URL)
        assert resp.status_code == 200

    def test_teacher_can_list(self, teacher_client):
        # PaymentViewSet uses IsAuthenticated() for all actions
        resp = teacher_client.get(PAYMENTS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(PAYMENTS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestPaymentImmutability:
    def test_patch_not_allowed(self, boss_client, group_student):
        create_resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student))
        assert create_resp.status_code == 201
        payment_id = create_resp.data["id"]
        resp = boss_client.patch(f"{PAYMENTS_URL}{payment_id}/", {"amount": "999.00"})
        assert resp.status_code == 405

    def test_delete_not_allowed(self, boss_client, group_student):
        create_resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student))
        payment_id = create_resp.data["id"]
        resp = boss_client.delete(f"{PAYMENTS_URL}{payment_id}/")
        assert resp.status_code == 405

    def test_put_not_allowed(self, boss_client, group_student):
        create_resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student))
        payment_id = create_resp.data["id"]
        resp = boss_client.put(f"{PAYMENTS_URL}{payment_id}/", {})
        assert resp.status_code == 405


@pytest.mark.django_db
class TestPaymentCreationBusinessLogic:
    def test_create_payment_success(self, boss_client, group_student):
        resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student))
        assert resp.status_code == 201
        assert Payment.objects.filter(group_student=group_student).exists()

    def test_payment_amount_frozen(self, boss_client, group_student):
        resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student, amount="300000.00"))
        assert resp.status_code == 201
        payment = Payment.objects.get(id=resp.data["id"])
        assert payment.amount == Decimal("300000.00")

    def test_payment_updates_debt_to_paid(self, boss_client, group_student, debt):
        # debt is 500000, paying exactly 500000 → paid
        resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student, amount="500000.00"))
        assert resp.status_code == 201
        debt.refresh_from_db()
        assert debt.status == "paid"
        assert debt.amount == Decimal("0.00")

    def test_payment_partial_reduces_debt(self, boss_client, group_student, debt):
        # debt is 500000, paying 200000 → partial, 300000 remaining
        resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student, amount="200000.00"))
        assert resp.status_code == 201
        debt.refresh_from_db()
        assert debt.status == "partial"
        assert debt.amount == Decimal("300000.00")

    def test_payment_no_debt_no_error(self, boss_client, group, company, db):
        from apps.students.models import Student
        from apps.groups.models import GroupStudent
        from django.utils import timezone
        from .conftest import make_phone

        student_no_debt = Student.objects.create(
            company=company, first_name="No", last_name="Debt",
            phone=make_phone(), status="active"
        )
        gs = GroupStudent.objects.create(group=group, student=student_no_debt, joined_at=timezone.now())
        resp = boss_client.post(PAYMENTS_URL, payment_payload(gs))
        assert resp.status_code == 201

    def test_payment_with_percent_discount(self, boss_client, group_student, discount, debt):
        # 10% discount on 500000 = 450000 final
        payload = payment_payload(group_student, amount="500000.00")
        payload["discount_id"] = str(discount.id)
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 201
        payment = Payment.objects.get(id=resp.data["id"])
        assert payment.amount == Decimal("450000.00")

    def test_payment_with_fixed_discount(self, boss_client, group_student, company, debt):
        # 10% discount on 500000 = 450000 final
        extra_disc = Discount.objects.create(
            company=company, student=group_student.student, course=group_student.group.course,
            percent=10, months=1, start_month=date.today().replace(day=1),
        )
        payload = payment_payload(group_student, amount="500000.00")
        payload["discount_id"] = str(extra_disc.id)
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 201
        payment = Payment.objects.get(id=resp.data["id"])
        assert payment.amount == Decimal("450000.00")

    def test_negative_discount_rejected(self, boss_client, group_student, company):
        big_disc = Discount.objects.create(
            company=company, student=group_student.student, course=group_student.group.course,
            percent=150, months=1, start_month=date.today().replace(day=1),
        )
        payload = payment_payload(group_student, amount="100.00")
        payload["discount_id"] = str(big_disc.id)
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 400

    def test_cross_company_student_rejected(self, boss_client, group, course, company2, db):
        resp = boss_client.post(PAYMENTS_URL, {
            "group_student_id": str(uuid.uuid4()),
            "requested_amount": "500000.00",
            "payment_type": "cash",
        })
        assert resp.status_code == 400

    def test_zero_amount_rejected(self, boss_client, group_student):
        payload = payment_payload(group_student, amount="0.00")
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 400

    def test_payment_types_accepted(self, boss_client, group_student):
        for ptype in ["cash", "card", "transfer"]:
            resp = boss_client.post(PAYMENTS_URL, payment_payload(group_student, payment_type=ptype))
            assert resp.status_code == 201
