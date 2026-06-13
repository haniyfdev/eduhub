import pytest
from decimal import Decimal

from apps.courses.models import Course

COURSES_URL = "/api/v1/courses/"


@pytest.mark.django_db
class TestCoursePermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(COURSES_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(COURSES_URL)
        assert resp.status_code == 200

    def test_admin_can_create(self, admin_client, teacher):
        resp = admin_client.post(COURSES_URL, {
            "name": "Go Course", "price": "600000.00",
            "duration_months": 4, "duration_hours": 80,
            "teacher_id": str(teacher.id),
        })
        assert resp.status_code == 201
        assert Course.objects.filter(name="Go Course").exists()

    def test_teacher_can_read(self, teacher_client):
        resp = teacher_client.get(COURSES_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(COURSES_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestCourseCRUD:
    def test_create_course(self, boss_client, teacher):
        resp = boss_client.post(COURSES_URL, {
            "name": "Django Course",
            "price": "800000.00",
            "duration_months": 6,
            "duration_hours": 120,
            "teacher_id": str(teacher.id),
        })
        assert resp.status_code == 201
        assert Course.objects.filter(name="Django Course").exists()

    def test_list_course(self, boss_client, course):
        resp = boss_client.get(COURSES_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.data.get("results", resp.data)]
        assert str(course.id) in ids

    def test_retrieve_course(self, boss_client, course):
        resp = boss_client.get(f"{COURSES_URL}{course.id}/")
        assert resp.status_code == 200

    def test_update_course_price(self, boss_client, course):
        resp = boss_client.patch(f"{COURSES_URL}{course.id}/", {"price": "600000.00"})
        assert resp.status_code == 200
        course.refresh_from_db()
        assert course.price == Decimal("600000.00")

    def test_archive_course(self, boss_client, course):
        resp = boss_client.post(f"{COURSES_URL}{course.id}/archive/")
        assert resp.status_code == 200
        course.refresh_from_db()
        assert course.status == "archived"

    def test_archive_does_not_delete(self, boss_client, course):
        boss_client.post(f"{COURSES_URL}{course.id}/archive/")
        assert Course.objects.filter(id=course.id).exists()

    def test_cross_company_blocked(self, boss_client, company2, teacher, db):
        from apps.teachers.models import Teacher
        from apps.users.models import User
        from .conftest import make_phone
        from datetime import date

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
            company=company2,
            name="Other Course", price=Decimal("400000"),
            duration_months=3, duration_hours=Decimal("60"),
        )
        other_course.teachers.add(other_teacher)
        resp = boss_client.get(f"{COURSES_URL}{other_course.id}/")
        assert resp.status_code in (403, 404)
