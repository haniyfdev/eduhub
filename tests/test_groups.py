import pytest
from django.utils import timezone

from apps.groups.models import Group, GroupStudent
from apps.students.models import Student
from .conftest import make_phone

GROUPS_URL = "/api/v1/groups/"


@pytest.mark.django_db
class TestGroupPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(GROUPS_URL)
        assert resp.status_code == 200

    def test_manager_can_list(self, manager_client):
        resp = manager_client.get(GROUPS_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        # GroupViewSet uses IsAuthenticated() for all actions
        resp = admin_client.get(GROUPS_URL)
        assert resp.status_code == 200

    def test_teacher_can_read(self, teacher_client):
        resp = teacher_client.get(GROUPS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(GROUPS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestGroupCRUD:
    def test_create_group_auto_number(self, boss_client, course, teacher, company):
        # GroupCreateSerializer uses `group` as FK (not group_id)
        resp = boss_client.post(GROUPS_URL, {
            "course": str(course.id),
            "teacher": str(teacher.id),
            "gender_type": "b",
        })
        assert resp.status_code == 201
        # GroupCreateSerializer doesn't expose `number`; verify via DB
        from apps.groups.models import Group
        created = Group.objects.get(id=resp.data["id"])
        assert created.number >= 1

    def test_group_display_name(self, group):
        assert group.display_name == f"{group.number}{group.gender_type}"

    def test_retrieve_group_includes_students(self, boss_client, group):
        resp = boss_client.get(f"{GROUPS_URL}{group.id}/")
        assert resp.status_code == 200
        assert "students" in resp.data

    def test_archive_group(self, boss_client, group):
        resp = boss_client.post(f"{GROUPS_URL}{group.id}/archive/")
        assert resp.status_code == 200
        group.refresh_from_db()
        assert group.status == "archived"

    def test_archive_does_not_delete(self, boss_client, group):
        boss_client.post(f"{GROUPS_URL}{group.id}/archive/")
        assert Group.objects.filter(id=group.id).exists()


@pytest.mark.django_db
class TestGroupStudentActions:
    def test_add_student_transitions_pending_to_active(self, boss_client, group, pending_student):
        resp = boss_client.post(f"{GROUPS_URL}{group.id}/add-student/", {
            "student_id": str(pending_student.id)
        })
        assert resp.status_code == 201
        pending_student.refresh_from_db()
        assert pending_student.status == "active"

    def test_add_student_creates_membership(self, boss_client, group, pending_student):
        boss_client.post(f"{GROUPS_URL}{group.id}/add-student/", {
            "student_id": str(pending_student.id)
        })
        assert GroupStudent.objects.filter(group=group, student=pending_student).exists()

    def test_remove_student_sets_left_at(self, boss_client, group, student, group_student):
        resp = boss_client.post(f"{GROUPS_URL}{group.id}/remove-student/", {
            "student_id": str(student.id)
        })
        assert resp.status_code == 200
        group_student.refresh_from_db()
        assert group_student.left_at is not None

    def test_add_nonexistent_student_returns_404(self, boss_client, group):
        import uuid
        resp = boss_client.post(f"{GROUPS_URL}{group.id}/add-student/", {
            "student_id": str(uuid.uuid4())
        })
        assert resp.status_code in (400, 404)

    def test_cross_company_student_blocked(self, boss_client, group, company2, db):
        other_student = Student.objects.create(
            company=company2, first_name="X", last_name="Y",
            phone=make_phone(), status="pending"
        )
        resp = boss_client.post(f"{GROUPS_URL}{group.id}/add-student/", {
            "student_id": str(other_student.id)
        })
        assert resp.status_code in (400, 403, 404)
