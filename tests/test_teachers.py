import pytest
from datetime import date
from decimal import Decimal

from apps.teachers.models import Teacher
from apps.users.models import User
from .conftest import make_phone

TEACHERS_URL = "/api/v1/teachers/"


def teacher_payload(user_id, company_id):
    return {
        "user_id": str(user_id),
        "company_id": str(company_id),
        "salary_type": "fixed",
        "fixed_amount": "1500000.00",
        "hired_at": str(date.today()),
    }


@pytest.mark.django_db
class TestTeacherPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(TEACHERS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(TEACHERS_URL)
        assert resp.status_code == 200

    def test_admin_can_create(self, admin_client, company):
        resp = admin_client.post(TEACHERS_URL, {
            "phone": make_phone(),
            "first_name": "New",
            "last_name": "Teacher",
            "password": "pass1234",
            "salary_type": "fixed",
            "fixed_amount": "1500000.00",
        })
        assert resp.status_code == 201
        assert Teacher.objects.filter(user__first_name="New", user__last_name="Teacher").exists()

    def test_teacher_cannot_create(self, teacher_client, teacher_user, company):
        resp = teacher_client.post(TEACHERS_URL, teacher_payload(teacher_user.id, company.id))
        assert resp.status_code == 403

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(TEACHERS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestTeacherCRUD:
    def test_list_teachers(self, boss_client, teacher):
        resp = boss_client.get(TEACHERS_URL)
        assert resp.status_code == 200
        assert len(resp.data.get("results", resp.data)) >= 1

    def test_retrieve_teacher(self, boss_client, teacher):
        resp = boss_client.get(f"{TEACHERS_URL}{teacher.id}/")
        assert resp.status_code == 200
        assert resp.data["id"] == str(teacher.id)

    def test_update_salary_type(self, boss_client, teacher):
        resp = boss_client.patch(f"{TEACHERS_URL}{teacher.id}/", {
            "salary_type": "per_student",
            "per_student_amt": "50000.00",
        })
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.salary_type == "per_student"

    def test_archive_teacher(self, boss_client, teacher, teacher_user):
        resp = boss_client.post(f"{TEACHERS_URL}{teacher.id}/archive/")
        assert resp.status_code == 200
        teacher.refresh_from_db()
        teacher_user.refresh_from_db()
        assert teacher.status == "archived"
        assert teacher_user.status == "archived"
        assert teacher_user.is_active is False

    def test_archive_does_not_delete(self, boss_client, teacher):
        boss_client.post(f"{TEACHERS_URL}{teacher.id}/archive/")
        assert Teacher.objects.filter(id=teacher.id).exists()

    def test_cross_company_blocked(self, boss_client, company2, db):
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
        resp = boss_client.get(f"{TEACHERS_URL}{other_teacher.id}/")
        assert resp.status_code in (403, 404)
