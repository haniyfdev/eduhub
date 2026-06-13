import pytest
from datetime import date
from dateutil.relativedelta import relativedelta

from apps.discounts.models import Discount

DISCOUNTS_URL = "/api/v1/discounts/"


@pytest.mark.django_db
class TestDiscountPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(DISCOUNTS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(DISCOUNTS_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        resp = admin_client.get(DISCOUNTS_URL)
        assert resp.status_code == 200

    def test_teacher_can_list(self, teacher_client):
        resp = teacher_client.get(DISCOUNTS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(DISCOUNTS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestDiscountCreate:
    def test_boss_can_create(self, boss_client, student, course):
        resp = boss_client.post(DISCOUNTS_URL, {
            "student": str(student.id),
            "course": str(course.id),
            "percent": 20,
            "months": 2,
            "note": "Loyalty discount",
        })
        assert resp.status_code == 201
        assert resp.data["percent"] == 20
        assert resp.data["months"] == 2

    def test_admin_can_create(self, admin_client, student, course):
        resp = admin_client.post(DISCOUNTS_URL, {
            "student": str(student.id),
            "course": str(course.id),
            "percent": 15,
            "months": 1,
        })
        assert resp.status_code == 201

    def test_teacher_cannot_create(self, teacher_client, student, course):
        resp = teacher_client.post(DISCOUNTS_URL, {
            "student": str(student.id),
            "course": str(course.id),
            "percent": 15,
            "months": 1,
        })
        assert resp.status_code == 403

    def test_create_invalid_percent_rejected(self, boss_client, student, course):
        resp = boss_client.post(DISCOUNTS_URL, {
            "student": str(student.id),
            "course": str(course.id),
            "percent": 150,
            "months": 1,
        })
        assert resp.status_code == 400
        assert "percent" in resp.data

    def test_create_invalid_months_rejected(self, boss_client, student, course):
        resp = boss_client.post(DISCOUNTS_URL, {
            "student": str(student.id),
            "course": str(course.id),
            "percent": 10,
            "months": 13,
        })
        assert resp.status_code == 400
        assert "months" in resp.data

    def test_create_sets_start_and_end_month(self, boss_client, student, course):
        resp = boss_client.post(DISCOUNTS_URL, {
            "student": str(student.id),
            "course": str(course.id),
            "percent": 10,
            "months": 1,
        })
        assert resp.status_code == 201

        expected_start = date.today().replace(day=1) + relativedelta(months=1)
        created = Discount.objects.get(student=student, course=course)
        assert created.start_month == expected_start
        assert created.end_month == expected_start + relativedelta(months=1)


@pytest.mark.django_db
class TestDiscountListAndRetrieve:
    def test_list_includes_discount(self, boss_client, discount):
        resp = boss_client.get(DISCOUNTS_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(discount.id) in ids

    def test_retrieve_discount_amounts(self, boss_client, discount, course):
        resp = boss_client.get(f"{DISCOUNTS_URL}{discount.id}/")
        assert resp.status_code == 200
        assert resp.data["discount_amount"] == float(course.price) * discount.percent / 100
        assert resp.data["final_amount"] == float(course.price) * (1 - discount.percent / 100)

    def test_filter_by_student(self, boss_client, discount, student):
        resp = boss_client.get(f"{DISCOUNTS_URL}?student={student.id}")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(discount.id) in ids

    def test_filter_by_course(self, boss_client, discount, course):
        resp = boss_client.get(f"{DISCOUNTS_URL}?course={course.id}")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(discount.id) in ids


@pytest.mark.django_db
class TestDiscountDelete:
    def test_boss_can_delete(self, boss_client, discount):
        resp = boss_client.delete(f"{DISCOUNTS_URL}{discount.id}/")
        assert resp.status_code == 204
        assert not Discount.objects.filter(id=discount.id).exists()

    def test_manager_can_delete(self, manager_client, discount):
        resp = manager_client.delete(f"{DISCOUNTS_URL}{discount.id}/")
        assert resp.status_code == 204

    def test_admin_cannot_delete(self, admin_client, discount):
        resp = admin_client.delete(f"{DISCOUNTS_URL}{discount.id}/")
        assert resp.status_code == 403

    def test_patch_not_allowed(self, boss_client, discount):
        resp = boss_client.patch(f"{DISCOUNTS_URL}{discount.id}/", {"percent": 50})
        assert resp.status_code == 405


@pytest.mark.django_db
class TestDiscountIsActiveForMonth:
    def test_active_within_range(self, discount):
        assert discount.is_active_for_month(discount.start_month) is True
        assert discount.is_active_for_month(discount.end_month) is True

    def test_inactive_outside_range(self, discount):
        before = discount.start_month - relativedelta(months=1)
        after = discount.end_month + relativedelta(months=1)
        assert discount.is_active_for_month(before) is False
        assert discount.is_active_for_month(after) is False
