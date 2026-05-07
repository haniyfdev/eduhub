import pytest
from decimal import Decimal

from apps.payments.models import Payment
from apps.debts.models import Debt

PAYMENTS_URL = "/api/v1/payments/"


def payment_payload(student, group, course, payment_type="cash", amount="500000.00"):
    return {
        "student_id": str(student.id),
        "group_id": str(group.id),
        "course_id": str(course.id),
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
    def test_patch_not_allowed(self, boss_client, student, group, course, company):
        create_resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course))
        assert create_resp.status_code == 201
        payment_id = create_resp.data["id"]
        resp = boss_client.patch(f"{PAYMENTS_URL}{payment_id}/", {"amount": "999.00"})
        assert resp.status_code == 405

    def test_delete_not_allowed(self, boss_client, student, group, course, company):
        create_resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course))
        payment_id = create_resp.data["id"]
        resp = boss_client.delete(f"{PAYMENTS_URL}{payment_id}/")
        assert resp.status_code == 405

    def test_put_not_allowed(self, boss_client, student, group, course, company):
        create_resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course))
        payment_id = create_resp.data["id"]
        resp = boss_client.put(f"{PAYMENTS_URL}{payment_id}/", {})
        assert resp.status_code == 405


@pytest.mark.django_db
class TestPaymentCreationBusinessLogic:
    def test_create_payment_success(self, boss_client, student, group, course):
        resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course))
        assert resp.status_code == 201
        assert Payment.objects.filter(student=student).exists()

    def test_payment_amount_frozen(self, boss_client, student, group, course):
        resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course, amount="300000.00"))
        assert resp.status_code == 201
        payment = Payment.objects.get(id=resp.data["id"])
        assert payment.amount == Decimal("300000.00")

    def test_payment_updates_debt_to_paid(self, boss_client, student, group, course, debt):
        # debt is 500000, paying exactly 500000 → paid
        resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course, amount="500000.00"))
        assert resp.status_code == 201
        debt.refresh_from_db()
        assert debt.status == "paid"
        assert debt.amount == Decimal("0.00")

    def test_payment_partial_reduces_debt(self, boss_client, student, group, course, debt):
        # debt is 500000, paying 200000 → partial, 300000 remaining
        resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course, amount="200000.00"))
        assert resp.status_code == 201
        debt.refresh_from_db()
        assert debt.status == "partial"
        assert debt.amount == Decimal("300000.00")

    def test_payment_no_debt_no_error(self, boss_client, group, course, company, db):
        from apps.students.models import Student
        from .conftest import make_phone
        student_no_debt = Student.objects.create(
            company=company, first_name="No", last_name="Debt",
            phone=make_phone(), status="active"
        )
        resp = boss_client.post(PAYMENTS_URL, payment_payload(student_no_debt, group, course))
        assert resp.status_code == 201

    def test_payment_with_percent_discount(self, boss_client, student, group, course, discount, debt):
        # 10% discount on 500000 = 450000 final
        payload = payment_payload(student, group, course, amount="500000.00")
        payload["discount_id"] = str(discount.id)
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 201
        payment = Payment.objects.get(id=resp.data["id"])
        assert payment.amount == Decimal("450000.00")

    def test_payment_with_fixed_discount(self, boss_client, student, group, course, company, debt):
        from apps.discounts.models import Discount
        fixed_disc = Discount.objects.create(
            company=company, course=course,
            name="Fixed 50k off", type="fixed",
            value=Decimal("50000"), status="active"
        )
        payload = payment_payload(student, group, course, amount="500000.00")
        payload["discount_id"] = str(fixed_disc.id)
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 201
        payment = Payment.objects.get(id=resp.data["id"])
        assert payment.amount == Decimal("450000.00")

    def test_negative_discount_rejected(self, boss_client, student, group, course, company):
        from apps.discounts.models import Discount
        big_disc = Discount.objects.create(
            company=company, course=course,
            name="Too Big", type="fixed",
            value=Decimal("1000000"), status="active"
        )
        payload = payment_payload(student, group, course, amount="100.00")
        payload["discount_id"] = str(big_disc.id)
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 400

    def test_cross_company_student_rejected(self, boss_client, group, course, company2, db):
        from apps.students.models import Student
        from .conftest import make_phone
        other_student = Student.objects.create(
            company=company2, first_name="X", last_name="Y",
            phone=make_phone(), status="active"
        )
        resp = boss_client.post(PAYMENTS_URL, payment_payload(other_student, group, course))
        assert resp.status_code == 400

    def test_zero_amount_rejected(self, boss_client, student, group, course):
        payload = payment_payload(student, group, course, amount="0.00")
        resp = boss_client.post(PAYMENTS_URL, payload)
        assert resp.status_code == 400

    def test_payment_types_accepted(self, boss_client, student, group, course):
        for ptype in ["cash", "card", "transfer"]:
            resp = boss_client.post(PAYMENTS_URL, payment_payload(student, group, course, payment_type=ptype))
            assert resp.status_code == 201
