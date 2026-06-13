import pytest

from apps.students.models import Student
from .conftest import make_phone

STUDENTS_URL = "/api/v1/students/"


def student_data():
    return {
        "first_name": "John",
        "last_name": "Doe",
        "phone": make_phone(),
        "birth_date": "2010-01-01",
        "status": "pending",
    }


@pytest.mark.django_db
class TestStudentPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(STUDENTS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(STUDENTS_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        resp = admin_client.get(STUDENTS_URL)
        assert resp.status_code == 200

    def test_teacher_can_list(self, teacher_client):
        # StudentViewSet uses IsAuthenticated() — all authenticated users can access
        resp = teacher_client.get(STUDENTS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(STUDENTS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestStudentCRUD:
    def test_create_student(self, boss_client, company):
        resp = boss_client.post(STUDENTS_URL, student_data())
        assert resp.status_code == 201
        assert resp.data["first_name"] == "John"

    def test_retrieve_student(self, boss_client, student):
        resp = boss_client.get(f"{STUDENTS_URL}{student.id}/")
        assert resp.status_code == 200
        assert resp.data["id"] == str(student.id)

    def test_update_student(self, boss_client, student):
        resp = boss_client.patch(f"{STUDENTS_URL}{student.id}/", {"first_name": "Updated"})
        assert resp.status_code == 200
        student.refresh_from_db()
        assert student.first_name == "Updated"

    def test_archive_student(self, boss_client, student):
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/archive/", {"reason": "graduated"})
        assert resp.status_code == 200
        student.refresh_from_db()
        assert student.status == "archived"
        assert student.archived_at is not None

    def test_archive_does_not_delete(self, boss_client, student):
        boss_client.post(f"{STUDENTS_URL}{student.id}/archive/")
        assert Student.objects.filter(id=student.id).exists()

    def test_cross_company_blocked(self, boss_client, company2, db):
        other_student = Student.objects.create(
            company=company2, first_name="Other", last_name="Student",
            phone=make_phone(), status="active"
        )
        resp = boss_client.get(f"{STUDENTS_URL}{other_student.id}/")
        assert resp.status_code in (403, 404)


@pytest.mark.django_db
class TestStudentFiltering:
    def test_filter_by_status(self, boss_client, student, pending_student):
        resp = boss_client.get(f"{STUDENTS_URL}?status=active")
        assert resp.status_code == 200
        statuses = [item["status"] for item in resp.data.get("results", resp.data)]
        assert all(s == "active" for s in statuses)
