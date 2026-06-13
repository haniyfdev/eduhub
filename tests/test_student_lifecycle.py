import pytest
from datetime import date

from apps.students.models import Student
from apps.leads.models import Lead
from apps.groups.models import GroupStudent
from .conftest import make_phone

STUDENTS_URL = "/api/v1/students/"


@pytest.mark.django_db
class TestStudentFreeze:
    def test_boss_can_freeze_active_student(self, boss_client, student):
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 200
        assert resp.data["status"] == "frozen"
        student.refresh_from_db()
        assert student.status == "frozen"

    def test_admin_can_freeze(self, admin_client, student):
        resp = admin_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 200

    def test_teacher_cannot_freeze(self, teacher_client, student):
        resp = teacher_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 403

    def test_freeze_already_frozen_returns_400(self, boss_client, student):
        student.status = "frozen"
        student.save()
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 400

    def test_freeze_archived_returns_400(self, boss_client, student):
        student.status = "archived"
        student.save()
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/freeze/")
        assert resp.status_code == 400


@pytest.mark.django_db
class TestStudentUnfreeze:
    def test_unfreeze_frozen_student(self, boss_client, student):
        student.status = "frozen"
        student.save()
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/unfreeze/")
        assert resp.status_code == 200
        assert resp.data["status"] == "active"
        student.refresh_from_db()
        assert student.status == "active"

    def test_unfreeze_non_frozen_returns_400(self, boss_client, student):
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/unfreeze/")
        assert resp.status_code == 400

    def test_teacher_cannot_unfreeze(self, teacher_client, student):
        student.status = "frozen"
        student.save()
        resp = teacher_client.post(f"{STUDENTS_URL}{student.id}/unfreeze/")
        assert resp.status_code == 403


@pytest.mark.django_db
class TestStudentArchiveValidation:
    def test_archive_missing_reason_returns_400(self, boss_client, student):
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/archive/", {})
        assert resp.status_code == 400

    def test_archive_invalid_reason_returns_400(self, boss_client, student):
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/archive/", {"reason": "moved_away"})
        assert resp.status_code == 400

    def test_archive_trial_student_graduated_blocked(self, boss_client, company, db):
        trial_student = Student.objects.create(
            company=company, first_name="Trial", last_name="Student",
            phone=make_phone(), status="trial",
        )
        resp = boss_client.post(f"{STUDENTS_URL}{trial_student.id}/archive/", {"reason": "graduated"})
        assert resp.status_code == 400

    def test_archive_trial_student_dropped_out_allowed(self, boss_client, company, db):
        trial_student = Student.objects.create(
            company=company, first_name="Trial", last_name="Student",
            phone=make_phone(), status="trial",
        )
        resp = boss_client.post(f"{STUDENTS_URL}{trial_student.id}/archive/", {"reason": "dropped_out"})
        assert resp.status_code == 200
        trial_student.refresh_from_db()
        assert trial_student.status == "archived"
        assert trial_student.archive_reason == "dropped_out"


@pytest.mark.django_db
class TestStudentArchiveCascade:
    def test_archive_ends_active_group_memberships(self, boss_client, student, group_student):
        assert group_student.left_at is None
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/archive/", {"reason": "graduated"})
        assert resp.status_code == 200

        group_student.refresh_from_db()
        assert group_student.left_at is not None

    def test_archive_dropped_out_marks_lead_ignored(self, boss_client, student, company, course):
        lead = Lead.objects.create(
            company=company, first_name=student.first_name, last_name=student.last_name,
            phone=make_phone(), course=course, status="pending",
        )
        student.lead = lead
        student.save()

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/archive/", {"reason": "dropped_out"})
        assert resp.status_code == 200

        lead.refresh_from_db()
        assert lead.status == "ignored"
        student.refresh_from_db()
        assert student.lead_id is None

    def test_archive_graduated_deletes_lead(self, boss_client, student, company, course):
        lead = Lead.objects.create(
            company=company, first_name=student.first_name, last_name=student.last_name,
            phone=make_phone(), course=course, status="trial",
        )
        student.lead = lead
        student.save()

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/archive/", {"reason": "graduated"})
        assert resp.status_code == 200

        assert not Lead.objects.filter(id=lead.id).exists()
        student.refresh_from_db()
        assert student.lead_id is None


@pytest.mark.django_db
class TestStudentRestore:
    def test_boss_can_restore_archived_student(self, boss_client, student):
        student.status = "archived"
        student.archive_reason = "graduated"
        student.save()

        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/restore/")
        assert resp.status_code == 200
        assert resp.data["status"] == "active"

        student.refresh_from_db()
        assert student.status == "active"
        assert student.archive_reason is None
        assert student.archived_at is None

    def test_manager_can_restore(self, manager_client, student):
        student.status = "archived"
        student.save()
        resp = manager_client.post(f"{STUDENTS_URL}{student.id}/restore/")
        assert resp.status_code == 200

    def test_admin_cannot_restore(self, admin_client, student):
        student.status = "archived"
        student.save()
        resp = admin_client.post(f"{STUDENTS_URL}{student.id}/restore/")
        assert resp.status_code == 403

    def test_restore_non_archived_returns_400(self, boss_client, student):
        resp = boss_client.post(f"{STUDENTS_URL}{student.id}/restore/")
        assert resp.status_code == 400
