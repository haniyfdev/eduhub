import pytest
from datetime import date

from apps.lessons.models import Lesson

LESSONS_URL = "/api/v1/lessons/"


@pytest.mark.django_db
class TestLessonPermissions:
    def test_boss_can_list(self, boss_client):
        resp = boss_client.get(LESSONS_URL)
        assert resp.status_code == 200

    def test_teacher_can_list_own(self, teacher_client):
        resp = teacher_client.get(LESSONS_URL)
        assert resp.status_code == 200

    def test_admin_can_list(self, admin_client):
        resp = admin_client.get(LESSONS_URL)
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, api_client):
        resp = api_client.get(LESSONS_URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestLessonCRUD:
    def test_create_lesson(self, boss_client, group, teacher):
        # LessonCreateSerializer uses 'group' FK field directly
        resp = boss_client.post(LESSONS_URL, {
            "group": str(group.id),
            "topic": "Intro to Python",
            "date": str(date.today()),
        })
        assert resp.status_code == 201
        assert Lesson.objects.filter(topic="Intro to Python").exists()

    def test_create_lesson_sets_teacher_from_group(self, boss_client, group, teacher):
        resp = boss_client.post(LESSONS_URL, {
            "group": str(group.id),
            "topic": "Variables",
            "date": str(date.today()),
        })
        assert resp.status_code == 201
        lesson = Lesson.objects.get(id=resp.data["id"])
        assert lesson.teacher == teacher

    def test_teacher_create_lesson_for_own_group(self, teacher_client, group):
        resp = teacher_client.post(LESSONS_URL, {
            "group": str(group.id),
            "topic": "Functions",
            "date": str(date.today()),
        })
        assert resp.status_code == 201

    def test_retrieve_lesson(self, boss_client, group, teacher):
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="Test Lesson", date=date.today()
        )
        resp = boss_client.get(f"{LESSONS_URL}{lesson.id}/")
        assert resp.status_code == 200

    def test_delete_not_allowed(self, boss_client, group, teacher):
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="ToDelete", date=date.today()
        )
        resp = boss_client.delete(f"{LESSONS_URL}{lesson.id}/")
        assert resp.status_code == 405


@pytest.mark.django_db
class TestAttendanceActions:
    def test_post_bulk_attendance(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="Attendance Test", date=date.today()
        )
        resp = boss_client.post(f"{LESSONS_URL}{lesson.id}/attendance/", [
            {"student_id": str(student.id), "status": "present"}
        ], format="json")
        assert resp.status_code == 201

    def test_get_attendance(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="Get Attend", date=date.today()
        )
        resp = boss_client.get(f"{LESSONS_URL}{lesson.id}/attendance/")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestGradeActions:
    def test_post_bulk_grades(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="Grade Test", date=date.today()
        )
        resp = boss_client.post(f"{LESSONS_URL}{lesson.id}/grades/", [
            {"student_id": str(student.id), "score": 95}
        ], format="json")
        assert resp.status_code == 201

    def test_get_grades(self, boss_client, group, teacher, student, group_student):
        lesson = Lesson.objects.create(
            group=group, teacher=teacher, topic="Get Grades", date=date.today()
        )
        resp = boss_client.get(f"{LESSONS_URL}{lesson.id}/grades/")
        assert resp.status_code == 200
